from pathlib import Path

import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header("Candidates & Resume Screening", "Upload resumes, let the Recruitment Agent score them against the job's competencies, "
                  "and inspect the evidence behind every score.", "Recruiter workspace")
    job_id = api.job_picker()
    if not job_id:
        return
    cfg = api.config() or {}
    if cfg.get("demo_llm"):
        C.callout("warning", "Demo mode: scores come from keyword rules, not an LLM",
                  "Each resume line that mentions a competency keyword is quoted as evidence. Configure an LLM provider in .env for semantic scoring.")
    elif cfg:
        C.callout("info", f"Scoring with {cfg['llm_provider']} / {cfg.get('llm_model') or 'default model'}",
                  "Every score must cite verbatim resume excerpts; invalid outputs are rejected and retried.")

    upload_section(job_id)
    screening_section(job_id)
    list_section(job_id)


def upload_section(job_id):
    C.section("1. Upload Resumes", "PDF, DOCX or TXT, up to 8 MB each. Scanned image-only PDFs require OCR preprocessing.")
    with st.container(border=True):
        files = st.file_uploader("Drop one or more resumes", accept_multiple_files=True, type=["pdf", "docx", "txt"], key=f"up_{job_id}")
        photos = []
        with st.expander("Optional: Reference photos for identity verification"):
            st.caption("Name each photo like its resume (e.g. Priya_Nair.jpg). Photos embedded in a resume are used automatically when present.")
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
                                 "detail": f"{len(d['skills'])} skills detected; reference photo: {'yes' if d['has_reference_photo'] else 'no'}"})
                else:
                    rows.append({"file": r["file"], "status": C.badge("Failed", "error"), "candidate": "-", "detail": r["data"]})
            C.table([("file", "File", "strong"), ("status", "Result"), ("candidate", "Candidate"), ("detail", "Details")], rows)
            ok_n = sum(1 for r in res if r["ok"])
            st.caption(f"{ok_n} of {len(res)} file(s) parsed. Failed files were not added.")


def screening_section(job_id):
    C.section("2. Score and Rank", "Evaluate evidence relevance, calculate competency scores, and rank applicants.")
    with st.container(border=True):
        apps = api.call("GET", f"/jobs/{job_id}/applications") or []
        todo = [a for a in apps if a["status"] in ("PARSED", "SCORING_FAILED")]
        scored_apps = [a for a in apps if a["resume_score"] is not None]
        c1, c2, c3 = st.columns([1.2, 1.3, 2.5])
        score_clicked = c1.button(f"Score {len(todo)} resume(s)" if todo else "All scored", type="primary", disabled=not todo, use_container_width=True)
        rescore_clicked = c2.button("Rescore all & re-rank", disabled=not scored_apps, help="Recalculate competency scores and update candidate rankings using updated scoring logic.", use_container_width=True)
        c3.caption("Evaluates direct vs partial vs missing evidence, checks action responsibilities and verified metrics, and recalculates rankings.")

        if score_clicked:
            with st.spinner("Scoring resumes against role competencies..."):
                r = api.call("POST", f"/jobs/{job_id}/screen")
            if r:
                if r["scored"]:
                    api.flash("success", f"Scored {len(r['scored'])} candidate(s)", "Rankings updated below.")
                for f in r["failed"]:
                    C.callout("error", f"Application {f['application_id']} could not be scored", f["error"])
                st.rerun()

        if rescore_clicked:
            with st.spinner("Recalculating competency scores and candidate rankings..."):
                r = api.call("POST", f"/jobs/{job_id}/screen?rescore=true")
            if r:
                if r["scored"]:
                    api.flash("success", f"Rescored {len(r['scored'])} candidate(s)", "Candidate rankings recalculated with updated competency scores.")
                for f in r["failed"]:
                    C.callout("error", f"Application {f['application_id']} could not be scored", f["error"])
                st.rerun()


def list_section(job_id):
    C.section("3. Candidate Ranking & Inspection", "Ranked in descending order of resume score (0-100). Select a candidate for detailed profile and competency evidence.")
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    if not apps:
        C.empty_state("No candidates yet", "Upload resumes in Step 1 above to get started.")
        return
    job = api.call("GET", f"/jobs/{job_id}") or {"title": "", "competencies": []}
    C.table([("rank", "Rank", "r"), ("name", "Candidate", "strong"), ("job", "Job"), ("score", "Resume score"), ("status", "Status"), ("src", "Scored by")],
            [{"rank": a["rank"] if a["rank"] is not None else "-", "name": a["name"] or f"Application #{a['application_id']}", "job": job["title"],
              "score": C.score_bar(a["resume_score"], 100) if a["resume_score"] is not None else "not scored",
              "status": C.status_badge(a["status"]), "src": C.source_badge(a["scoring_source"])} for a in apps])

    with st.container(border=True):
        st.markdown("#### Candidate Inspection")
        pick = st.selectbox("Select candidate to inspect", [a["application_id"] for a in apps], key="cand_pick",
                            format_func=lambda i: next(f"{a['name'] or 'Application'} (#{i}) - Score: {a['resume_score']:.1f}/100" if a["resume_score"] is not None else f"{a['name'] or 'Application'} (#{i})" for a in apps if a["application_id"] == i))
        detail_view(pick, job, next(a for a in apps if a["application_id"] == pick))


def detail_view(app_id, job, row):
    rep = api.call("GET", f"/applications/{app_id}/report")
    if not rep:
        return
    cand_name = row.get("name") or f"Candidate #{app_id}"
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
    if row.get("scoring_error"):
        C.callout("error", "Scoring failed for this candidate", row["scoring_error"])
    t_profile, t_evidence = st.tabs(["Parsed Profile", "Competency Evidence"])
    with t_profile:
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
        st.caption("Profile fields are extracted directly from the resume text with enhanced pattern matching. Missing fields are left blank, never invented.")
    with t_evidence:
        scores = {s["competency_id"]: s for s in rep["resume"]["per_competency"]}
        if not scores:
            C.empty_state("Not scored yet", "Run scoring to see evidence for each competency.")
            return
        if rep["resume"]["source"] == "demo_rules":
            C.callout("warning", "Demo Heuristic Evidence Evaluation",
                      "Scores are computed using deterministic heuristics that evaluate evidence relevance (Direct vs Partial vs Missing), check action responsibilities and verified metrics, and prevent inflated scores. Configure an LLM provider in .env for semantic AI evaluation.")
        else:
            C.callout("info", "AI Semantic Evidence Evaluation",
                      "Scores are evaluated by the Recruitment Agent LLM against the competency rubric with verbatim evidence verification.")
        for c in job["competencies"]:
            s = scores.get(c["id"])
            analysis = H.analyze_competency_details(c, s)
            with st.expander(f"{c['name']}   ·   {analysis['score']:.1f} / 10   [{analysis['level_label']}]", expanded=False):
                C.competency_evidence_card(c, s)

