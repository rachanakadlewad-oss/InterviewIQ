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
    C.page_header("Jobs", "A job defines the competencies every candidate is screened and interviewed against.", "Recruiter workspace")
    tab_list, tab_new = st.tabs(["Your jobs", "Create a job"])
    with tab_list:
        jobs_view()
    with tab_new:
        create_view()


def jobs_view():
    ov = api.call("GET", "/overview") or {"per_job": []}
    if not ov["per_job"]:
        C.empty_state("No jobs yet", "Use the 'Create a job' tab, or load the sample job from the Overview page.")
        return
    selected = api.job_picker("Selected job")
    C.table([("job_id", "ID"), ("title", "Job", "strong"), ("applicants", "Applicants", "r"), ("scored", "Scored", "r"),
             ("shortlisted", "Shortlisted", "r")], ov["per_job"])
    if not selected:
        return
    job = api.call("GET", f"/jobs/{selected}")
    if not job:
        return
    C.section(job["title"], "Competencies and scoring weights")
    if job["description"]:
        C.quote(job["description"])
    tw = sum(c["weight"] for c in job["competencies"]) or 1
    C.table([("name", "Competency", "strong"), ("weight", "Weight"), ("share", "Share of resume score"), ("keywords", "Demo keywords")],
            [{"name": c["name"], "weight": c["weight"], "share": C.score_bar(c["weight"] / tw * 100, 100),
              "keywords": ", ".join(c.get("keywords", [])[:5]) or "-"} for c in job["competencies"]])
    for c in job["competencies"]:
        if c.get("rubric") or c.get("questions"):
            with st.expander(f"Rubric and opening question - {c['name']}"):
                for lvl, txt in sorted(c.get("rubric", {}).items()):
                    st.markdown(f"**Level {lvl}:** {txt}")
                for q in c.get("questions", []):
                    st.markdown(f"*Opening question:* {q}")


def create_view():
    C.callout("info", "Describe the role in plain fields",
              "Add one row per competency. The rubric levels tell the AI what weak, working and strong evidence looks like - "
              "clear rubrics give fairer, more explainable scores.")
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
                api.flash("success", "Job created", f"'{res['title']}' is ready. Next, upload resumes on the Candidates page.")
                st.rerun()
    c1, c2 = st.columns(2)
    with c1:
        with st.expander("Advanced: import a job from JSON"):
            txt = st.text_area("Job JSON", value=SAMPLE.read_text() if SAMPLE.exists() else "{}", height=180, key="json_import")
            if st.button("Import JSON"):
                try:
                    res = api.call("POST", "/jobs", json=json.loads(txt))
                    if res:
                        api.select_job_next_run(res["id"])
                        api.flash("success", "Job imported", res["title"])
                        st.rerun()
                except json.JSONDecodeError as e:
                    C.callout("error", "Invalid JSON", str(e))
    with c2:
        with st.expander("Load the sample job and mock calendar"):
            st.caption("Creates 'Backend Python Engineer' (10 competencies) and loads the sample interview slots.")
            if st.button("Load sample"):
                r = api.call("POST", "/jobs/load-sample")
                if r:
                    api.select_job_next_run(r["id"])
                    api.flash("success", "Sample loaded", f"Job #{r['id']} created; {r['slots_added']} calendar slots added.")
                    st.rerun()
