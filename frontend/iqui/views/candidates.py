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
    C.section("1. Upload resumes", "PDF, DOCX or TXT, up to 8 MB each. Scanned image-only PDFs cannot be read (no OCR).")
    files = st.file_uploader("Drop one or more resumes", accept_multiple_files=True, type=["pdf", "docx", "txt"], key=f"up_{job_id}")
    photos = []
    with st.expander("Optional: reference photos for identity verification"):
        st.caption("Name each photo like its resume (Priya_Nair.jpg). Photos embedded in a resume are used automatically when present. "
                   "The photo is deleted once the interview has been assessed.")
        photos = st.file_uploader("Reference photos", accept_multiple_files=True, type=["jpg", "jpeg", "png"], key=f"ph_{job_id}")
    if st.button("Upload and parse", type="primary", disabled=not files):
        pm = {Path(p.name).stem: p for p in photos or []}
        results = []
        bar = st.progress(0.0, text="Uploading...")
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
    C.section("2. Score and rank", "Runs the Recruitment Agent on every candidate that has not been scored yet.")
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    todo = [a for a in apps if a["status"] in ("PARSED", "SCORING_FAILED")]
    c1, c2 = st.columns([1, 3])
    clicked = c1.button(f"Score {len(todo)} resume(s)" if todo else "Everything is scored", type="primary", disabled=not todo)
    c2.caption("Scoring is retried a bounded number of times if the model returns invalid output; failures are listed below and can be re-run.")
    if clicked:
        with st.spinner("Recruitment Agent is scoring resumes..."):
            r = api.call("POST", f"/jobs/{job_id}/screen")
        if r:
            if r["scored"]:
                C.callout("success", f"Scored {len(r['scored'])} candidate(s)", "Ranking updated below.")
            for f in r["failed"]:
                C.callout("error", f"Application {f['application_id']} could not be scored", f["error"])


def list_section(job_id):
    C.section("3. Candidates", "Ranked by resume score (0-100). Select a candidate for details.")
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    if not apps:
        C.empty_state("No candidates yet", "Upload resumes above to get started.")
        return
    job = api.call("GET", f"/jobs/{job_id}") or {"title": "", "competencies": []}
    C.table([("rank", "Rank", "r"), ("name", "Candidate", "strong"), ("job", "Job"), ("score", "Resume score"), ("status", "Status"), ("src", "Scored by")],
            [{"rank": a["rank"] if a["rank"] is not None else "-", "name": a["name"] or f"Application #{a['application_id']}", "job": job["title"],
              "score": C.score_bar(a["resume_score"], 100) if a["resume_score"] is not None else "not scored",
              "status": C.status_badge(a["status"]), "src": C.source_badge(a["scoring_source"])} for a in apps],)
    pick = st.selectbox("Inspect candidate", [a["application_id"] for a in apps], key="cand_pick",
                        format_func=lambda i: next(f"{a['name'] or 'Application'} (#{i})" for a in apps if a["application_id"] == i))
    detail_view(pick, job, next(a for a in apps if a["application_id"] == pick))


def detail_view(app_id, job, row):
    rep = api.call("GET", f"/applications/{app_id}/report")
    if not rep:
        return
    C.badges(C.status_badge(row["status"]), C.source_badge(rep["resume"]["source"]))
    if row.get("scoring_error"):
        C.callout("error", "Scoring failed for this candidate", row["scoring_error"])
    t_profile, t_evidence = st.tabs(["Parsed profile", "Competency evidence"])
    with t_profile:
        p = rep["profile"]
        C.kv([("Name", p.get("name")), ("Email", p.get("email")), ("Phone", p.get("phone")),
              ("Experience (years)", p.get("experience_years") or "not stated")])
        if p.get("skills"):
            st.markdown("**Skills detected in the resume**")
            C.badges(*[C.badge(s, "neutral", dot=False) for s in p["skills"]])
        if p.get("education"):
            st.markdown("**Education**")
            for e in p["education"]:
                C.quote(e)
        if p.get("summary"):
            st.markdown("**Summary line from the resume**")
            C.quote(p["summary"])
        st.caption("Profile fields are extracted from the resume text with pattern matching (and refined by the LLM when configured). Missing fields are left blank, never guessed.")
    with t_evidence:
        scores = {s["competency_id"]: s for s in rep["resume"]["per_competency"]}
        if not scores:
            C.empty_state("Not scored yet", "Run scoring to see evidence for each competency.")
            return
        if rep["resume"]["source"] == "demo_rules":
            C.callout("warning", "Demo-rule scores", "Evidence lines were matched by keyword, not understood semantically.")
        for c in job["competencies"]:
            s = scores.get(c["id"])
            if not s:
                continue
            with st.expander(f"{c['name']}  -  {s['score']:.1f} / 10", expanded=False):
                C.badges(C.badge(f"weight {c['weight']}", "neutral", dot=False))
                st.markdown(s["justification"])
                if s["evidence"]:
                    for e in s["evidence"]:
                        C.quote(e)
                else:
                    C.callout("warning", "No resume evidence found for this competency", "It may be probed in the interview.")
