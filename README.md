# InterviewIQ - Agentic AI End-to-End Hiring Pipeline

JD -> resume shortlist -> auto-scheduling -> **identity gate** -> adaptive spoken AI interview -> combined recommendation (human decides).
Three LLM agents (Recruitment, Interviewer, Assessment) coordinated by a **deterministic LangGraph supervisor**.

> **Read this first - what is real and what is demo**
> * `LLM_PROVIDER=demo` (default, no key): agents run **keyword/rule heuristics**, labelled `demo_rules` everywhere. This is *not* LLM intelligence.
> * Real reasoning needs `LLM_PROVIDER=openai|anthropic` + a key. That path is implemented but **was not exercised against a live provider** (see "Verification status").
> * `IDENTITY_BACKEND=demo` is a **demo adapter**: you choose the outcome. It is *not* biometric verification. `opencv_basic` does real face detection with a weak similarity score - *not biometric grade*.

## Windows setup (VS Code terminal, PowerShell or cmd)

Prerequisite: Python 3.10-3.12 from python.org ("Add python.exe to PATH" ticked).

```bat
cd interviewiq
setup.bat
```
`setup.bat` creates `.venv`, installs `requirements.txt`, copies `.env.example` to `.env`, and generates the demo data. Manual equivalent:
```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python data\generate_demo_data.py
```
(PowerShell: if activation is blocked run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.)

## Run

Terminal 1 - backend (http://127.0.0.1:8000, docs at /docs):
```bat
run_backend.bat
```
Terminal 2 - UI (opens http://localhost:8501):
```bat
run_frontend.bat
```
Fast check without UI (whole pipeline in the console):
```bat
run_demo_cli.bat
```
Tests:
```bat
run_tests.bat
```
Use **Chrome or Edge** for voice input. The sample calendar is generated relative to the day you run `generate_demo_data.py`; if scheduling says "no free slot", re-run it and use *(Re)load mock calendar*.

## Using a real LLM
Edit `.env`:
```
LLM_PROVIDER=openai            # or anthropic
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini          # any chat model that follows JSON instructions
LLM_BASE_URL=                  # blank = OpenAI; Groq/OpenRouter/Ollama work via their OpenAI-compatible URL
```
Restart the backend. The UI sidebar switches from the orange DEMO banner to "Real LLM". Weights, limits and identity threshold are all in `.env` (documented in `docs/ARCHITECTURE.md`).

## Project layout
```
app/agents/        recruitment.py interviewer.py assessment.py base.py demo_logic.py
app/workflow/      supervisor.py (LangGraph) state.py
app/services/      resume_parser scoring scheduler slotlogic identity interview_engine reports state_machine
app/api/main.py    FastAPI        app/db.py SQLAlchemy models     app/schemas.py Pydantic contracts
frontend/          streamlit_app.py (entry), iqui/ (theme, components, api client, views/), voice_component/ (browser STT/TTS)
data/              generate_demo_data.py, sample/ (JD, calendar, 6 fictional resumes, scripted answers)
scripts/           run_demo_cli.py (headless end-to-end demo)
tests/             pytest suite (126 tests)   docs/  ARCHITECTURE.md DEMO.md VIVA_NOTES.md UI_REDESIGN.md
```
Runtime output (created automatically in `runtime/`): `interviewiq.db`, `identity_logs/identity_log_<id>.json`, `traces/interview_trace_<id>.json`, `confirmations/`.

## Verification status (honest)
The build sandbox had no network, so Pydantic, LangGraph, SQLAlchemy, FastAPI, Streamlit and pytest were **stand-ins written for testing only** (not shipped). 126 tests passed under them, and every UI page was executed against the real backend logic through a fake Streamlit; custom components were rendered in headless Chromium. **Not verified:** the real libraries, the real Streamlit shell/widgets, PyMuPDF, live LLM calls, real voice/biometrics. Run `run_tests.bat` and click through the UI on your machine first; see `docs/UI_REDESIGN.md` section 6 and `docs/VIVA_NOTES.md`.

## Sample data
All resumes are fictional (`data/sample/resumes`). The Kaggle Resume Dataset can be used by saving rows as `.txt/.pdf/.docx` and uploading. For real-face testing of `opencv_basic`, upload a photo of **yourself** (with consent) as the reference and use your webcam.
