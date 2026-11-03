import json
from pathlib import Path

import pandas as pd
import streamlit as st

from .. import api, components as C, helpers as H

SAMPLE = Path(__file__).resolve().parents[3] / "data" / "sample" / "sample_jd.json"
EDITOR_COLUMNS = {
    "name": st.column_config.TextColumn("Competency", required=True, help="e.g. Python Programming, System Design"),
    "weight": st.column_config.NumberColumn("Weight", min_value=0.1, max_value=10.0, step=0.1, default=1.0, help="Relative evaluation weight (e.g. 1.0 = standard, 2.0 = high priority)"),
    "description": st.column_config.TextColumn("Skill Description", help="Brief summary of what this competency measures"),
    "keywords": st.column_config.TextColumn("Target Keywords", help="Key technologies or terms to look for (comma-separated)"),
    "question": st.column_config.TextColumn("Opening Question", help="Suggested opening question for the interview"),
    "rubric_basic": st.column_config.TextColumn("Level 1 (Basic)", help="Expectations for a developing candidate"),
    "rubric_working": st.column_config.TextColumn("Level 3 (Proficient)", help="Expectations for a solid, competent hire"),
    "rubric_strong": st.column_config.TextColumn("Level 5 (Advanced)", help="Expectations for an exceptional hire"),
}


def _records(df: pd.DataFrame) -> list:
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in df.to_dict("records")]


def render():
    C.page_header(
        "Jobs",
        "Define and manage job positions, evaluation competencies, and scoring rubrics.",
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
        C.empty_state("No jobs yet", "Create your first job opening, or load the sample job from the Dashboard.", icon="💼")
        return

    # Job selection dropdown
    selected = api.job_picker("Selected Job")
    if not selected:
        return

    job = api.call("GET", f"/jobs/{selected}")
    if not job:
        return

    # 1. Selected Job Profile Card
    with st.container(border=True):
        col_t, col_act = st.columns([3.5, 1])
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

        # Edit Job Title / Description inline
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

    # 2. Competency Rubrics Table for the selected job
    with st.container(border=True):
        C.section(f"Evaluation Competencies: {job['title']}", "Core competencies and scoring weight distribution for this position.")
        tw = sum(c["weight"] for c in job["competencies"]) or 1
        C.table(
            [("name", "Competency", "strong"), ("weight", "Weight"), ("share", "Share of Evaluation"), ("keywords", "Target Keywords")],
            [{"name": c["name"], "weight": f"{c['weight']:.1f}x", "share": C.score_bar(c["weight"] / tw * 100, 100),
              "keywords": ", ".join(c.get("keywords", [])[:5]) or "-"} for c in job["competencies"]]
        )

        with st.expander("Detailed Rubric Criteria & Seed Questions"):
            for c in job["competencies"]:
                st.markdown(f"**{c['name']}** (Weight: {c.get('weight', 1.0)})")
                if c.get("rubric"):
                    for lvl, txt in sorted(c.get("rubric", {}).items()):
                        st.markdown(f"• *Level {lvl}:* {txt}")
                for q in c.get("questions", []):
                    st.caption(f"Suggested Opening Question: {q}")
                st.markdown("---")

    # 3. Overview directory table showing all configured jobs
    C.section("All Job Positions", "Quickly compare candidate volumes across all positions in your workspace.")
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
        ("applicants", "Total Candidates", "r"),
        ("scored", "Screened", "r"),
        ("shortlisted", "Shortlisted", "r")
    ], job_rows)


def create_view():
    C.callout(
        "info",
        "Define Role Competencies",
        "Add one row per competency. Well-defined criteria ensure consistent, fair scoring across both resume screening and the live interview."
    )
    with st.form("create_job"):
        title = st.text_input("Job Title", placeholder="e.g. Senior Backend Engineer")
        desc = st.text_area("Job Description & Requirements", placeholder="Role responsibilities, seniority level, tech stack...", height=110)
        st.markdown("**Role Competencies & Scoring Weights**")
        starter = pd.DataFrame([{"name": "", "weight": 1.0, "description": "", "keywords": "", "question": "",
                                 "rubric_basic": "", "rubric_working": "", "rubric_strong": ""}])
        edited = st.data_editor(starter, column_config=EDITOR_COLUMNS, num_rows="dynamic", hide_index=True, use_container_width=True, key="comp_editor")
        submit = st.form_submit_button("Create Job Position", type="primary")
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

    with st.expander("Import Job from JSON (Advanced)"):
        st.caption("Upload or paste a standardized JSON job specification.")
        txt = st.text_area("Job JSON Specification", value=SAMPLE.read_text() if SAMPLE.exists() else "{}", height=160, key="json_import")
        if st.button("Import JSON", key="btn_import_json"):
            try:
                res = api.call("POST", "/jobs", json=json.loads(txt))
                if res:
                    api.select_job_next_run(res["id"])
                    api.flash("success", "Job imported", f"'{res['title']}' loaded.")
                    st.rerun()
            except Exception as e:
                C.callout("error", "Invalid JSON", str(e))
