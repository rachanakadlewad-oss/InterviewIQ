"""Recruiter Jobs Management View.
Provides job listings, status management (Active/Inactive), editing,
safe deletion, and a simplified, intuitive Create Job form."""
import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header(
        "Job Positions",
        "Define job openings, configure role requirements, and manage active hiring listings.",
        "Recruiter workspace"
    )

    tab_list, tab_create = st.tabs(["📋 All Job Positions", "➕ Create New Job"])

    with tab_list:
        jobs_directory_view()

    with tab_create:
        create_job_view()


def jobs_directory_view():
    jobs = api.call("GET", "/jobs") or []

    if not jobs:
        C.empty_state(
            "No Job Openings Found",
            "You haven't created any job openings yet. Switch to the 'Create New Job' tab to post your first position.",
            icon="💼"
        )
        return

    st.markdown(
        f'<div style="margin-bottom:0.9rem;display:flex;align-items:center;justify-content:space-between;">'
        f'<span class="iq-badge info" style="font-size:0.85rem;padding:0.25rem 0.75rem;">'
        f'<b>{len(jobs)}</b> Total Positions Configured'
        f'</span>'
        f'<span style="font-size:0.82rem;color:var(--muted);">All changes update database records in real-time</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    for job in jobs:
        jid = job["id"]
        title = job.get("title", f"Job #{jid}")
        company = job.get("company", "TechCorp")
        location = job.get("location", "Remote")
        exp_level = job.get("experience_level", "Mid-level")
        emp_type = job.get("employment_type", "Full-time")
        status = job.get("status", "ACTIVE")
        is_active = (status == "ACTIVE")
        applicants_count = job.get("applicants", 0)
        shortlisted_count = job.get("shortlisted", 0)
        created_date = job.get("created_at") or "-"
        if "T" in created_date:
            created_date = created_date.split("T")[0]

        status_badge = C.badge("Active", "success", dot=True) if is_active else C.badge("Inactive", "neutral", dot=False)

        with st.container(border=True):
            col_info, col_metrics, col_actions = st.columns([3.2, 1.8, 1.8], vertical_alignment="center")

            with col_info:
                st.markdown(
                    f'''<div>
                        <div style="display:flex;align-items:center;gap:0.65rem;margin-bottom:0.25rem;">
                            <span style="font-size:1.18rem;font-weight:750;color:var(--text);">{C.esc(title)}</span>
                            {status_badge}
                        </div>
                        <div style="font-size:0.88rem;color:var(--text2);margin-bottom:0.2rem;">
                            <b style="color:var(--text);">{C.esc(company)}</b> &nbsp;·&nbsp; {C.esc(location)} &nbsp;·&nbsp; {C.esc(emp_type)} &nbsp;·&nbsp; {C.esc(exp_level)}
                        </div>
                        <div style="font-size:0.78rem;color:var(--muted);">
                            Created: {C.esc(created_date)} &nbsp;·&nbsp; Position ID: #{jid}
                        </div>
                    </div>''',
                    unsafe_allow_html=True
                )

            with col_metrics:
                st.markdown(
                    f'''<div style="display:flex;gap:1.2rem;align-items:center;">
                        <div>
                            <div style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;font-weight:700;">Applicants</div>
                            <div style="font-size:1.45rem;font-weight:800;color:var(--text);">{applicants_count}</div>
                        </div>
                        <div style="border-left:1px solid var(--border);padding-left:1.2rem;">
                            <div style="font-size:0.72rem;color:var(--muted);text-transform:uppercase;font-weight:700;">Shortlisted</div>
                            <div style="font-size:1.45rem;font-weight:800;color:var(--success);">{shortlisted_count}</div>
                        </div>
                    </div>''',
                    unsafe_allow_html=True
                )

            with col_actions:
                a1, a2 = st.columns(2)
                with a1:
                    toggle_btn_label = "Deactivate" if is_active else "Activate"
                    if st.button(toggle_btn_label, key=f"tog_{jid}", use_container_width=True):
                        api.call("POST", f"/jobs/{jid}/toggle-status")
                        api.flash("success", "Job Status Updated", f"Job #{jid} is now {'Inactive' if is_active else 'Active'}.")
                        st.rerun()
                with a2:
                    if st.button("Delete", key=f"del_{jid}", type="secondary", use_container_width=True):
                        st.session_state[f"confirm_delete_{jid}"] = True

            # Confirmation prompt for job deletion
            if st.session_state.get(f"confirm_delete_{jid}"):
                C.callout(
                    "warning",
                    f"Confirm Deletion of Job #{jid}",
                    f"Are you sure you want to delete '{title}'? This will remove the position and associated test records."
                )
                c_conf1, c_conf2, _ = st.columns([1.5, 1.5, 3])
                with c_conf1:
                    if st.button("Yes, Delete Job", key=f"btn_yes_del_{jid}", type="primary", use_container_width=True):
                        api.call("DELETE", f"/jobs/{jid}")
                        st.session_state.pop(f"confirm_delete_{jid}", None)
                        api.flash("success", "Job Deleted", f"Successfully deleted job position #{jid}.")
                        st.rerun()
                with c_conf2:
                    if st.button("Cancel", key=f"btn_no_del_{jid}", use_container_width=True):
                        st.session_state.pop(f"confirm_delete_{jid}", None)
                        st.rerun()

            # Expandable View / Edit panel
            with st.expander(f"⚙️ View Details & Edit Job #{jid}"):
                with st.form(f"edit_form_{jid}"):
                    st.markdown("#### Edit Job Opening")
                    e_title = st.text_input("Job Title", value=job.get("title", ""))
                    e_company = st.text_input("Company Name", value=job.get("company", "TechCorp"))
                    e_desc = st.text_area("Job Description", value=job.get("description", "") or "", height=90)
                    
                    c_loc, c_type, c_exp = st.columns(3)
                    with c_loc:
                        e_location = st.text_input("Location", value=job.get("location", "Remote"))
                    with c_type:
                        e_emp_type = st.selectbox(
                            "Employment Type",
                            ["Full-time", "Part-time", "Contract", "Internship"],
                            index=["Full-time", "Part-time", "Contract", "Internship"].index(emp_type) if emp_type in ["Full-time", "Part-time", "Contract", "Internship"] else 0
                        )
                    with c_exp:
                        e_exp_level = st.selectbox(
                            "Experience Level",
                            ["Entry-level", "Mid-level", "Senior", "Lead / Principal"],
                            index=["Entry-level", "Mid-level", "Senior", "Lead / Principal"].index(exp_level) if exp_level in ["Entry-level", "Mid-level", "Senior", "Lead / Principal"] else 1
                        )

                    c_req, c_pref = st.columns(2)
                    with c_req:
                        e_req = st.text_input("Required Skills (comma-separated)", value=job.get("required_skills", ""))
                    with c_pref:
                        e_pref = st.text_input("Preferred Skills (comma-separated)", value=job.get("preferred_skills", ""))

                    e_status = st.selectbox("Status", ["ACTIVE", "INACTIVE"], index=0 if is_active else 1)

                    if st.form_submit_button("Save Changes to Database", type="primary"):
                        if len(e_title.strip()) < 2:
                            C.callout("error", "Validation Error", "Job title must be at least 2 characters long.")
                        else:
                            api.call("PATCH", f"/jobs/{jid}", json={
                                "title": e_title.strip(),
                                "company": e_company.strip(),
                                "description": e_desc.strip(),
                                "location": e_location.strip(),
                                "employment_type": e_emp_type,
                                "experience_level": e_exp_level,
                                "required_skills": e_req.strip(),
                                "preferred_skills": e_pref.strip(),
                                "status": e_status
                            })
                            api.flash("success", "Job Position Updated", f"Successfully saved changes for '{e_title.strip()}'.")
                            st.rerun()


def create_job_view():
    C.section(
        "Create a New Job Opening",
        "Fill in the role information and requirements. All candidates will be semantically scored against these criteria."
    )

    with st.container(border=True):
        with st.form("create_new_job_form"):
            st.markdown("#### 1. Basic Information")
            c_t, c_c = st.columns([2, 1.5])
            with c_t:
                title = st.text_input("Job Title *", placeholder="e.g. Senior Backend Python Developer")
            with c_c:
                company = st.text_input("Company Name *", value="TechCorp", placeholder="e.g. Acme Tech Solutions")

            desc = st.text_area(
                "Job Description & Responsibilities *",
                placeholder="Describe role responsibilities, team environment, and day-to-day deliverables...",
                height=110
            )

            c_l, c_et, c_el = st.columns(3)
            with c_l:
                location = st.text_input("Location", value="Remote", placeholder="e.g. Remote, New York, NY, Hybrid")
            with c_et:
                employment_type = st.selectbox(
                    "Employment Type",
                    ["Full-time", "Part-time", "Contract", "Internship"],
                    index=0
                )
            with c_el:
                experience_level = st.selectbox(
                    "Experience Level",
                    ["Entry-level", "Mid-level", "Senior", "Lead / Principal"],
                    index=1
                )

            st.markdown("#### 2. Candidate Requirements")
            c_req, c_pref = st.columns(2)
            with c_req:
                required_skills = st.text_input(
                    "Required Skills (comma-separated) *",
                    placeholder="e.g. Python, FastAPI, SQL, REST APIs"
                )
            with c_pref:
                preferred_skills = st.text_input(
                    "Preferred Skills (comma-separated)",
                    placeholder="e.g. Docker, Kubernetes, AWS, Redis"
                )

            c_min_exp, c_edu = st.columns(2)
            with c_min_exp:
                min_experience = st.number_input("Minimum Experience (Years)", min_value=0.0, max_value=25.0, value=3.0, step=0.5)
            with c_edu:
                education = st.text_input("Educational Requirements (Optional)", placeholder="e.g. B.S. in Computer Science or equivalent")

            st.markdown("#### 3. Listing Status")
            status_choice = st.radio(
                "Initial Status",
                ["Active (Accepting Applications)", "Inactive (Draft / Hidden)"],
                horizontal=True
            )
            initial_status = "ACTIVE" if "Active" in status_choice else "INACTIVE"

            st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
            submit = st.form_submit_button("🚀 Create Job Opening", type="primary", use_container_width=True)

        if submit:
            errors = []
            if len((title or "").strip()) < 2:
                errors.append("Job Title must be at least 2 characters long.")
            if len((desc or "").strip()) < 5:
                errors.append("Please provide a meaningful Job Description.")
            if len((required_skills or "").strip()) < 2:
                errors.append("Please specify at least one required skill.")

            if errors:
                C.callout("error", "Validation Error", " ".join(errors))
            else:
                with st.spinner("Creating job opening in database..."):
                    res = api.call("POST", "/jobs", json={
                        "title": title.strip(),
                        "company": company.strip() if company else "TechCorp",
                        "description": desc.strip(),
                        "location": location.strip() if location else "Remote",
                        "employment_type": employment_type,
                        "experience_level": experience_level,
                        "required_skills": required_skills.strip(),
                        "preferred_skills": preferred_skills.strip() if preferred_skills else "",
                        "status": initial_status
                    })
                    if res:
                        api.flash("success", "Job Created Successfully", f"Job opening '{title.strip()}' has been posted and saved to the database.")
                        st.rerun()
