"""InterviewIQ - entry point. Run with:  streamlit run frontend/streamlit_app.py
Structure: iqui/theme.py (design tokens + CSS), iqui/components.py (UI building blocks), iqui/api.py (backend client),
iqui/views/* (one module per page)."""
import streamlit as st

st.set_page_config(page_title="InterviewIQ", page_icon="IQ", layout="wide", initial_sidebar_state="expanded")

from iqui import api, components as C  # noqa: E402
from iqui.views import (candidate, candidates, interviews, jobs, overview, reports, settings)  # noqa: E402

RECRUITER_PAGES = {
    "Dashboard": overview.render,
    "Jobs": jobs.render,
    "Candidates": candidates.render,
    "Interviews": interviews.render,
    "Reports": reports.render,
    "Settings": settings.render,
}

RECRUITER_LABELS = {
    "Dashboard": "📊  Dashboard",
    "Jobs": "💼  Jobs",
    "Candidates": "👥  Candidates",
    "Interviews": "🎙️  Interviews",
    "Reports": "📑  Reports",
    "Settings": "⚙️  Settings",
}

C.inject_theme()
cfg = api.config()

with st.sidebar:
    C.brand()
    role = st.radio("Workspace", ["Recruiter", "Candidate"], horizontal=True, label_visibility="collapsed", key="role")
    if role == "Recruiter":
        C.side_label("Recruiter Workspace")
        page = st.radio(
            "Navigation",
            list(RECRUITER_PAGES),
            label_visibility="collapsed",
            key="nav_recruiter",
            format_func=lambda k: RECRUITER_LABELS.get(k, k)
        )
    else:
        C.side_label("My interview")
        page = st.radio("Navigation", candidate.PAGES, label_visibility="collapsed", key="nav_candidate")
        if st.session_state.get("cand_token"):
            candidate.sign_out_button()
    C.side_label("System")
    if cfg:
        llm = "Demo rules (no LLM)" if cfg["demo_llm"] else f"{cfg['llm_provider']} ({cfg.get('llm_model') or 'Default'})"
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
