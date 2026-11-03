# 1. Update frontend/iqui/views/candidates.py
with open('frontend/iqui/views/candidates.py', 'r', encoding='utf-8') as f:
    cand_txt = f.read()

old_screen_top = '''def screening_section(job_id):
    C.section("2. Score & Rank Resumes", "Evaluate evidence against rubrics, compute weighted scores (0-100), and rank candidates.")
    with st.container(border=True):
        apps = api.call("GET", f"/jobs/{job_id}/applications") or []
        todo = [a for a in apps if a["status"] in ("PARSED", "SCORING_FAILED")]
        scored_apps = [a for a in apps if a["resume_score"] is not None]

        c1, c2, c3 = st.columns([1.5, 1.5, 3])
        score_clicked = c1.button(f"Score {len(todo)} resume(s)" if todo else "All scored", type="primary", disabled=not todo, use_container_width=True)
        rescore_clicked = c2.button("Rescore all & re-rank", disabled=not scored_apps, help="Recalculate competency scores and update rankings.", use_container_width=True)'''

new_screen_top = '''def screening_section(job_id):
    C.section("2. Score & Rank Resumes", "Evaluate evidence against rubrics, compute weighted scores (0-100), and rank candidates.")
    cfg = api.config() or {}
    is_live_llm = not cfg.get("demo_llm", True)

    with st.container(border=True):
        apps = api.call("GET", f"/jobs/{job_id}/applications") or []
        todo = [a for a in apps if a["status"] in ("PARSED", "SCORING_FAILED")]
        scored_apps = [a for a in apps if a["resume_score"] is not None]
        demo_scored = [a for a in scored_apps if a.get("scoring_source") == "demo_rules"]

        if is_live_llm and demo_scored:
            C.callout(
                "info",
                f"{len(demo_scored)} candidate(s) evaluated under Demo Rules",
                "These candidates were scored using heuristic demo rules before LLM mode was activated. "
                "Click 'Rescore with Active LLM' to evaluate them using genuine AI reasoning with the configured model."
            )

        c1, c2, c3 = st.columns([1.5, 2.0, 2.5])
        score_clicked = c1.button(f"Score {len(todo)} resume(s)" if todo else "All scored", type="primary", disabled=not todo, use_container_width=True)
        rescore_lbl = "Rescore with Active LLM" if (is_live_llm and demo_scored) else "Rescore all & re-rank"
        rescore_clicked = c2.button(rescore_lbl, disabled=not scored_apps, help="Recalculate competency scores with active model.", use_container_width=True)'''

assert old_screen_top in cand_txt, 'old_screen_top not found'
cand_txt = cand_txt.replace(old_screen_top, new_screen_top)
with open('frontend/iqui/views/candidates.py', 'w', encoding='utf-8') as f:
    f.write(cand_txt)
print('Updated frontend/iqui/views/candidates.py')

# 2. Update frontend/iqui/views/settings.py
with open('frontend/iqui/views/settings.py', 'r', encoding='utf-8') as f:
    set_txt = f.read()

old_set_callout = '''    else:
        C.callout(
            "success",
            f"Operating in LLM-Powered Mode ({provider.upper()})",
            f"Connected to external provider '{provider}' using model '{model_name or 'Default'}'. "
            "Recruitment, Interviewer, and Assessment agents run live inferences with structured Pydantic schema validation."
        )'''

new_set_callout = '''    else:
        C.callout(
            "success",
            f"Operating in LLM-Powered Mode ({provider.upper()})",
            f"Connected to external provider '{provider}' using model '{model_name or 'Default'}'. "
            "Recruitment, Interviewer, and Assessment agents run live inferences with structured Pydantic schema validation. "
            "Note: Previously evaluated candidate records retain their original scoring label (e.g. 'Demo Rules') until rescored from the Candidates page."
        )'''

assert old_set_callout in set_txt, 'old_set_callout not found'
set_txt = set_txt.replace(old_set_callout, new_set_callout)
with open('frontend/iqui/views/settings.py', 'w', encoding='utf-8') as f:
    f.write(set_txt)
print('Updated frontend/iqui/views/settings.py')
