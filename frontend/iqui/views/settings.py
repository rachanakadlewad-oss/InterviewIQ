import streamlit as st

from .. import api, components as C


def render():
    C.page_header(
        "Settings",
        "System configuration, scoring weights, decision thresholds, and AI connectivity status.",
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
    id_thresh = cfg.get("identity_threshold", 0.70)

    # 1. Mode Callout
    if is_demo:
        C.callout(
            "info",
            "Evaluation Mode: Rule-Based (Demo)",
            "The workspace is currently operating in local demo mode using deterministic screening rules and interview heuristics. Connect an AI provider in configuration for live generative reasoning."
        )
    else:
        C.callout(
            "success",
            f"Evaluation Mode: Live AI Reasoning ({provider.upper()})",
            f"Connected to {provider.title()} using model '{model_name or 'Default'}'. Screening, Interviewer, and Assessment agents run live AI evaluations."
        )

    # 2. Key Metrics Grid
    C.metric_grid([
        {
            "label": "Application Mode",
            "value": "Rule-Based Demo" if is_demo else "AI-Powered",
            "hint": "Local heuristics" if is_demo else f"Live {provider.title()} API"
        },
        {
            "label": "AI Model",
            "value": "None (Rules)" if is_demo else (model_name or "Default"),
            "hint": "Rule-based engine" if is_demo else f"Provider: {provider.title()}"
        },
        {
            "label": "Identity Check",
            "value": "Simulated Demo" if id_is_demo else "Automated Check",
            "hint": "Predefined test cases" if id_is_demo else f"Face match threshold: {id_thresh:.2f}"
        },
        {
            "label": "Evaluation Weights",
            "value": f"{w_res*100:.0f}% / {w_int*100:.0f}%",
            "hint": "Resume / Interview ratio"
        },
    ], cols=4)

    # 3. AI Connectivity & Health Check
    C.section("AI Model & Connectivity", "Verify authentication and responsiveness of the connected AI reasoning provider.")
    with st.container(border=True):
        col1, col2 = st.columns([2.2, 1.2], vertical_alignment="center")
        with col1:
            C.kv([
                ("AI Engine Mode", "Rule-based (Heuristics)" if is_demo else "Live AI Reasoning"),
                ("Provider", provider.title()),
                ("Configured Model", "None (Demo heuristics)" if is_demo else (model_name or "Default")),
                ("Service Endpoint", "Local In-Process" if is_demo else "Configured in environment"),
            ])
        with col2:
            st.markdown("**Connectivity Check**")
            st.caption("Verify live API connection and model latency.")
            if st.button("Test AI Connection", type="primary", use_container_width=True, key="btn_test_llm_conn"):
                with st.spinner("Testing model connection..."):
                    test_res = api.call("POST", "/config/test-llm")
                if test_res:
                    if test_res.get("status") == "ok":
                        lat = test_res.get("latency_ms", 0)
                        msg = test_res.get("message", "Connection verified.")
                        C.callout("success", "Connection Successful", f"{msg} (Latency: {lat} ms)")
                    else:
                        err = test_res.get("error", "Unknown error")
                        C.callout("error", "Connection Failed", err)

    # 4. Scoring Weights & Decision Thresholds
    C.section("Scoring Weights & Decision Thresholds", "Configured rules for combining resume screening with interview evaluations.")
    with st.container(border=True):
        c_w1, c_w2 = st.columns(2)
        with c_w1:
            st.markdown("##### Evaluation Weights")
            C.kv([
                ("Resume Screening Weight", f"{w_res*100:.0f}% ({w_res:.2f})"),
                ("Spoken Interview Weight", f"{w_int*100:.0f}% ({w_int:.2f})"),
                ("Combined Calculation", f"Final = ({w_res*100:.0f}% × Resume) + ({w_int*100:.0f}% × Interview)"),
            ])
        with c_w2:
            st.markdown("##### Recommendation Benchmarks")
            C.kv([
                ("Recommend Advancing", f"Final Score ≥ {thresholds.get('advance_min', 70.0):.0f} / 100"),
                ("Recruiter Review", f"{thresholds.get('review_min', 50.0):.0f} ≤ Final Score < {thresholds.get('advance_min', 70.0):.0f}"),
                ("Not Recommended", f"Final Score < {thresholds.get('review_min', 50.0):.0f} / 100"),
            ])

    # 5. Shortlisting & Interview Guardrails
    C.section("Interview Guardrails & Shortlist Rules", "Configured limits that ensure standardized, fair evaluation across candidates.")
    with st.container(border=True):
        c_l1, c_l2 = st.columns(2)
        with c_l1:
            st.markdown("##### Shortlist Rules")
            C.kv([
                ("Target Shortlist Size", f"Top {shortlist.get('top_n', 3)} candidates"),
                ("Minimum Score Cutoff", f"{shortlist.get('min_score', 40.0):.0f} / 100"),
            ])
        with c_l2:
            st.markdown("##### Interview Session Guardrails")
            C.kv([
                ("Max Questions per Session", f"{limits.get('max_questions', 8)} questions"),
                ("Max Follow-ups per Skill", f"{limits.get('max_followups', 2)} questions"),
                ("Max Competency Pivots", f"{limits.get('max_pivots', 2)} pivots"),
                ("Planned Core Skills", f"{limits.get('planned_competencies', 4)} competencies"),
            ])

    # 6. Advanced Architecture & Technical Details (Collapsible)
    with st.expander("System Architecture & Security Details (Advanced)"):
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
