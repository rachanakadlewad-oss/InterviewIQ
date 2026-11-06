"""Recruiter Dashboard & Analytics View.
Provides high-contrast metrics, pipeline analytics, status distribution charts,
and recent applications calculated strictly from database records."""
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
        "Recruitment Dashboard",
        "Real-time pipeline analytics, candidate status distribution, and actionable recruitment tasks.",
        "Recruiter workspace",
    )

    ov = api.call("GET", "/overview")
    if ov is None:
        return

    m = ov.get("metrics") or {}
    total_jobs = m.get("total_jobs", len(ov.get("per_job", [])))

    # Empty state when no jobs exist
    if total_jobs == 0:
        C.empty_state(
            "Welcome to InterviewIQ",
            "Get started by creating your first job opening, or explore with a sample position.",
            icon="💼"
        )
        c1, c2, _ = st.columns([1.5, 2, 2.5])
        with c1:
            st.button("Create a Job Opening", on_click=api.go, args=("Jobs",), type="primary", use_container_width=True)
        with c2:
            if st.button("Load Sample Job & Calendar", use_container_width=True):
                r = api.call("POST", "/jobs/load-sample")
                if r:
                    api.select_job_next_run(r["id"])
                    api.flash("success", "Sample job loaded", "Next: upload resumes on the Candidates page.")
                    st.rerun()
        return

    # 1. Six Essential Metric Cards (Master Prompt Part 3)
    # - Total Jobs, Active Jobs, Total Applications, Shortlisted Candidates, Rejected Candidates, Pending Applications
    st.markdown(
        f'''<div class="iq-grid-6">
            <div class="iq-metric">
                <div class="l">Total Jobs</div>
                <div class="v">{total_jobs}</div>
                <div class="h">Configured roles</div>
            </div>
            <div class="iq-metric">
                <div class="l">Active Jobs</div>
                <div class="v">{m.get("active_jobs", 0)}</div>
                <div class="h">Accepting applicants</div>
            </div>
            <div class="iq-metric">
                <div class="l">Total Applications</div>
                <div class="v">{m.get("total_applicants", 0)}</div>
                <div class="h">Candidate submissions</div>
            </div>
            <div class="iq-metric tone-success">
                <div class="l">Shortlisted</div>
                <div class="v" style="color:var(--success);">{m.get("shortlisted", 0)}</div>
                <div class="h">Interview eligible</div>
            </div>
            <div class="iq-metric {'tone-warning' if m.get('pending', 0) > 0 else ''}">
                <div class="l">Pending Review</div>
                <div class="v">{m.get("pending", 0)}</div>
                <div class="h">Awaiting screening</div>
            </div>
            <div class="iq-metric {'tone-error' if m.get('rejected', 0) > 0 else ''}">
                <div class="l">Rejected</div>
                <div class="v">{m.get("rejected", 0)}</div>
                <div class="h">Archived candidates</div>
            </div>
        </div>''',
        unsafe_allow_html=True
    )

    # 2. Visualizations: Application Status Distribution & Hiring Funnel
    col_dist, col_funnel = st.columns([1.1, 1.3])

    with col_dist:
        C.section("Application Status Distribution", "Candidate breakdown across evaluation stages.")
        with st.container(border=True):
            status_dist = ov.get("status_distribution") or {
                "Shortlisted": m.get("shortlisted", 0),
                "Pending Review": m.get("pending", 0),
                "Scheduled": m.get("scheduled", 0),
                "Decided": m.get("decided", 0),
                "Rejected": m.get("rejected", 0),
            }
            st.bar_chart(status_dist, height=210, use_container_width=True)

    with col_funnel:
        C.section("Hiring Pipeline Funnel", "Candidate progression through the full assessment pipeline.")
        funnel_map = {f.get("stage"): f.get("count", 0) for f in ov.get("funnel", [])}
        pipeline_stages = [
            ("Uploaded", funnel_map.get("Uploaded", m.get("total_applicants", 0))),
            ("Scored", funnel_map.get("Scored", 0)),
            ("Shortlisted", funnel_map.get("Shortlisted", m.get("shortlisted", 0))),
            ("Scheduled", funnel_map.get("Scheduled", m.get("scheduled", 0))),
            ("Interviewed", funnel_map.get("Interviewed", m.get("completed_interviews", 0))),
            ("Decided", funnel_map.get("Decided", m.get("decided", 0))),
        ]
        C.pipeline_progression(pipeline_stages)

    # 3. Needs Attention - Actionable Recruiter Tasks
    pending_actions = ov.get("pending_actions") or []
    if pending_actions:
        C.section("Needs Attention", "Tasks requiring your review to keep candidates moving forward.")
        with st.container(border=True):
            for i, act in enumerate(pending_actions):
                tgt = "Interviews" if act.get("key") == "schedule" else api.PAGE_MAP.get(act.get("page", ""), act.get("page", ""))
                status_text, status_tone = TASK_STATUS_MAP.get(
                    act.get("key"),
                    (act.get("tone", "neutral").replace("_", " ").title(), act.get("tone", "neutral"))
                )

                c_left, c_right = st.columns([4.4, 1.2], vertical_alignment="center")
                with c_left:
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:0.75rem;flex-wrap:wrap;min-width:0;padding:0.25rem 0;">'
                        f'{C.badge(status_text, status_tone)}'
                        f'<span style="color:var(--text);font-size:0.94rem;font-weight:600;line-height:1.4;">'
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
                    st.markdown('<div style="border-bottom:1px solid rgba(35,53,84,0.7);margin:0.25rem 0;"></div>', unsafe_allow_html=True)

    # 4. Recent Applications & Recent Job Activity
    col_recent_apps, col_recent_jobs = st.columns([1.2, 1.0])

    with col_recent_apps:
        C.section("Recent Applications", "Latest candidates who applied to your open positions.")
        recent_apps = ov.get("recent_applications") or []
        if recent_apps:
            app_rows = []
            for a in recent_apps:
                sc = a.get("ai_score")
                score_repr = f"**{sc:.1f}**" if sc is not None else "-"
                shortlisted_badge = C.badge("Yes", "success", dot=False) if a.get("shortlisted") else C.badge("No", "neutral", dot=False)
                app_rows.append({
                    "name": a.get("name", "Candidate"),
                    "job_title": a.get("job_title", "Job"),
                    "ai_score": score_repr,
                    "status": C.status_badge(a.get("status", "APPLIED")),
                    "shortlisted": shortlisted_badge,
                    "applied_date": a.get("applied_date", "-")
                })
            C.table([
                ("name", "Candidate", "strong"),
                ("job_title", "Position"),
                ("ai_score", "AI Match", "r"),
                ("status", "Status"),
                ("shortlisted", "Shortlisted?"),
                ("applied_date", "Applied", "r")
            ], app_rows)
        else:
            C.empty_state("No Applications Yet", "Upload resumes in the Candidates page or share job openings.")

    with col_recent_jobs:
        C.section("Recent Job Activity", "Overview of current candidate pipeline per position.")
        per_job = ov.get("per_job") or []
        if per_job:
            job_rows = []
            for pj in per_job:
                is_act = pj.get("status") == "ACTIVE"
                st_badge = C.badge("Active", "info", dot=True) if is_act else C.badge("Inactive", "neutral", dot=False)
                job_rows.append({
                    "status": st_badge,
                    "title": pj.get("title", "Position"),
                    "applicants": pj.get("applicants", 0),
                    "shortlisted": pj.get("shortlisted", 0),
                    "completed": pj.get("completed", 0),
                })
            C.table([
                ("status", "Status"),
                ("title", "Job Title", "strong"),
                ("applicants", "Applicants", "r"),
                ("shortlisted", "Shortlisted", "r"),
                ("completed", "Interviews", "r"),
            ], job_rows)
        else:
            C.empty_state("No Job Positions", "Create a new opening in the Jobs tab.")
