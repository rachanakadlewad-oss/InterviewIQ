from pathlib import Path

import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header(
        "Candidates",
        "Upload resumes, run AI screening against competency rubrics, rank candidates, and confirm your interview shortlist.",
        "Recruiter workspace"
    )
    job_id = api.job_picker()
    if not job_id:
        return
    job = api.call("GET", f"/jobs/{job_id}") or {"title": f"Job #{job_id}", "competencies": []}
    job_title = job.get("title", f"Job #{job_id}")
    cfg = api.config() or {}

    if cfg.get("demo_llm"):
        C.callout(
            "warning",
            "Demo Mode Active: Rule-Based Keyword Scoring",
            "Resume evaluation is running deterministic heuristics. Configure an LLM provider (openai/anthropic) in .env for live semantic scoring."
        )
    elif cfg:
        C.callout(
            "info",
            f"Live AI Screening Active ({cfg.get('llm_provider', 'LLM').upper()} / {cfg.get('llm_model', 'Default')})",
            "The Recruitment Agent semantically scores resumes against role competency rubrics and verifies verbatim evidence."
        )

    # 4 Sequential Steps on One Page
    upload_section(job_id)
    screening_section(job_id)
    shortlist_and_ranking_section(job_id, job_title, cfg)
    inspection_section(job_id, job)


def upload_section(job_id):
    C.section("1. Upload Resumes", "Drop PDF, DOCX or TXT resumes (up to 8 MB each). Reference photos are optional.")
    with st.container(border=True):
        files = st.file_uploader("Candidate resumes", accept_multiple_files=True, type=["pdf", "docx", "txt"], key=f"up_{job_id}")
        photos = []
        with st.expander("Optional: Reference photos for identity verification"):
            st.caption("Name photo like the resume (e.g. Aarav_Mehta.jpg). Photos embedded in documents are extracted automatically.")
            photos = st.file_uploader("Reference photos", accept_multiple_files=True, type=["jpg", "jpeg", "png"], key=f"ph_{job_id}")

        if st.button("Upload and parse resumes", type="primary", disabled=not files, use_container_width=True):
            pm = {Path(p.name).stem: p for p in photos or []}
            results = []
            bar = st.progress(0.0, text="Uploading and parsing...")
            for i, f in enumerate(files):
                parts = {"file": (f.name, f.getvalue())}
                if Path(f.name).stem in pm:
                    ph = pm[Path(f.name).stem]
                    parts["photo"] = (ph.name, ph.getvalue())
                ok, data = api.request("POST", f"/jobs/{job_id}/applications", files=parts)
                results.append({"file": f.name, "ok": ok, "data": data})
                bar.progress((i + 1) / len(files), text=f"Processed {i + 1} of {len(files)}")
            bar.empty()
            st.session_state["upload_results"] = results

        res = st.session_state.get("upload_results")
        if res:
            rows = []
            for r in res:
                if r["ok"]:
                    d = r["data"]
                    rows.append({"file": r["file"], "status": C.badge("Parsed", "success"), "candidate": d["name"] or "(name not found)",
                                 "detail": f"{len(d.get('skills', []))} skills detected; reference photo: {'yes' if d.get('has_reference_photo') else 'no'}"})
                else:
                    rows.append({"file": r["file"], "status": C.badge("Failed", "error"), "candidate": "-", "detail": r["data"]})
            C.table([("file", "File", "strong"), ("status", "Result"), ("candidate", "Candidate"), ("detail", "Details")], rows)
            ok_n = sum(1 for r in res if r["ok"])
            st.caption(f"{ok_n} of {len(res)} file(s) parsed successfully.")


def screening_section(job_id):
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
        rescore_clicked = c2.button(rescore_lbl, disabled=not scored_apps, help="Recalculate competency scores with active model.", use_container_width=True)
        c3.caption(f"{len(scored_apps)} scored / {len(apps)} total applicants. Scoring calibrates direct, partial, and missing evidence.")

        if score_clicked:
            with st.spinner("Scoring resumes against role competencies..."):
                r = api.call("POST", f"/jobs/{job_id}/screen")
            if r:
                if r.get("scored"):
                    api.flash("success", f"Scored {len(r['scored'])} candidate(s)", "Rankings updated below.")
                for f in r.get("failed", []):
                    C.callout("error", f"Application {f['application_id']} scoring failed", f["error"])
                st.rerun()

        if rescore_clicked:
            with st.spinner("Recalculating competency scores..."):
                r = api.call("POST", f"/jobs/{job_id}/screen?rescore=true")
            if r:
                if r.get("scored"):
                    api.flash("success", f"Rescored {len(r['scored'])} candidate(s)", "Candidate rankings recalculated.")
                for f in r.get("failed", []):
                    C.callout("error", f"Application {f['application_id']} could not be scored", f["error"])
                st.rerun()


def shortlist_and_ranking_section(job_id, job_title, cfg):
    C.section("3. Candidate Ranking & Shortlist", "Confirm which candidates move forward to interview scheduling.")
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    scored_apps = [a for a in apps if a["resume_score"] is not None]

    if not scored_apps:
        C.empty_state("No scored candidates yet", "Upload and score resumes in Steps 1 & 2 above.")
        return

    sorted_apps = H.sort_candidates_by_score(scored_apps)
    selectable_apps = [a for a in sorted_apps if a["status"] in ("SCORED", "SHORTLISTED")]
    confirmed_in_db = H.get_confirmed_shortlist_ids(selectable_apps)

    sel_key = f"sl_selected_{job_id}"
    if sel_key not in st.session_state:
        st.session_state[sel_key] = list(confirmed_in_db)

    selected_ids = list(dict.fromkeys(st.session_state[sel_key]))
    top_n = (cfg.get("shortlist") or {}).get("top_n", 3)

    with st.container(border=True):
        # Ranking Table
        C.table(
            [("rank", "Rank", "r"), ("name", "Candidate", "strong"), ("score", "Resume Score"), ("status", "Status"), ("shortlisted", "Shortlisted?"), ("src", "Scored by")],
            [{"rank": a["rank"] if a.get("rank") is not None else "-",
              "name": a.get("name") or f"Application #{a['application_id']}",
              "score": C.score_bar(a["resume_score"], 100),
              "status": C.status_badge(a["status"]),
              "shortlisted": C.badge("Yes", "success", dot=False) if a.get("shortlisted") else C.badge("No", "neutral", dot=False),
              "src": C.source_badge(a.get("scoring_source"))}
             for a in sorted_apps]
        )

        st.markdown("---")
        st.markdown(f"#### Shortlist Selection for {job_title}")
        num_selected = len(selected_ids)
        num_selectable = len(selectable_apps)

        t1, t2, t3, t4 = st.columns([2.5, 1.2, 1.2, 1])
        with t1:
            st.markdown(
                f'<div class="iq-sl-pill"><i></i><span>Selected: <b>{num_selected}</b> of {num_selectable} candidates</span></div>'
                f'<span style="font-size:0.78rem;color:var(--muted);margin-left:0.6rem">Target: top {top_n}</span>',
                unsafe_allow_html=True
            )
        with t2:
            if st.button(f"Select top {top_n}", key=f"btn_top_{job_id}"):
                st.session_state[sel_key] = [a["application_id"] for a in selectable_apps[:top_n]]
                st.rerun()
        with t3:
            if st.button("Select all", key=f"btn_all_{job_id}"):
                st.session_state[sel_key] = [a["application_id"] for a in selectable_apps]
                st.rerun()
        with t4:
            if st.button("Clear", key=f"btn_clear_{job_id}"):
                st.session_state[sel_key] = []
                st.rerun()

        # Candidate Cards for toggle
        for a in sorted_apps:
            aid = a["application_id"]
            is_locked = a["status"] not in ("SCORED", "SHORTLISTED")
            is_selected = aid in selected_ids

            c_info, c_btn = st.columns([4.4, 1.2])
            with c_info:
                C._emit(C.candidate_card_html(a, job_title, is_selected=is_selected, is_locked=is_locked))
            with c_btn:
                if is_locked:
                    st.caption("🔒 Scheduled")
                elif is_selected:
                    if st.button("✕ Remove", key=f"rem_{aid}", use_container_width=True):
                        st.session_state[sel_key] = H.remove_candidate_from_selection(st.session_state[sel_key], aid)
                        st.rerun()
                else:
                    if st.button("➕ Add", key=f"add_{aid}", type="secondary", use_container_width=True):
                        st.session_state[sel_key] = H.add_candidate_to_selection(st.session_state[sel_key], aid)
                        st.rerun()

        # Confirmation Action Bar
        has_unconfirmed = set(selected_ids) != set(confirmed_in_db)
        if num_selected > 0:
            names = ", ".join(f"**{a['name'] or a['application_id']}** ({a['resume_score']:.1f}/100)"
                              for a in selectable_apps if a["application_id"] in selected_ids)
            st.markdown(f"**{num_selected} candidate(s) ready to confirm:** {names}")
            if has_unconfirmed:
                st.caption("⚠️ Unsaved changes: click 'Confirm Shortlist' to enable interview scheduling.")

        b1, b2 = st.columns([2, 1])
        with b1:
            if st.button("Confirm Shortlist", type="primary", use_container_width=True, key=f"confirm_sl_{job_id}"):
                valid, errors = H.validate_shortlist_selection(selected_ids, selectable_apps)
                if not valid:
                    for err in errors:
                        C.callout("error", "Validation Error", err)
                else:
                    res = api.call("POST", f"/jobs/{job_id}/shortlist", json={"application_ids": selected_ids})
                    if res is not None:
                        api.flash("success", "Shortlist Confirmed",
                                  f"Successfully confirmed {len(selected_ids)} candidate(s) for '{job_title}'. "
                                  "They are now eligible for scheduling on the Interviews page.")
                        st.rerun()
        with b2:
            if confirmed_in_db:
                if st.button("Reset Shortlist", use_container_width=True, key=f"reset_sl_{job_id}"):
                    res = api.call("POST", f"/jobs/{job_id}/shortlist", json={"application_ids": []})
                    if res is not None:
                        st.session_state[sel_key] = []
                        api.flash("info", "Shortlist Reset", "All candidates returned to Scored status.")
                        st.rerun()


def inspection_section(job_id, job):
    C.section("4. Candidate Inspection & Evidence", "Select a candidate to view parsed resume profile and verbatim competency evidence.")
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    if not apps:
        return
    with st.container(border=True):
        pick = st.selectbox(
            "Select candidate to inspect",
            [a["application_id"] for a in apps],
            key="cand_inspect_pick",
            format_func=lambda i: next(
                f"{a['name'] or 'Application'} (#{i}) - Resume: {a['resume_score']:.1f}/100"
                if a.get("resume_score") is not None else f"{a['name'] or 'Application'} (#{i}) - Not scored"
                for a in apps if a["application_id"] == i
            )
        )
        rep = api.call("GET", f"/applications/{pick}/report")
        if not rep:
            return
        row = next(a for a in apps if a["application_id"] == pick)
        cand_name = row.get("name") or f"Candidate #{pick}"
        score_display = f"{row['resume_score']:.1f}/100" if row.get("resume_score") is not None else "Not scored"

        st.markdown(
            f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:0.75rem;padding:0.6rem 0.85rem;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-sm);margin:0.5rem 0 0.85rem;">'
            f'<div style="display:flex;align-items:center;gap:0.6rem;flex-wrap:wrap">'
            f'<b style="font-size:1.05rem;color:var(--text);">{cand_name}</b>'
            f'{C.status_badge(row["status"])}'
            f'{C.source_badge(rep["resume"]["source"])}'
            f'</div>'
            f'<div style="font-size:0.9rem;font-weight:650;color:var(--text);">Resume Score: <span style="color:var(--primary-hover);">{score_display}</span></div>'
            f'</div>',
            unsafe_allow_html=True
        )

        t_prof, t_ev = st.tabs(["Candidate Profile", "Competency Evidence"])
        with t_prof:
            p = rep["profile"]
            C.kv([("Full Name", p.get("name")), ("Email Address", p.get("email")), ("Phone Number", p.get("phone")),
                  ("Experience (years)", p.get("experience_years") or "not stated")])
            if p.get("skills"):
                st.markdown("##### Skills Detected in Resume")
                C.badges(*[C.badge(s, "neutral", dot=False) for s in p["skills"]])
            if p.get("experience"):
                st.markdown("##### Professional Experience & Roles")
                for ex in p["experience"]:
                    C.quote(ex)
            if p.get("projects"):
                st.markdown("##### Key Projects & Contributions")
                for pr in p["projects"]:
                    C.quote(pr)
            if p.get("education"):
                st.markdown("##### Education & Qualifications")
                for e in p["education"]:
                    C.quote(e)
            if p.get("summary"):
                st.markdown("##### Professional Summary")
                C.quote(p["summary"])

        with t_ev:
            scores = {s["competency_id"]: s for s in rep["resume"]["per_competency"]}
            if not scores:
                C.empty_state("Not scored yet", "Run scoring in Step 2 to view evidence.")
            else:
                for c in job.get("competencies", []):
                    s = scores.get(c["id"])
                    analysis = H.analyze_competency_details(c, s)
                    with st.expander(f"{c['name']}   ·   {analysis['score']:.1f} / 10   [{analysis['level_label']}]", expanded=False):
                        C.competency_evidence_card(c, s)
