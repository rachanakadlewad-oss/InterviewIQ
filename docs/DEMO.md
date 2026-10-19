# Demo scenario (about 10 minutes)

Start both servers (README). Sidebar: Recruiter.

1. **Setup & Jobs** -> *Load sample job + mock calendar*. Show the 10 competencies with weights and rubric.
2. **Resumes & Ranking** -> upload all six files from `data/sample/resumes/` -> *Upload & parse* -> *Run Recruitment Agent*.
   Expect a ranking roughly Aarav > Meera > Priya > Rohan > Karan > Sneha (demo rules). Open a candidate's evidence: every score shows verbatim resume excerpts.
3. **Shortlist & Scheduling** -> keep the top 3 -> *Confirm shortlist* -> *Schedule*. Note each candidate gets a different slot and an **access token**; files appear in `runtime/confirmations/`. Click *Schedule* again: nothing changes (no double booking).
4. Switch sidebar to **Candidate**, paste Aarav's token.
   * **Gate demo (failure):** pick `different_person` -> *Run identity check* -> "sent to human review"; reload, you cannot start. Switch to Recruiter -> **Identity Review Queue** -> resolve `approve_retry`.
   * Candidate again: choose `match` -> pass -> *Start interview*. (Demo adapter banner stays visible.)
5. **Interview.** The question is spoken (browser TTS). Use the mic button or type. Suggested answers are in `data/sample/demo_answers.json` (keyed by competency). Key moment: for the database question answer with the `databases` text, which says *"I also mentored two juniors..."* -> the agent should pick **BROAD_PIVOT** to leadership/mentoring - not a fixed question tree. Give a vague answer like "I did some work on it" once to see **NARROW_FOLLOW_UP**.
   Try the *Periodic identity re-check* expander with `swap_mid_session` -> the interview is suspended and appears in the review queue.
6. After the last answer the Assessment Agent runs. Candidate view shows **feedback only** (strengths / weaknesses / improvement areas - no scores, no decision).
7. Recruiter -> **Reports & Decisions**: scores table (resume vs interview vs weight), final score formula, flags (e.g. "DEMO MODE", "question cap reached"), evidence per competency, the **decision trace** (trigger phrase, reasoning, decision, question) and identity log. Record ADVANCE/HOLD/REJECT yourself.
8. Show files: `runtime/identity_logs/identity_log_<id>.json`, `runtime/traces/interview_trace_<id>.json`.

Headless alternative: `run_demo_cli.bat` prints the same flow in the console.

**Showing the gate violations (good for viva):** in the API docs (`/docs`) call `POST /portal/interview/start` with a token whose identity has not passed -> `409 GATE_VIOLATION`.
