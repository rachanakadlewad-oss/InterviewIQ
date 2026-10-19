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
        left, right = st.columns([5, 1])
        with left:
            C.callout(na["tone"], "Next step", na["label"])
        right.button("Open", on_click=api.go, args=(na["page"],), key="next_open", type="primary")
    else:
        C.callout("success", "You are all caught up", "Nothing is waiting for you right now.")

    C.metric_grid([
        {"label": "Active jobs", "value": m["active_jobs"], "hint": "Jobs you have created"},
        {"label": "Total applicants", "value": m["total_applicants"], "hint": f"{m['awaiting_screening']} not scored yet"},
        {"label": "Awaiting review", "value": m["awaiting_review"], "hint": "Scored, no shortlist decision", "tone": "warning" if m["awaiting_review"] else "neutral"},
        {"label": "Shortlisted", "value": m["shortlisted"], "hint": f"{m['awaiting_scheduling']} still need a slot"},
        {"label": "Scheduled interviews", "value": m["scheduled"], "hint": f"{m['free_slots']} free calendar slots"},
        {"label": "Identity reviews", "value": m["pending_identity"], "hint": "Blocking interviews" if m["pending_identity"] else "None pending", "tone": "error" if m["pending_identity"] else "neutral"},
        {"label": "Completed interviews", "value": m["completed_interviews"], "hint": f"{m['interviews_in_progress']} in progress"},
        {"label": "Awaiting decision", "value": m["awaiting_decision"], "hint": "Reports you must decide", "tone": "warning" if m["awaiting_decision"] else "neutral"},
    ])

    a, b = st.columns([1, 1], gap="large")
    with a:
        C.section("Hiring pipeline", "Candidates who have reached each stage.")
        C.funnel(ov["funnel"])
    with b:
        C.section("Pending actions", "Ordered by what blocks candidates first.")
        if not ov["pending_actions"]:
            C.empty_state("Nothing pending", "Pending work will appear here.")
        for i, act in enumerate(ov["pending_actions"]):
            c1, c2 = st.columns([4, 1])
            with c1:
                C.badges(C.badge(act["page"], act["tone"], dot=False))
                st.caption(act["label"])
            c2.button("Open", key=f"act_{i}", on_click=api.go, args=(act["page"],))

    C.section("Jobs at a glance")
    C.table([("title", "Job", "strong"), ("applicants", "Applicants", "r"), ("scored", "Scored", "r"),
             ("shortlisted", "Shortlisted", "r"), ("completed", "Interviews done", "r")], ov["per_job"])
    C.callout("info", "How these numbers are counted",
              "All figures are read live from the database. 'Awaiting review' means scored but not yet shortlisted. "
              "'Scheduled' counts booked interview slots. Funnel stages are cumulative.")
