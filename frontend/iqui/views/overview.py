import streamlit as st

from .. import api, components as C, helpers as H


def render():
    C.page_header("Overview", "Where every candidate stands and what needs your attention next.", "Recruiter workspace")
    ov = api.call("GET", "/overview")
    if ov is None:
        return
    m, na = ov["metrics"], ov["next_action"]

    if m["active_jobs"] == 0:
        C.empty_state("Welcome to InterviewIQ", "Start by creating a job, then upload resumes to screen candidates.")
        c1, c2 = st.columns([1, 1])
        c1.button("Create a job", on_click=api.go, args=("Jobs",), type="primary")
        if c2.button("Load the sample job and calendar"):
            r = api.call("POST", "/jobs/load-sample")
            if r:
                api.select_job_next_run(r["id"])
                api.flash("success", "Sample job and calendar loaded", "Next: upload resumes on the Candidates page.")
                st.rerun()
        return

    if na:
        left, right = st.columns([4.8, 1.2])
        with left:
            C.callout(na["tone"], "Next Recommended Action", na["label"])
        with right:
            st.button(f"Go to {na['page']}", on_click=api.go, args=(na["page"],), key="next_open", type="primary", use_container_width=True)
    else:
        C.callout("success", "You are all caught up", "No pipeline blocks require immediate recruiter attention.")

    C.metric_grid([
        {"label": "Active jobs", "value": m["active_jobs"], "hint": "Positions created"},
        {"label": "Total applicants", "value": m["total_applicants"], "hint": f"{m['awaiting_screening']} not scored yet"},
        {"label": "Awaiting review", "value": m["awaiting_review"], "hint": "Scored, pending shortlist", "tone": "warning" if m["awaiting_review"] else "neutral"},
        {"label": "Shortlisted", "value": m["shortlisted"], "hint": f"{m['awaiting_scheduling']} need slots"},
        {"label": "Scheduled interviews", "value": m["scheduled"], "hint": f"{m['free_slots']} free calendar slots"},
        {"label": "Identity reviews", "value": m["pending_identity"], "hint": "Blocking interviews" if m["pending_identity"] else "All cleared", "tone": "error" if m["pending_identity"] else "neutral"},
        {"label": "Completed interviews", "value": m["completed_interviews"], "hint": f"{m['interviews_in_progress']} in progress"},
        {"label": "Awaiting decision", "value": m["awaiting_decision"], "hint": "Reports to decide", "tone": "warning" if m["awaiting_decision"] else "neutral"},
    ])

    a, b = st.columns([1, 1], gap="medium")
    with a:
        C.section("Hiring Pipeline", "Cumulative progression across evaluation stages.")
        with st.container(border=True):
            C.funnel(ov["funnel"])
    with b:
        C.section("Pending Recruiter Actions", "Action items blocking candidate progression.")
        with st.container(border=True):
            if not ov["pending_actions"]:
                C.empty_state("Nothing pending", "All candidates are progressing smoothly.", icon="✅")
            else:
                for i, act in enumerate(ov["pending_actions"]):
                    c1, c2 = st.columns([3.8, 1.2])
                    with c1:
                        C.badges(C.badge(act["page"], act["tone"], dot=False))
                        st.caption(act["label"])
                    with c2:
                        st.button("Open", key=f"act_{i}", on_click=api.go, args=(act["page"],), use_container_width=True)

    C.section("Job Openings Summary", "Live pipeline metrics per job role.")
    C.table([("title", "Job Title", "strong"), ("applicants", "Applicants", "r"), ("scored", "Scored", "r"),
             ("shortlisted", "Shortlisted", "r"), ("completed", "Interviews Done", "r")], ov["per_job"])
    C.callout("info", "How figures are calculated",
              "All figures are read live from the database. 'Awaiting review' counts scored candidates not yet shortlisted. "
              "'Scheduled' counts booked interview slots. Pipeline funnel stages are cumulative.")

