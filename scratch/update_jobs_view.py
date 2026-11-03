with open('frontend/iqui/views/jobs.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_jobs_view = '''def jobs_view():
    ov = api.call("GET", "/overview") or {"per_job": []}
    if not ov["per_job"]:
        C.empty_state("No jobs yet", "Use the 'Create a Job' tab, or load the sample job from the Dashboard.", icon="💼")
        return
    selected = api.job_picker("Selected job")
    C.table([("job_id", "ID"), ("title", "Job Title", "strong"), ("applicants", "Applicants", "r"), ("scored", "Scored", "r"),
             ("shortlisted", "Shortlisted", "r")], ov["per_job"])
    if not selected:
        return
    job = api.call("GET", f"/jobs/{selected}")
    if not job:
        return
    with st.container(border=True):
        C.section(job["title"], "Configured role competencies and evaluation weights")
        if job["description"]:
            C.quote(job["description"])
        tw = sum(c["weight"] for c in job["competencies"]) or 1
        C.table([("name", "Competency", "strong"), ("weight", "Weight"), ("share", "Share of Resume Score"), ("keywords", "Demo Keywords")],
                [{"name": c["name"], "weight": c["weight"], "share": C.score_bar(c["weight"] / tw * 100, 100),
                  "keywords": ", ".join(c.get("keywords", [])[:5]) or "-"} for c in job["competencies"]])

        with st.expander("Advanced: Competency Rubrics & Seed Questions"):
            for c in job["competencies"]:
                st.markdown(f"**{c['name']}** (Weight: {c.get('weight', 1.0)})")
                if c.get("rubric"):
                    for lvl, txt in sorted(c.get("rubric", {}).items()):
                        st.markdown(f"• *Level {lvl}:* {txt}")
                for q in c.get("questions", []):
                    st.caption(f"Opening Seed: {q}")
                st.markdown("---")'''

new_jobs_view = '''def jobs_view():
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
                st.markdown("---")'''

assert old_jobs_view in c, 'old_jobs_view not found'
c = c.replace(old_jobs_view, new_jobs_view)
with open('frontend/iqui/views/jobs.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('Successfully updated frontend/iqui/views/jobs.py')
