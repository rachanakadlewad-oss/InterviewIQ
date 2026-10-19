import streamlit as st

from .. import api, components as C


def render():
    C.page_header("Settings & Demo Information", "How this installation is configured and what its limits are. Secrets are never shown here.", "Recruiter workspace")
    cfg = api.config()
    if not cfg:
        C.callout("error", "Backend offline", "Start the backend with run_backend.bat and refresh.")
        return
    C.section("Application mode")
    if cfg["demo_llm"]:
        C.callout("warning", "Demo mode - deterministic rules, no LLM",
                  "All three agents use keyword and pattern rules. Outputs are labelled 'Demo rules' throughout. Set LLM_PROVIDER, LLM_API_KEY and LLM_MODEL in .env to use a real model.")
    else:
        C.callout("success", f"LLM provider: {cfg['llm_provider']}", f"Model: {cfg.get('llm_model') or 'provider default'}. API key configured: {'yes' if cfg.get('llm_configured') else 'no'} (value hidden).")
    C.kv([("LLM mode", "Demo rules" if cfg["demo_llm"] else cfg["llm_provider"]), ("Identity verification", "Demo adapter" if cfg["identity_is_demo"] else "OpenCV basic heuristic"),
          ("Recruiter API key required", "Yes" if cfg["recruiter_auth_enabled"] else "No (local demo)"), ("Interview only at slot time", "Yes" if cfg["enforce_slot_time"] else "No")])
    C.section("Scoring and limits")
    w = cfg["weights"]
    C.kv([("Resume weight", w["resume"]), ("Interview weight", w["interview"]), ("Advance threshold", cfg["thresholds"]["advance_min"]),
          ("Review threshold", cfg["thresholds"]["review_min"]), ("Shortlist proposal", f"top {cfg['shortlist']['top_n']}, minimum {cfg['shortlist']['min_score']}"),
          ("Max interview questions", cfg["limits"]["max_questions"]), ("Max follow-ups per competency", cfg["limits"]["max_followups"]),
          ("Max broad pivots", cfg["limits"]["max_pivots"]), ("Identity threshold", cfg["identity_threshold"])])
    st.caption("Change these in the .env file and restart the backend. Final score = resume weight x resume score + interview weight x interview score.")
    C.section("Architecture")
    st.markdown("Three LLM agents - **Recruitment**, **Interviewer**, **Assessment** - are coordinated by a deterministic LangGraph supervisor (not an LLM). "
                "Scheduling, scoring, the identity gate and the interview stopping rules are ordinary code. The recruiter makes every hiring decision.")
    C.section("Known limitations")
    for t in ["Demo mode scoring is keyword matching, not understanding.",
              "The demo identity adapter is not biometric verification; the OpenCV backend is a weak heuristic without liveness detection.",
              "Voice input uses the browser's speech recognition (Chrome or Edge) and needs microphone permission; typing always works.",
              "Confirmations are saved as local files. No e-mail is sent.",
              "Scanned (image-only) PDFs cannot be read.",
              "The recruiter console has no user login unless RECRUITER_API_KEY is set."]:
        st.markdown(f"- {t}")
    if cfg["demo_identity_scenarios"] and cfg["identity_is_demo"]:
        with st.expander("Demo identity scenarios"):
            st.write(", ".join(cfg["demo_identity_scenarios"]))
