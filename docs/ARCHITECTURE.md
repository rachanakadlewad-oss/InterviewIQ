# InterviewIQ - Architecture

## 1. Pipeline (matches the revised faculty specification)

```
JD + 10 competencies -> [1] resume intake & shortlist -> [2] auto-scheduling -> [3] IDENTITY GATE
        -> [4] agent-conducted spoken interview -> [5] combined recommendation (human decides)
```
Stage 3 is a **hard gate**: pass -> interview may start; fail/inconclusive -> human review queue, interview does **not** start.

## 2. Components

| Layer | Files | Notes |
|---|---|---|
| API | `app/api/main.py` | FastAPI. Recruiter routes (optional `X-API-Key`), candidate routes (per-application access token). |
| Supervisor | `app/workflow/supervisor.py`, `state.py` | **Deterministic LangGraph orchestrator - not an LLM.** Three compiled graphs share one `PipelineState`. |
| Agents (exactly 3) | `app/agents/recruitment.py`, `interviewer.py`, `assessment.py` | LLM-backed; run through `agents/base.py` (schema validation + semantic checks + bounded retries). |
| Demo logic | `app/agents/demo_logic.py` | Deterministic keyword rules used only when `LLM_PROVIDER=demo`. Outputs are labelled `demo_rules`. |
| Deterministic services | `services/` | resume parsing, interview engine (guards), scoring aggregation, scheduler, identity, reports, state machine. |
| Persistence | `app/db.py` | SQLAlchemy 2.x + SQLite. |
| UI | `frontend/streamlit_app.py`, `voice_component/` | Recruiter console + candidate portal; voice via browser Web Speech API. |

### LangGraph graphs
```
screening : load -> (apps?) score -> rank -> END
identity  : precheck -> verify -> record -> pass: mark_passed | fail: human_review -> END
interview : gate -> start: init_session -> END
                 -> answer: record -> decide -> concluded: assess -> END | else END (wait for next answer)
```
The graphs are invoked per event (upload/screen, identity check, each answer) because a human sits between steps;
state is persisted in the DB between invocations.

## 3. Who decides what

| Concern | Owner | Why |
|---|---|---|
| Understand resume/answer **meaning**; pick NARROW/BROAD/NEXT/CONCLUDE; write the next question | LLM agents | Requires semantic reasoning |
| Score aggregation, ranking, weights, thresholds | `services/scoring.py` | Must be transparent and reproducible |
| Scheduling, double-booking prevention | `services/scheduler.py` | Correctness-critical |
| Identity gate | `services/identity.py` + state machine | Must not be bypassable by an LLM |
| Interview completion, follow-up/pivot caps, no repeats | `services/interview_engine.py` | Prevents loops; agent only *proposes* |
| Final hiring decision | **Human recruiter** | Responsible-AI requirement |

## 4. Agent contracts (validated schemas, `app/schemas.py`)

* **Recruitment Agent** -> `ResumeScoringOutput`: per competency `score 0-10`, `evidence[]`, `justification`.
  Semantic checks: every JD competency present exactly once; score > 0 requires evidence; **each evidence quote must be a verbatim excerpt of the resume** (fabricated evidence is rejected and retried).
* **Interviewer Agent** -> `InterviewerDecision {trigger_phrase, reasoning, decision, target_competency, question}`.
  Semantic checks: `trigger_phrase` must be quoted from the candidate's last answer; decision must be in `allowed_decisions`; NEXT target must be a remaining planned competency; question <= 45 words (voice-ready); question must not repeat an earlier one.
* **Assessment Agent** -> `AssessmentOutput`: per-competency interview score + verbatim evidence, recruiter summary, strengths/weaknesses, `candidate_feedback`.
  Semantic checks: all covered competencies assessed; evidence verbatim from the candidate's answers; candidate feedback must not contain numeric scores.

### Failure handling
| Failure | Behaviour |
|---|---|
| Invalid JSON / schema / semantic check | Retry up to `AGENT_MAX_RETRIES` with the error fed back; then `AgentError` |
| LLM timeout / HTTP error | Same bounded retries with backoff |
| Recruitment Agent fails | Application -> `SCORING_FAILED` (recruiter can re-run); pipeline continues for others |
| Interviewer Agent fails | Supervisor uses a **labelled `fallback`** decision (next planned competency, rubric seed question); flagged in the report |
| Assessment Agent fails | Application -> `ASSESSMENT_FAILED`; `POST /applications/{id}/assessment/retry` |

## 5. Adaptive interview rules (`interview_engine.py`)

**Planning.** Priority = `JD weight x (1 + (10 - resume score)/10)`; top `PLANNED_COMPETENCIES` (default 4) are planned. High-weight competencies whose resume evidence is weak are verified first.

**Per turn** (after the candidate answers): the agent proposes a decision; the engine then applies these guards (each override is logged in `guard_note` with the agent's original proposal in `agent_decision`):
1. `CONCLUDE` only if all planned competencies are covered, or >= `MIN_COMPETENCIES_COVERED` covered and >= `MIN_QUESTIONS_BEFORE_CONCLUDE` questions asked.
2. `NARROW_FOLLOW_UP` <= `MAX_FOLLOWUPS_PER_COMPETENCY` (2) per competency.
3. `BROAD_PIVOT` <= `MAX_BROAD_PIVOTS` (2) and must target a competency **not yet explored**; it can be a JD competency not in the plan or an entirely new one (`extra_<name>`).
4. **Budget fairness:** extras (follow-up/pivot) are allowed only while every uncovered planned competency can still get a question.
5. **No repeats:** a question with Jaccard word-overlap > 0.75 against any earlier question is replaced.
6. **Hard cap:** after `MAX_QUESTIONS` (8) the supervisor concludes without calling the agent.
Therefore the interview always terminates in <= 8 questions.

**Trace** (`TraceEntry`, stored in DB and `runtime/traces/interview_trace_<id>.json`) - one per turn:
`{trigger_phrase, reasoning, decision, competency, question_asked, source, guard_note}`. The opening question's trigger is the *plan* (no answer exists yet) and is labelled `trigger_source=plan`.

## 6. Scoring (documented, configurable)

```
resume_score    = sum(w_c * resume_c) / sum(w_c)  * 10          over ALL JD competencies          (0-100)
interview_score = sum(w_c * interview_c) / sum(w_c) * 10        over PLANNED competencies that were assessed (renormalised)
final_score     = WEIGHT_RESUME * resume_score + WEIGHT_INTERVIEW * interview_score      (defaults 0.4 / 0.6)
label           = >= 70 RECOMMEND_ADVANCE | >= 50 BORDERLINE_RECRUITER_REVIEW | else NOT_RECOMMENDED
```
`w_c` = competency weight from the JD. Pivot/unplanned competencies are *reported* (evidence + score) but do not change the interview score. Unassessed planned competencies are flagged. If no interview score exists the final equals the resume score (flagged). Weights must sum to 1 (validated at start-up). The label is advisory - the recruiter records ADVANCE / HOLD / REJECT separately.

## 7. Identity verification

`passed = face_detected AND single_face AND match_confidence >= IDENTITY_MATCH_THRESHOLD`, otherwise fail; backend errors, unreadable images or a missing reference photo are `inconclusive` = fail. Every check is appended to `runtime/identity_logs/identity_log_<application_id>.json` (timestamp, backend, face count, confidence, threshold, result, reason, warning).

* `IDENTITY_BACKEND=demo` - **demo adapter**; outcome picked via an explicit scenario; flagged `is_real_biometric=false` everywhere (log, API, UI).
* `IDENTITY_BACKEND=opencv_basic` - real face *detection* (Haar) and a *weak* LBP-histogram similarity. **Not biometric grade** - it is sensitive to pose, lighting and cannot defend against spoofing. A production system would plug an embedding model (e.g. InsightFace/DeepFace) and liveness detection into the same `verify()` interface.
* **No swap mid-session:** `/portal/identity-check?check_type=mid_session` re-runs the check; a failure suspends the session and creates a review item. Re-checks are candidate-triggered in this build (the UI offers a button); automatic periodic capture is not implemented.
* **Data minimisation:** live frames are never written to disk; the reference photo is deleted when the assessment completes, on rejection, or via `purge-biometrics`.

## 8. Application status machine (`services/state_machine.py`)
`PARSED -> SCORED -> SHORTLISTED -> SCHEDULED -> (IDENTITY_PASSED | HUMAN_REVIEW) -> INTERVIEW_IN_PROGRESS -> INTERVIEW_COMPLETE -> ASSESSED -> DECIDED`.
`INTERVIEW_IN_PROGRESS` is reachable only from `IDENTITY_PASSED` (or from `HUMAN_REVIEW` for a suspended session after a recorded human pass). The interview graph's first node also re-checks that the **latest** identity record passed.

## 9. Scheduling
Slots are loaded from a mock calendar JSON. Booking is an atomic compare-and-set (`UPDATE ... WHERE application_id IS NULL`), the `application_id` column is UNIQUE (one slot per candidate), and overlapping bookings on the same resource are skipped. Confirmation artifacts (`confirmation_<id>.json`, `email_<id>.txt`) are files - **no e-mail is sent**.

## 10. Voice
Browser Web Speech API: `SpeechSynthesis` reads each question aloud (all major browsers); `SpeechRecognition` transcribes (Chrome/Edge only, needs internet - the browser vendor's service performs recognition - and microphone permission). The transcript lands in an editable text box; the text box alone is a full fallback. Questions are short and single-sentence so they are speakable. Whisper STT would be a drop-in replacement for the transcript step (not implemented).

## 11. Assumptions (documented where the spec was silent)
1. Dataset: synthetic fictional resumes are shipped; the Kaggle Resume Dataset / LFW can be used by dropping files in (parser accepts PDF/DOCX/TXT; use real photos only with consent).
2. "Interview response score" = Assessment Agent per-competency score (0-10) aggregated as above.
3. Interview is allowed any time after the identity pass; `ENFORCE_SLOT_TIME=true` additionally blocks identity checks before the booked slot starts.
4. One interview session per application; no rescheduling UI (service `release_booking` exists).
5. Recruiter console has no login (local demo); optional shared `RECRUITER_API_KEY`. Candidate access uses an unguessable token.
