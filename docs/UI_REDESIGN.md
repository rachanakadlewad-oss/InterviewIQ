# UI redesign - what changed

Framework kept: **Streamlit** (no migration). Backend, agents, LangGraph supervisor, DB models and existing API routes/schemas are unchanged; only additive backend fields/endpoints were added (section 4).

## 1. Inventory before the redesign
| Area | What existed |
|---|---|
| Frontend | one file `frontend/streamlit_app.py` (336 lines): default Streamlit theme, radio navigation, 5 recruiter pages + 1 candidate page, raw JSON textarea for job creation, `st.dataframe` tables, light voice component |
| Backend | FastAPI `app/api/main.py` (29 routes), Supervisor (3 LangGraph graphs), 3 agents, services (parser, scoring, scheduler, identity, interview engine, reports), SQLAlchemy models |
| Tests | 89 test functions (9 modules) |
| Run scripts | `setup.bat`, `run_backend.bat`, `run_frontend.bat`, `run_tests.bat`, `run_demo_cli.bat` (unchanged) |
A backup of the pre-redesign project was kept at `interviewiq_backup_before_redesign/` (not shipped in the zip).

## 2. New frontend structure
```
.streamlit/config.toml            dark base theme (#080B12 / #111827 / #1677FF ...)
frontend/streamlit_app.py         entry: theme, sidebar (brand, workspace switch, nav, mode box), routing
frontend/iqui/theme.py            design tokens + all CSS
frontend/iqui/components.py       reusable UI: page_header, metric_grid, badge, table, funnel, stepper, callout,
                                  empty_state, trace timeline, question_card ... (all user text HTML-escaped)
frontend/iqui/helpers.py          pure logic (status labels/tones, candidate progress, form validation) - unit-tested
frontend/iqui/api.py              backend client, error handling, flash messages, shared job selector
frontend/iqui/views/              overview, jobs, candidates, scheduling, identity_review, reports, settings, candidate
frontend/voice_component/         restyled (dark) browser speech component
```

## 3. Pages
Recruiter: **Overview** (live metrics, pipeline funnel, pending actions, next step) - **Jobs** (guided form with competency table + rubric levels, validation, JSON import demoted to "Advanced") - **Candidates** (multi-file upload with per-file result, score & rank, ranked table, parsed profile, per-competency evidence, demo-vs-LLM badges) - **Shortlist & Scheduling** (shortlist, schedule, scheduled-interview table, per-day calendar, slot generation, honest "no email sent" note) - **Identity Review** (open/resolved queue, check history with confidence vs threshold, resolution actions with required notes, demo-adapter disclosure) - **Reports & Decisions** (score cards with weights, AI recommendation kept visually separate from the recruiter decision, competency table + evidence, transcript, decision trace timeline, identity log, JSON download) - **Settings & Demo Info** (mode, weights, thresholds, limits, limitations; no secrets).
Candidate: **My Application** (progress stepper) - **Interview Details** - **Identity Verification** - **Join Interview** (focused room: context, progress, history, question card, voice + text, loading/complete states) - **My Feedback** (strengths, improvements, per-topic level + the candidate's own words).

## 4. Backend changes (all additive; reasons)
| Change | Why |
|---|---|
| `GET /overview`, `app/services/overview.py` | dashboard needs real aggregated metrics, funnel and pending actions |
| `GET /applications` | all-jobs applicant list with job titles |
| `/slots` + candidate/job/status/`confirmation_file` | scheduling table shows who is booked and whether the local confirmation file exists |
| `/reviews` + candidate/job/resolution/notes, `status=ALL` | identity-review queue and history |
| `/applications/{id}/report` + `transcript` | recruiters see the conversation |
| `/config` + status flags (never secrets) | settings page |
| `/portal/me` + `job_title`, `max_questions` | candidate screens (own application only) |
| `candidate_feedback()` + job and per-topic `{name, level, evidence}` | evidence-based feedback; level is a band derived from the real score, number never shown; evidence is the candidate's own verbatim words |
| `scheduler.generate_slots`, `POST /calendar/generate`, `load_calendar(now=...)` | the shipped sample calendar goes stale (found while testing: scheduling failed once the sample dates passed). Slots are now generated for the next working days, idempotently, and past slots are ignored |
| overview: job with no applicants -> "upload resumes" | found by UI testing: it previously said "all caught up" |
No change to: agents, Supervisor/LangGraph, DB models, schemas, scoring/weights, identity gate, interview engine.

## 5. Security / privacy decisions
Candidates authenticate with a per-application token; every `/portal/*` call is scoped to that application server-side, so recruiter reports and other candidates are unreachable (tested: feedback JSON contains no scores, rank, recommendation or email). The identity gate remains enforced in the backend (409), not by hiding buttons. All candidate/resume text rendered in HTML is escaped (tested with a hostile resume name).

## 6. What to inspect manually (I could not launch the real Streamlit UI)
1. `run_backend.bat`, `run_frontend.bat`, open http://localhost:8501.
2. Check native widgets look dark and aligned: sidebar radio nav (selected item highlight), buttons (primary = blue), text inputs, tabs, expanders, file uploader, the competency table editor on Jobs -> "Create a job".
3. Resize the browser narrow: cards should wrap; columns stack.
4. In Chrome/Edge test the microphone button on Join Interview.
5. If a Streamlit upgrade changes widget markup, only `frontend/iqui/theme.py` needs touching; `.streamlit/config.toml` keeps the base dark palette regardless.
