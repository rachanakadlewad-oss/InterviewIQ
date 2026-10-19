# Viva notes

## What was verified and how (be precise about this)
| Item | Status |
|---|---|
| Syntax of every module | `py_compile` on all files - OK |
| 126 tests incl. UI helpers/components and overview (schemas, parser, scoring, identity, agents, interview engine, scheduler, workflow/supervisor) | **Passed in the build sandbox, but against minimal stand-ins** for Pydantic v2, LangGraph `StateGraph`, SQLAlchemy and pytest (the sandbox had no network/pip). They validate *our* logic (guards, gates, scoring, traces, failure handling). They do **not** prove compatibility with the real libraries. |
| Real PyMuPDF path | Not run (pypdf fallback was exercised on the sample PDFs) |
| Real Pydantic / SQLAlchemy / LangGraph | Not run in the sandbox. Code uses only mainstream v2 APIs; first `run_tests.bat` on your PC is the true test. |
| `tests/test_api.py` + FastAPI app | Executed under a FastAPI **stand-in** (12 tests pass); never run on real FastAPI |
| Streamlit UI (redesign) | Every page's code executed (42 renders) via a fake Streamlit against the real backend logic; custom HTML/CSS screenshotted in headless Chromium. **Real Streamlit never launched**; native widget styling unverified |
| Voice component | Written, never executed in a browser |
| Real LLM calls (openai/anthropic) | **Implemented, never executed** against a live provider |
| Concurrency of slot booking | CAS + UNIQUE constraint by design; the concurrency test is single-threaded (no real race run) |
| OpenCV identity | Detection/unreadable-image/no-face paths tested; **a real face-match was not tested** (no face images available offline); similarity threshold 0.70 is **uncalibrated** |

## Likely questions and answers
* **Why exactly three agents and a non-LLM supervisor?** Semantic judgement (resume meaning, answer meaning, assessment) needs an LLM; gating, scheduling, scoring and loop control must be deterministic, auditable and un-bypassable. The supervisor is a LangGraph graph with plain-Python routing.
* **How does the interviewer avoid being a fixed question tree?** It receives the last answer, remaining/unexplored competencies and rubrics, and returns a decision + a *newly written* question. It may BROAD_PIVOT to a competency outside the plan (stored as `extra_*`). In demo mode this is only a cue-word lexicon - say so.
* **How do you stop infinite follow-ups / repeats?** Engine guards (caps, budget fairness, Jaccard repeat check, hard 8-question cap). The agent only proposes; overrides are logged.
* **How is hallucinated evidence prevented?** Evidence must be a verbatim substring of the resume/answers, else the output is rejected and retried; `trigger_phrase` must be quoted from the answer.
* **Is the identity check biometric?** Not by default (demo adapter). `opencv_basic` is a weak heuristic. The *gate logic* (pass/fail/inconclusive -> human review; no interview start) is real and tested.
* **Bias/fairness?** Prompts forbid protected attributes and score substance only; scoring is rubric-based with evidence; human decides. Not formally audited - state this limitation.
* **Privacy?** Live frames are never stored; reference photo deleted after assessment/rejection; only confidence scores are logged; tokens are random; recruiter API key optional.
* **Why Streamlit + browser speech?** Zero-install voice with Chrome/Edge; limitations: STT Chrome/Edge only and cloud-based, needs mic permission; text fallback always available.
* **Why is the final score 40/60?** Interview evidence is richer and more current than resume claims; weights are configurable in `.env` and shown in every report.

## Known limitations
Demo-mode scoring is crude keyword matching; no OCR for scanned PDFs; no real e-mail; no rescheduling UI; mid-session identity re-check is button-triggered, not automatic; no recruiter login; no liveness/anti-spoofing; no formal bias audit; SQLite single-node only; LLM prompts untuned (expect to iterate once a real model is connected).
