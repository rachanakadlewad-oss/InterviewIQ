import streamlit as st

from .. import api, components as C


def render():
    C.page_header(
        "Settings",
        "Inspect active backend configuration, evaluation thresholds, and operational limits, and test live AI provider connectivity.",
        "Recruiter workspace"
    )

    cfg = api.config()
    if not cfg:
        C.callout("error", "Backend Offline", "Could not connect to the InterviewIQ backend service. Ensure the backend server is running and refresh this page.")
        return

    is_demo = cfg.get("demo_llm", True)
    provider = cfg.get("llm_provider", "demo")
    model_name = cfg.get("llm_model")
    w = cfg.get("weights", {"resume": 0.4, "interview": 0.6})
    w_res = float(w.get("resume", 0.4))
    w_int = float(w.get("interview", 0.6))
    limits = cfg.get("limits", {})
    thresholds = cfg.get("thresholds", {})
    shortlist = cfg.get("shortlist", {})
    id_is_demo = cfg.get("identity_is_demo", True)
    id_backend = cfg.get("identity_backend", "demo")
    id_thresh = cfg.get("identity_threshold", 0.70)

    # 1. Mode Callout
    if is_demo:
        C.callout(
            "warning",
            "Operating in Deterministic Demo Mode (No LLM Active)",
            "The application is executing deterministic regex and heuristic rule-based logic for resume screening, dynamic questioning, and assessment. "
            "To enable live AI reasoning, set LLM_PROVIDER (openai/anthropic), LLM_API_KEY, and LLM_MODEL in .env."
        )
    else:
        C.callout(
            "success",
            f"Operating in LLM-Powered Mode ({provider.upper()})",
            f"Connected to external provider '{provider}' using model '{model_name or 'Default'}'. "
            "Recruitment, Interviewer, and Assessment agents run live inferences with structured Pydantic schema validation."
        )

    # 2. Key Metrics Grid
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
            "hint": "Simulated scenarios" if id_is_demo else f"Haar + LBP (Thr: {id_thresh:.2f})"
        },
        {
            "label": "Scoring Weight",
            "value": f"{w_res*100:.0f}% / {w_int*100:.0f}%",
            "hint": "Resume / Interview ratio"
        },
    ])

    st.markdown("---")

    # 3. Interactive LLM Connectivity Test Tool
    st.markdown("### 1. AI Model & Connectivity")
    with st.container(border=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            C.kv([
                ("AI Mode", "Deterministic Demo (Heuristics)" if is_demo else "Live LLM Reasoning"),
                ("Provider", provider.title()),
                ("Model Name", "None (Demo heuristics)" if is_demo else (model_name or "Default")),
                ("API Endpoint", "Local in-process" if is_demo else "Configured in .env"),
            ])
        with col2:
            st.markdown("**Test Model Connectivity**")
            st.caption("Perform a live test call to verify authentication, endpoint connectivity, and model responsiveness.")
            if st.button("Test Live Connection", type="primary", use_container_width=True, key="btn_test_llm_conn"):
                with st.spinner("Pinging model endpoint..."):
                    test_res = api.call("POST", "/config/test-llm")
                if test_res:
                    if test_res.get("status") == "ok":
                        lat = test_res.get("latency_ms", 0)
                        msg = test_res.get("message", "Connection verified.")
                        C.callout("success", "Connection Successful", f"{msg} (Latency: {lat} ms)")
                    else:
                        err = test_res.get("error", "Unknown error")
                        C.callout("error", "Connection Failed", err)

    # 4. Scoring Weights & Hiring Thresholds
    st.markdown("### 2. Scoring Weights & Decision Thresholds")
    with st.container(border=True):
        c_w1, c_w2 = st.columns(2)
        with c_w1:
            st.markdown("##### Score Aggregation Weights")
            C.kv([
                ("Resume Score Weight", f"{w_res*100:.0f}% ({w_res:.2f})"),
                ("Interview Score Weight", f"{w_int*100:.0f}% ({w_int:.2f})"),
                ("Weighted Combination", f"Final = ({w_res:.2f} × Resume) + ({w_int:.2f} × Interview)"),
            ])
        with c_w2:
            st.markdown("##### Recommendation Cutoffs")
            C.kv([
                ("Recommend Advancing", f"Score ≥ {thresholds.get('advance_min', 70.0):.0f} / 100"),
                ("Borderline / Recruiter Review", f"{thresholds.get('review_min', 50.0):.0f} ≤ Score < {thresholds.get('advance_min', 70.0):.0f}"),
                ("Not Recommended", f"Score < {thresholds.get('review_min', 50.0):.0f} / 100"),
            ])

    # 5. Shortlisting & Interview Guardrails
    st.markdown("### 3. Shortlisting & Interview Limits")
    with st.container(border=True):
        c_l1, c_l2 = st.columns(2)
        with c_l1:
            st.markdown("##### Shortlisting Guardrails")
            C.kv([
                ("Target Shortlist Size", f"Top {shortlist.get('top_n', 3)} candidates"),
                ("Minimum Score Cutoff", f"{shortlist.get('min_score', 40.0):.0f} / 100"),
            ])
        with c_l2:
            st.markdown("##### Dynamic Interview Limits")
            C.kv([
                ("Max Questions per Interview", str(limits.get("max_questions", 8))),
                ("Max Follow-ups per Competency", str(limits.get("max_followups", 2))),
                ("Max Broad Pivots", str(limits.get("max_pivots", 2))),
                ("Planned Competencies", str(limits.get("planned_competencies", 4))),
            ])

    # 6. Advanced Architecture & Technical Details (Collapsible)
    with st.expander("Advanced: System Architecture, LangGraph Supervision & Integrity Guards"):
        st.markdown(
            "#### LangGraph Deterministic Supervisor\n"
            "The hiring workflow is coordinated by a deterministic Python state machine orchestrated with LangGraph:\n"
            "1. **Screening Graph:** Loads parsed applications, invokes Recruitment Agent with rubric validation, computes weighted rank.\n"
            "2. **Identity Gate Graph:** Pre-checks slot timing, evaluates biometric / scenario match, enforces gate lock until passed.\n"
            "3. **Interview Graph:** Manages turn-by-turn dialogue, enforces question caps, calls Interviewer Agent for adaptive decisions, triggers Assessment Agent upon conclusion.\n"
            "\n"
            "#### Prompt Injection & Data Isolation\n"
            "- Resume text and candidate transcripts are treated as **untrusted data** and isolated from instruction streams.\n"
            "- All agent outputs are strictly validated against Pydantic schemas before state transitions.\n"
            "- Secrets, API keys, and database passwords are never exposed via API endpoints or user interfaces."
        )
