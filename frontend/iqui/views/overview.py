import streamlit as st

from .. import api, components as C, helpers as H

TASK_STATUS_MAP = {
    "identity": ("Identity Verification Needed", "error"),
    "failed_assessment": ("Needs Review / Retry", "error"),
    "screen": ("Ready to Screen", "warning"),
    "shortlist": ("Ready to Shortlist", "warning"),
    "schedule": ("Ready to Schedule", "warning"),
    "decide": ("Awaiting Final Decision", "info"),
    "live": ("Interview in Progress", "info"),
    "upload": ("Add Resumes", "info"),
    "create_job": ("Create Job", "info"),
}


def render():
    C.page_header(
        "Dashboard",
        "Overview of your active recruitment pipeline, hiring metrics, and pending actions.",
        "Recruiter workspace",
    )

    ov = api.call("GET", "/overview")
    if ov is None:
        return

    m = ov.get("metrics") or {}

    # Empty state when no jobs exist
    if m.get("active_jobs", 0) == 0:
        C.empty_state(
            "Welcome to InterviewIQ",
            "Get started by creating your first job opening, or load sample data to explore the platform.",
            icon="👋"
        )
        c1, c2, _ = st.columns([1.5, 2, 2.5])
        with c1:
            st.button("Create a Job", on_click=api.go, args=("Jobs",), type="primary", use_container_width=True)
        with c2:
            if st.button("Load Sample Job & Calendar", use_container_width=True):
                r = api.call("POST", "/jobs/load-sample")
                if r:
                    api.select_job_next_run(r["id"])
                    api.flash("success", "Sample job loaded", "Next: upload resumes on the Candidates page.")
                    st.rerun()
        return

    # 1. Four essential metric cards
    C.metric_grid([
        {"label": "Active Jobs", "value": m.get("active_jobs", 0), "hint": "Open positions"},
        {"label": "Total Candidates", "value": m.get("total_applicants", 0), "hint": "In hiring pipeline"},
        {"label": "Scheduled Interviews", "value": m.get("scheduled", 0), "hint": "Confirmed sessions"},
        {
            "label": "Pending Decisions",
            "value": m.get("awaiting_decision", 0),
            "hint": "Awaiting final review",
            "tone": "warning" if m.get("awaiting_decision", 0) > 0 else "neutral",
        },
    ], cols=4)

    # 2. Needs Attention - Clear, actionable recruiter tasks
    pending_actions = ov.get("pending_actions") or []
    C.section("Needs Attention", "Tasks requiring your review to keep candidates moving forward.")

    if not pending_actions:
        C.empty_state(
            "All Caught Up",
            "No tasks currently require your attention. All candidates are progressing smoothly.",
            icon="✅",
        )
    else:
        with st.container(border=True):
            for i, act in enumerate(pending_actions):
                tgt = "Interviews" if act.get("key") == "schedule" else api.PAGE_MAP.get(act.get("page", ""), act.get("page", ""))
                status_text, status_tone = TASK_STATUS_MAP.get(
                    act.get("key"),
                    (act.get("tone", "neutral").replace("_", " ").title(), act.get("tone", "neutral"))
                )

                c_left, c_right = st.columns([4.2, 1.2], vertical_alignment="center")
                with c_left:
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;min-width:0;padding:0.2rem 0;">'
                        f'{C.badge(status_text, status_tone)}'
                        f'<span style="color:var(--text);font-size:0.9rem;font-weight:550;line-height:1.4;">'
                        f'{C.esc(act.get("label", ""))}'
                        f'</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                with c_right:
                    btn_type = "primary" if i == 0 else "secondary"
                    st.button(
                        f"Open {tgt}",
                        key=f"na_act_{i}",
                        on_click=api.go,
                        args=(tgt,),
                        type=btn_type,
                        use_container_width=True,
                    )
                if i < len(pending_actions) - 1:
                    st.markdown('<div style="border-bottom:1px solid rgba(30,45,74,0.6);margin:0.25rem 0;"></div>', unsafe_allow_html=True)

    # 3. Hiring Pipeline Progression
    C.section("Hiring Pipeline", "Candidate progression through each stage of the hiring process.")
    funnel_map = {f.get("stage"): f.get("count", 0) for f in ov.get("funnel", [])}
    pipeline_stages = [
        ("Applied", funnel_map.get("Uploaded", m.get("total_applicants", 0))),
        ("Screened", funnel_map.get("Scored", 0)),
        ("Shortlisted", funnel_map.get("Shortlisted", m.get("shortlisted", 0))),
        ("Interviewed", funnel_map.get("Interviewed", m.get("completed_interviews", 0))),
        ("Decided", funnel_map.get("Decided", m.get("decided", 0))),
    ]
    C.pipeline_progression(pipeline_stages)

    # 4. Active Job Openings Table
    C.section("Active Job Openings", "Overview of current candidate counts and interview progress per job.")
    job_columns = [
        ("title", "Job Title", "strong"),
        ("applicants", "Total Candidates", "r"),
        ("shortlisted", "Shortlisted", "r"),
        ("completed", "Interviews Completed", "r"),
    ]
    C.table(job_columns, ov.get("per_job", []), empty="No active job openings found.")
