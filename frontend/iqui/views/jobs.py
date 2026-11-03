import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .. import api, components as C, helpers as H

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_jd.json"
EDITOR_COLUMNS = {
    "name": st.column_config.TextColumn("Competency", required=True, help="e.g. Python Programming"),
    "weight": st.column_config.NumberColumn("Weight", min_value=0.1, max_value=10.0, step=0.1, default=1.0, help="Relative importance in scoring"),
    "description": st.column_config.TextColumn("What it means"),
    "keywords": st.column_config.TextColumn("Keywords (comma separated)", help="Used only by deterministic DEMO scoring"),
    "question": st.column_config.TextColumn("Opening question", help="Seed question the interviewer can start from"),
    "rubric_basic": st.column_config.TextColumn("Level 1 looks like"),
    "rubric_working": st.column_config.TextColumn("Level 3 looks like"),
    "rubric_strong": st.column_config.TextColumn("Level 5 looks like"),
}


def _records(df: pd.DataFrame) -> list:
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in df.to_dict("records")]


def render():
    C.page_header(
        "Jobs",
        "A job defines the competencies every candidate is screened and interviewed against.",
        "Recruiter workspace"
    )
    tab_list, tab_new = st.tabs(["Active Jobs", "Create a Job"])
    with tab_list:
        jobs_view()
    with tab_new:
        create_view()


def jobs_view():
    ov = api.call("GET", "/overview") or {"per_job": []}
    if not ov["per_job"]:
        C.empty_state("No jobs yet", "Use the 'Create a Job' tab, or load the sample job from the Dashboard.", icon="💼")
        return

    # Job selection dropdown with immediate state reflection
    selected = api.job_picker("Active Job Selection")
    if not selected:
        return

    job = api.call("GET", f"/jobs/{selected}")
    if not job:
        return

    # Active Job Summary Card
    with st.container(border=True):
        col_t, col_act = st.columns([3, 1])
        with col_t:
            C.badges(
                C.badge(f"Active Job #{selected}", "info", dot=True),
                C.badge(f"{len(job.get('competencies', []))} Competencies", "neutral", dot=False)
            )
            st.markdown(f"### {job['title']}")
            if job.get("description"):
                C.quote(job["description"])
        with col_act:
            st.caption("Active in workspace")

        # Edit Job Title / Description inline to correct typos or update details
        with st.expander("Edit Job Title or Description", expanded=False):
            with st.form(f"edit_job_{selected}"):
                edit_title = st.text_input("Job Title", value=job.get("title", ""))
                edit_desc = st.text_area("Job Description", value=job.get("description", "") or "", height=80)
                if st.form_submit_button("Save Changes", type="primary"):
                    if len((edit_title or "").strip()) < 2:
                        C.callout("error", "Invalid Title", "Job title must be at least 2 characters.")
                    else:
                        res = api.call("PATCH", f"/jobs/{selected}", json={"title": edit_title.strip(), "description": edit_desc.strip()})
                        if res:
                            api.flash("success", "Job Updated", f"Successfully updated job to '{res['title']}'.")
                            st.rerun()

    # Overview table showing all configured jobs with clear active marker
    st.markdown("#### All Configured Jobs")
    job_rows = []
    for pj in ov["per_job"]:
        is_active = (pj["job_id"] == selected)
        job_rows.append({
            "status": C.badge("Active", "info", dot=True) if is_active else C.badge("Switch", "neutral", dot=False),
            "job_id": str(pj["job_id"]),
            "title": f"**{pj['title']}**" if is_active else pj["title"],
            "applicants": pj.get("applicants", 0),
            "scored": pj.get("scored", 0),
            "shortlisted": pj.get("shortlisted", 0),
        })

    C.table([
        ("status", "Status"),
        ("job_id", "ID"),
        ("title", "Job Title"),
        ("applicants", "Applicants", "r"),
        ("scored", "Scored", "r"),
        ("shortlisted", "Shortlisted", "r")
    ], job_rows)

    # Competency Rubrics Table for the selected job
    with st.container(border=True):
        C.section(f"Competencies & Evaluation Weights: {job['title']}", "Configured rubric dimensions and evaluation share.")
        tw = sum(c["weight"] for c in job["competencies"]) or 1
        C.table(
            [("name", "Competency", "strong"), ("weight", "Weight"), ("share", "Share of Resume Score"), ("keywords", "Demo Keywords")],
            [{"name": c["name"], "weight": c["weight"], "share": C.score_bar(c["weight"] / tw * 100, 100),
              "keywords": ", ".join(c.get("keywords", [])[:5]) or "-"} for c in job["competencies"]]
        )

        with st.expander("Advanced: Competency Rubrics & Seed Questions"):
            for c in job["competencies"]:
                st.markdown(f"**{c['name']}** (Weight: {c.get('weight', 1.0)})")
                if c.get("rubric"):
                    for lvl, txt in sorted(c.get("rubric", {}).items()):
                        st.markdown(f"• *Level {lvl}:* {txt}")
                for q in c.get("questions", []):
                    st.caption(f"Opening Seed: {q}")
                st.markdown("---")


def create_view():
    C.callout("info", "Define Competency Rubrics",
              "Add one row per competency. Clear rubric levels give fairer, more explainable scoring across both resume evaluation and the spoken interview.")
    with st.form("create_job"):
        title = st.text_input("Job title", placeholder="e.g. Backend Python Engineer")
        desc = st.text_area("Job description", placeholder="Responsibilities, seniority, tech stack...", height=110)
        st.markdown("**Competencies**")
        starter = pd.DataFrame([{"name": "", "weight": 1.0, "description": "", "keywords": "", "question": "",
                                 "rubric_basic": "", "rubric_working": "", "rubric_strong": ""}])
        edited = st.data_editor(starter, column_config=EDITOR_COLUMNS, num_rows="dynamic", hide_index=True, use_container_width=True, key="comp_editor")
        submit = st.form_submit_button("Create job", type="primary")
    if submit:
        errors = []
        if len((title or "").strip()) < 2:
            errors.append("Job title is required (at least 2 characters).")
        clean, comp_errors = H.competency_rows_valid(_records(edited))
        errors += comp_errors
        if errors:
            C.callout("error", "Please fix the following", " ".join(errors))
        else:
            res = api.call("POST", "/jobs", json={"title": title.strip(), "description": desc.strip(), "competencies": clean})
            if res:
                api.select_job_next_run(res["id"])
                api.flash("success", "Job created", f"'{res['title']}' is ready. Next: upload resumes on the Candidates page.")
                st.rerun()

    with st.expander("Advanced: Import Job from JSON Specification"):
        txt = st.text_area("Job JSON", value=SAMPLE.read_text() if SAMPLE.exists() else "{}", height=180, key="json_import")
        if st.button("Import JSON"):
            try:
                res = api.call("POST", "/jobs", json=json.loads(txt))
                if res:
                    api.select_job_next_run(res["id"])
                    api.flash("success", "Job imported", f"'{res['title']}' loaded.")
                    st.rerun()
            except Exception as e:
                C.callout("error", "Invalid JSON", str(e))
