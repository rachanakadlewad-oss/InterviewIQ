import streamlit as st

from .. import api, components as C


def render():
    C.page_header(
        "Settings & Demo Information",
        "Inspect active backend configuration, evaluation thresholds, system architecture, and operational limits. Credentials and secrets are never exposed.",
        "Recruiter workspace"
    )

    cfg = api.config()
    if not cfg:
        C.callout("error", "Backend Offline", "Could not connect to the InterviewIQ backend service. Ensure the backend server is running and refresh this page.")
        return

    is_demo = cfg.get("demo_llm", True)
    provider = cfg.get("llm_provider", "demo")
    model_name = cfg.get("llm_model")
    conn_status = cfg.get("llm_connection_status", "demo_mode")
    w = cfg.get("weights", {"resume": 0.4, "interview": 0.6})
    w_res = float(w.get("resume", 0.4))
    w_int = float(w.get("interview", 0.6))
    limits = cfg.get("limits", {})
    thresholds = cfg.get("thresholds", {})
    shortlist = cfg.get("shortlist", {})
    id_is_demo = cfg.get("identity_is_demo", True)
    id_backend = cfg.get("identity_backend", "demo")
    id_thresh = cfg.get("identity_threshold", 0.70)

    # -------------------------------------------------------------
    # 1. Application Mode Banner (Accurate mode labeling)
    # -------------------------------------------------------------
    if is_demo:
        C.callout(
            "warning",
            "Operating in Deterministic Demo Mode (No LLM Active)",
            "The application is executing deterministic regex and heuristic rule-based logic (app/agents/demo_logic.py) "
            "for resume screening, dynamic questioning, and assessment. NO external LLM is invoked and NO AI inference is performed. "
            "Outputs are accurately labeled as 'Demo rules' throughout the application. To enable live LLM inference, configure LLM_PROVIDER (openai or anthropic), "
            "LLM_API_KEY, and LLM_MODEL in your environment."
        )
    else:
        C.callout(
            "success",
            f"Operating in LLM-Powered Mode ({provider.upper()})",
            f"Connected to external provider '{provider}' using model '{model_name or 'Default'}'. "
            "The Recruitment, Interviewer, and Assessment modules run live LLM inferences with structured Pydantic schema validation."
        )

    # -------------------------------------------------------------
    # 2. Key Metrics Overview Cards
    # -------------------------------------------------------------
    C.metric_grid([
        {
            "label": "Application Mode",
            "value": "Demo Rules" if is_demo else "LLM-Powered",
            "hint": "Deterministic heuristics" if is_demo else f"Live {provider.title()} API"
        },
        {
            "label": "Configured Model",
            "value": "None (Rules)" if is_demo else (model_name or "Default"),
            "hint": "No model in demo mode" if is_demo else f"Provider: {provider}"
        },
        {
            "label": "Identity Mode",
            "value": "Demo Adapter" if id_is_demo else "OpenCV Heuristic",
            "hint": "Simulated scenarios" if id_is_demo else "Haar + LBP"
        },
        {
            "label": "Scoring Weight",
            "value": f"{w_res*100:.0f}% / {w_int*100:.0f}%",
            "hint": "Resume / Interview ratio"
        },
    ])

    st.markdown("---")

    # -------------------------------------------------------------
    # 3. Model & AI Intelligence Configuration
    # -------------------------------------------------------------
    st.markdown("### 1. LLM & Intelligence Configuration")
    with st.container(border=True):
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            conn_display = "Not Applicable (Demo rules operate locally without network calls)" if is_demo else (
                "Available (API Key configured)" if cfg.get("llm_configured") else "Disconnected / Missing API Key"
            )
            C.kv([
                ("Application Mode", "Deterministic Demo (No LLM)" if is_demo else "Live LLM-Powered"),
                ("LLM Provider", provider.title()),
                ("Model Name", "None (Demo heuristics active)" if is_demo else (model_name or "Provider Default")),
                ("Connection Status", conn_display),
            ])
        with col_m2:
            C.kv([
                ("Max Agent Retries", str(limits.get("max_retries", 2))),
                ("Validation Framework", "Pydantic Schema Validation"),
                ("Prompt Injection Guard", "Active (Inputs isolated as untrusted data)"),
                ("Recruiter API Key", "Enforced" if cfg.get("recruiter_auth_enabled") else "Disabled (Local Demo)"),
            ])

        st.markdown("#### Mode Distinction: Deterministic Demo Rules vs. Live LLM")
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown(
                f'<div style="background:rgba(250,173,20,0.08);border:1px solid rgba(250,173,20,0.3);padding:0.9rem;border-radius:6px;">'
                f'<b style="color:var(--warning);">Deterministic Demo Rules (Current)</b><br>'
                f'<span style="font-size:0.85rem;color:var(--text2);">'
                f'• Operates offline with zero external API calls.<br>'
                f'• Evaluates competency keywords, measurable project metrics, and regex pattern matching.<br>'
                f'• Dynamically picks structured follow-up questions from an curated answer rubric.<br>'
                f'• Scores and recommendations are labelled as <b>Demo rules</b> across all views.</span></div>',
                unsafe_allow_html=True
            )
        with col_d2:
            st.markdown(
                f'<div style="background:rgba(22,119,255,0.08);border:1px solid rgba(22,119,255,0.3);padding:0.9rem;border-radius:6px;">'
                f'<b style="color:var(--primary);">Actual LLM-Powered Mode (Optional)</b><br>'
                f'<span style="font-size:0.85rem;color:var(--text2);">'
                f'• Invokes real language models (e.g., GPT-4o, Claude 3.5 Sonnet).<br>'
                f'• Evaluates nuanced contextual evidence and depth of understanding.<br>'
                f'• Synthesizes adaptive conversational follow-up questions in real time.<br>'
                f'• Generates qualitative reasoning, labeled as <b>LLM inference</b>.</span></div>',
                unsafe_allow_html=True
            )

    # -------------------------------------------------------------
    # 4. Evaluation Weights, Thresholds & Scoring Formula
    # -------------------------------------------------------------
    st.markdown("### 2. Scoring Formula, Thresholds & Shortlist Configuration")
    with st.container(border=True):
        st.markdown(
            f'<div class="iq-callout info" style="margin-bottom:1rem;">'
            f'<div><div class="t">Configured Mathematical Scoring Formula</div>'
            f'<div class="b"><b>Final Score = (Resume Weight × Resume Score) + (Interview Weight × Interview Score)</b><br>'
            f'= ({w_res:.2f} × Resume Score) + ({w_int:.2f} × Interview Score)<br>'
            f'<i>Resume Weight: {w_res*100:.0f}% · Interview Weight: {w_int*100:.0f}% · Sum = {(w_res + w_int)*100:.0f}%</i>'
            f'</div></div></div>',
            unsafe_allow_html=True
        )

        col_w1, col_w2 = st.columns(2)
        with col_w1:
            C.kv([
                ("Resume Scoring Weight", f"{w_res:.2f} ({w_res*100:.0f}%)"),
                ("Interview Scoring Weight", f"{w_int:.2f} ({w_int*100:.0f}%)"),
                ("Advance Threshold (Min)", f"{thresholds.get('advance_min', 70.0):.1f} / 100"),
                ("Review Threshold (Min)", f"{thresholds.get('review_min', 50.0):.1f} / 100"),
            ])
        with col_w2:
            C.kv([
                ("Shortlist Proposal Top N", f"Top {shortlist.get('top_n', 3)} candidates"),
                ("Shortlist Minimum Score", f"{shortlist.get('min_score', 40.0):.1f} / 100"),
                ("Recruiter Shortlist Control", "Mandatory (Recruiter must confirm shortlist)"),
                ("Recommendation Status", "Advisory Only (Recruiter retains hiring authority)"),
            ])

    # -------------------------------------------------------------
    # 5. Interview Session & Operational Limits
    # -------------------------------------------------------------
    st.markdown("### 3. Interview Session & Progression Limits")
    with st.container(border=True):
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            C.kv([
                ("Max Interview Questions", f"{limits.get('max_questions', 8)} questions"),
                ("Max Follow-ups per Competency", f"{limits.get('max_followups', 2)} follow-ups"),
                ("Max Broad Pivots", f"{limits.get('max_pivots', 2)} pivots"),
            ])
        with col_l2:
            C.kv([
                ("Planned Competencies per Role", f"{limits.get('planned_competencies', 4)} competencies"),
                ("Min Competencies Covered", f"{limits.get('min_competencies', 3)} competencies"),
                ("Interview Time Enforcement", "Enforced" if cfg.get("enforce_slot_time") else "Disabled (Flexible Testing)"),
            ])

    # -------------------------------------------------------------
    # 6. Identity Verification Configuration
    # -------------------------------------------------------------
    st.markdown("### 4. Identity Verification Configuration")
    with st.container(border=True):
        col_i1, col_i2 = st.columns(2)
        with col_i1:
            id_name = "Demo Adapter (Simulated Scenarios - Non-Biometric)" if id_is_demo else "OpenCV Basic Heuristic (Haar + LBP - Non-Biometric Grade)"
            C.kv([
                ("Identity Backend", id_name),
                ("Verification Match Threshold", f"{id_thresh:.2f} (Required: {id_thresh*100:.0f}% match)"),
                ("Security Gate Rule", "Single face detected AND confidence >= threshold"),
            ])
        with col_i2:
            C.kv([
                ("Ambiguous Outcome Action", "Routes to Recruiter Identity Review queue"),
                ("Interview Gate Behavior", "Strictly locked until verification passes or override is logged"),
                ("Biometric Status", "⚠️ Not Real Biometric Verification (Demo / Heuristic Only)"),
            ])

        if id_is_demo and cfg.get("demo_identity_scenarios"):
            with st.expander("Available Demo Identity Scenarios", expanded=False):
                st.caption("These scenarios are selectable in candidate portal when using the demo identity adapter:")
                st.write(", ".join(cfg["demo_identity_scenarios"]))

    # -------------------------------------------------------------
    # 7. System Architecture Overview
    # -------------------------------------------------------------
    st.markdown("### 5. System Architecture Overview")
    with st.container(border=True):
        st.markdown(
            "The InterviewIQ platform is built on a hybrid architecture combining **deterministic workflow coordination** "
            "with **dynamic pipeline modules** (which execute rule-based logic in demo mode or live model calls in LLM mode):"
        )

        st.markdown(
            "1. **LangGraph State Graph Coordinator (`app/workflow/supervisor.py`)**:\n"
            "   - Coordinated entirely by deterministic Python code (NOT an LLM).\n"
            "   - Enforces valid state transitions: `PARSED → SCORED → SHORTLISTED → SCHEDULED → IDENTITY_PASSED → INTERVIEW_IN_PROGRESS → INTERVIEW_COMPLETE → ASSESSED → DECIDED`.\n"
            "   - Enforces hard security gates preventing interview start prior to identity clearance."
        )

        st.markdown(
            "2. **Three Pipeline Processing Modules**:\n"
            "   - **Recruitment Module (`app/agents/recruitment.py`)**: Parses resumes, extracts structured competencies, projects, and calculates baseline resume scores. Uses deterministic heuristics in Demo mode or LLM prompt extraction when configured.\n"
            "   - **Interviewer Module (`app/agents/interviewer.py`)**: Governs conversational turns (`NEXT_COMPETENCY`, `NARROW_FOLLOW_UP`, `BROAD_PIVOT`, `CONCLUDE`). Uses scripted questions in Demo mode or LLM generation when configured.\n"
            "   - **Assessment Module (`app/agents/assessment.py`)**: Evaluates interview transcripts against competency rubrics. Evaluates via deterministic rubrics in Demo mode or LLM synthesis when configured."
        )

        st.markdown(
            "3. **Deterministic Core Engines (Always Code, Never an LLM)**:\n"
            "   - **Interview Engine (`app/services/interview_engine.py`)**: Turn counts, stopping triggers, question budgeting, and competency coverage tracking.\n"
            "   - **Scoring Engine (`app/services/scoring.py`)**: Mathematical calculation: `(0.40 × Resume) + (0.60 × Interview)`.\n"
            "   - **Scheduling Engine (`app/services/scheduler.py`)**: Transactional room allocation, time-slot deduplication, and overlap prevention.\n"
            "   - **Human Recruiter Authority**: AI recommendations and benchmarks remain non-binding; the human recruiter always retains complete final decision authority."
        )

    # -------------------------------------------------------------
    # 8. Operational Limitations & Security
    # -------------------------------------------------------------
    st.markdown("### 6. Known Operational Limitations")
    with st.container(border=True):
        limitations = [
            "**Demo Mode Heuristics**: In demo mode, scoring and questioning use keyword and pattern heuristics rather than deep semantic comprehension.",
            "**Non-Biometric Identity**: The demo identity adapter simulates test scenarios; the OpenCV heuristic uses basic Haar cascades without 3D liveness detection. Neither is biometric grade.",
            "**Scanned Document Handling**: Image-only scanned PDFs require external OCR preprocessing before upload; standard text PDFs and DOCX are parsed directly.",
            "**Browser Speech Recognition**: Voice input utilizes browser Web Speech API (supported in Chrome/Edge); typed responses are universally supported across all browsers.",
            "**Local Data Storage**: Candidate records, interview transcripts, and audit logs are persisted in local SQLite (`runtime/interviewiq.db`) and local files. No external SMTP email is dispatched.",
            "**Advisory AI Recommendations**: All AI scores and recommendation labels are strictly decision support. Human recruiters must manually review and confirm hiring decisions.",
            "**Credential Security**: API keys, passwords, and sensitive system secrets are never rendered in the frontend or transmitted to clients."
        ]
        for lim in limitations:
            st.markdown(f"- {lim}")
