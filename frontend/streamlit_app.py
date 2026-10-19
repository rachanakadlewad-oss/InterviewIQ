"""InterviewIQ - entry point. Run with:  streamlit run frontend/streamlit_app.py
Structure: iqui/theme.py (design tokens + CSS), iqui/components.py (UI building blocks), iqui/api.py (backend client),
iqui/views/* (one module per page)."""
import streamlit as st

st.set_page_config(page_title="InterviewIQ", page_icon="IQ", layout="wide", initial_sidebar_state="expanded")

from iqui import api, components as C  # noqa: E402
from iqui.views import (candidate, candidates, identity_review, jobs, overview, reports, scheduling, settings)  # noqa: E402

RECRUITER_PAGES = {
    "Overview": overview.render,
    "Jobs": jobs.render,
    "Candidates": candidates.render,
    "Shortlist & Scheduling": scheduling.render,
    "Identity Review": identity_review.render,
    "Reports & Decisions": reports.render,
    "Settings & Demo Info": settings.render,
}

C.inject_theme()
cfg = api.config()

with st.sidebar:
    C.brand()
    role = st.radio("Workspace", ["Recruiter", "Candidate"], horizontal=True, label_visibility="collapsed", key="role")
    if role == "Recruiter":
        C.side_label("Recruiter")
        page = st.radio("Navigation", list(RECRUITER_PAGES), label_visibility="collapsed", key="nav_recruiter")
    else:
        C.side_label("My interview")
        page = st.radio("Navigation", candidate.PAGES, label_visibility="collapsed", key="nav_candidate")
        if st.session_state.get("cand_token"):
            candidate.sign_out_button()
    C.side_label("System")
    if cfg:
        llm = "Demo rules (no LLM)" if cfg["demo_llm"] else f"{cfg['llm_provider']}"
        idm = "Demo adapter" if cfg["identity_is_demo"] else "OpenCV heuristic"
        st.markdown(f'<div class="iq-mode"><b>AI:</b> {llm}<br><b>Identity:</b> {idm}</div>', unsafe_allow_html=True)
    else:
        C.callout("error", "Backend offline", "Run run_backend.bat")

if cfg is None:
    C.page_header("Cannot reach the backend", "InterviewIQ needs its API server running.")
    C.callout("error", "Backend offline", f"Expected at {api.API}. Open a terminal and run run_backend.bat, then refresh this page.")
elif role == "Recruiter":
    api.show_flash()
    RECRUITER_PAGES[page]()
else:
    candidate.render(page)
