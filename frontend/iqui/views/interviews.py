from datetime import date, datetime
from typing import Optional

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import RESOLUTIONS, RESOLUTION_TONES, backend_badge, identity_status_badge, identity_table


def render():
    C.page_header(
        "Interviews",
        "Manage interview scheduling, calendar availability, candidate identity verification, and interview sessions.",
        "Recruiter workspace"
    )
    job_id = api.job_picker()
    if not job_id:
        return
    job = api.call("GET", f"/jobs/{job_id}") or {}
    job_title = job.get("title", f"Job #{job_id}")
    cfg = api.config() or {}

    t_sched, t_identity, t_sessions = st.tabs([
        "📅  Scheduling & Calendar",
        "🛡️  Identity Verification",
        "🎙️  Interview Sessions"
    ])

    with t_sched:
        scheduling_tab(job_id, job_title, cfg)

    with t_identity:
        identity_tab(job_id, cfg)

    with t_sessions:
        sessions_tab(job_id, job_title)


# ==============================================================================
# TAB 1: SCHEDULING & CALENDAR
# ==============================================================================
def scheduling_tab(job_id: int, job_title: str, cfg: dict):
    apps_list = api.call("GET", f"/jobs/{job_id}/applications") or []
    apps = {a["application_id"]: a for a in apps_list}
    pending_sched = [a for a in apps_list if a["status"] == "SHORTLISTED"]

    # 1. Quick Scheduling Action Card
    if pending_sched:
        with st.container(border=True):
            c_text, c_btn = st.columns([3.5, 1.5], vertical_alignment="center")
            with c_text:
                st.markdown(f"**{len(pending_sched)} Shortlisted Candidate(s) Awaiting Interview Slots**")
                st.caption(", ".join(a.get("name") or f"#{a['application_id']}" for a in pending_sched))
            with c_btn:
                if st.button("Schedule Candidates", type="primary", key=f"btn_sched_{job_id}", use_container_width=True):
                    with st.spinner("Assigning calendar slots..."):
                        res = api.call("POST", f"/jobs/{job_id}/schedule")
                    booked = []
                    failed = []
                    for r in res or []:
                        cand_name = r.get("candidate") or f"Application #{r['application_id']}"
                        if r.get("scheduled"):
                            if not r.get("already_scheduled"):
                                booked.append(f"{cand_name} on {H.fmt_dt(r['start'])} ({r['resource']})")
                        else:
                            failed.append(f"{cand_name}: {r.get('reason', 'no free slot available')}")
                    if booked:
                        api.flash("success", "Interviews Scheduled", f"Successfully scheduled {len(booked)} candidate(s): " + ", ".join(booked))
                    if failed:
                        api.flash("warning", "Insufficient Slots", f"Could not schedule: " + "; ".join(failed) + ". Generate more slots below.")
                    st.rerun()

    # 2. Booked Interviews for this Job
    slots = api.call("GET", "/slots") or []
    booked_for_job = [s for s in slots if s.get("application_id") in apps]

    C.section(f"Booked Interviews: {job_title}", "Upcoming interview slots assigned to candidates.")
    if booked_for_job:
        C.table(
            [("when", "Interview Slot", "strong"), ("who", "Candidate"), ("room", "Resource / Room"), ("status", "Application Status")],
            [{"when": H.fmt_dt(s["start"]), "who": s.get("candidate") or "-", "room": s.get("resource"),
              "status": C.status_badge(s.get("application_status"))}
             for s in booked_for_job]
        )
        with st.expander("Candidate Portal Access Tokens"):
            st.caption("Private single-use access links for candidates to join their interview:")
            show = st.checkbox("Reveal tokens", key=f"rev_tokens_{job_id}")
            for s in booked_for_job:
                a = apps.get(s["application_id"])
                if a:
                    st.markdown(f"• **{a.get('name') or '#' + str(a['application_id'])}**: `{a['access_token'] if show else '************'}`")
    else:
        C.empty_state("No interviews booked for this job yet", "Shortlist candidates on the Candidates page and click Schedule above.", icon="📅")

    # 3. Calendar Capacity & Management
    C.section("Calendar Availability", "Monitor open calendar capacity and generate new interview slots.")
    now_iso = datetime.now().isoformat()
    upcoming_slots = [s for s in slots if s["start"] >= now_iso]
    free_upcoming = [s for s in upcoming_slots if s["application_id"] is None]
    booked_upcoming = [s for s in upcoming_slots if s["application_id"] is not None]

    C.metric_grid([
        {"label": "Available Free Slots", "value": len(free_upcoming), "hint": "Ready for booking"},
        {"label": "Booked Slots", "value": len(booked_upcoming), "hint": "Reserved for candidates"},
        {"label": "Total Upcoming", "value": len(upcoming_slots), "hint": "Next 5+ working days"},
    ])

    if not free_upcoming:
        C.callout("warning", "No upcoming free slots", "All upcoming slots are booked or elapsed. Generate more slots below.")

    c_gen1, c_gen2, _ = st.columns([2, 1.5, 1.5])
    with c_gen1:
        if st.button("Generate Slots for Next 5 Working Days", key="btn_gen_5d", use_container_width=True):
            n = api.call("POST", "/calendar/generate")
            if n is not None:
                api.flash("success", "Calendar Updated", f"{n.get('slots_added', 0)} new slot(s) added.")
                st.rerun()
    with c_gen2:
        if st.button("Load Sample Calendar", key="btn_mock_cal", use_container_width=True):
            if api.call("POST", "/calendar/load") is not None:
                api.flash("success", "Sample Calendar Loaded", "Loaded interview slots from sample calendar.")
                st.rerun()

    # Day Schedule Breakdown
    days = sorted({s["start"][:10] for s in slots})
    if days:
        st.markdown("##### Day Schedule Breakdown")
        pick_day = st.selectbox("Select Date", days, format_func=lambda d: date.fromisoformat(d).strftime("%A %d %B %Y"), key="interviews_cal_day")
        raw_day_slots = [s for s in slots if s["start"].startswith(pick_day)]
        dedup_map = {}
        for s in raw_day_slots:
            key = (s["resource"], s["start"], s["end"])
            if key not in dedup_map or (s.get("application_id") and not dedup_map[key].get("application_id")):
                dedup_map[key] = s
        day_slots = list(dedup_map.values())
        day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))
        C.table(
            [("t", "Time Slot", "strong"), ("room", "Resource / Room"), ("state", "Booking Status"), ("job", "Assigned Job")],
            [{"t": f"{H.fmt_dt(s['start'], False)} - {H.fmt_dt(s['end'], False)}", "room": s["resource"],
              "state": C.badge(f"Booked: {s['candidate']}", "info", dot=False) if s["application_id"] else C.badge("Available", "success", dot=False),
              "job": s.get("job_title") or ("-" if not s["application_id"] else "Other Position")}
             for s in day_slots]
        )


# ==============================================================================
# TAB 2: IDENTITY VERIFICATION
# ==============================================================================
def identity_tab(job_id: int, cfg: dict):
    data = api.call("GET", "/identity/candidates", quiet=True)
    if not data:
        C.callout("info", "Identity Verification", "No verification records available.")
        return

    action_list = data.get("action_required", [])
    pending_list = data.get("pending", [])
    passed_list = data.get("passed", [])
    resolved_list = data.get("resolved", [])

    sub1, sub2, sub3, sub4 = st.tabs([
        f"Needs Review ({len(action_list)})",
        f"Pending Verification ({len(pending_list)})",
        f"Verified ({len(passed_list)})",
        f"Resolution History ({len(resolved_list)})"
    ])

    with sub1:
        if not action_list:
            C.empty_state("No Identity Reviews Pending", "All candidates with scheduled interviews have verified identity or are progressing normally.", icon="✅")
        else:
            C.callout("warning", f"{len(action_list)} Candidate(s) Require Identity Review", "Interviews remain locked until a recruiter reviews and resolves these cases.")
            for cand in action_list:
                render_action_card(cand)

    with sub2:
        if not pending_list:
            C.empty_state("No Pending Checks", "No candidates are currently waiting to complete verification.")
        else:
            st.caption("Candidates who have interview slots booked and have yet to complete the pre-interview check.")
            C.table(
                [("name", "Candidate", "strong"), ("job", "Job Title"), ("status", "Application Status"), ("when", "Scheduled Slot")],
                [{"name": c["candidate_name"], "job": c["job_title"], "status": C.status_badge(c["application_status"]),
                  "when": H.fmt_dt(c["slot"]["start"]) if c.get("slot") else "-"}
                 for c in pending_list]
            )

    with sub3:
        if not passed_list:
            C.empty_state("No Verified Candidates Yet", "Candidates who pass verification will appear here.")
        else:
            st.caption("Candidates whose identity has been verified (automated pass or recruiter approval).")
            C.table(
                [("name", "Candidate", "strong"), ("job", "Job Title"), ("status", "Application Status"), ("attempts", "Attempts"), ("backend", "Verification Method")],
                [{"name": c["candidate_name"], "job": c["job_title"], "status": C.status_badge(c["application_status"]),
                  "attempts": c.get("attempts", 1),
                  "backend": backend_badge(c["latest_check"]["backend"] if c.get("latest_check") else "automated")}
                 for c in passed_list]
            )

    with sub4:
        if not resolved_list:
            C.empty_state("No Resolved Reviews Yet", "Resolved identity reviews will appear here.")
        else:
            st.caption("Audit trail of manual recruiter identity decisions.")
            C.table(
                [("name", "Candidate", "strong"), ("job", "Job Title"), ("res", "Resolution"), ("notes", "Recruiter Notes"), ("at", "Resolved Date")],
                [{"name": r["candidate_name"], "job": r["job_title"],
                  "res": C.badge(RESOLUTION_TONES.get(r["resolution"], (r["resolution"], "neutral"))[0],
                                 RESOLUTION_TONES.get(r["resolution"], (r["resolution"], "neutral"))[1]),
                  "notes": r.get("notes") or "-", "at": H.fmt_dt(r.get("resolved_at"))}
                 for r in resolved_list]
            )


def render_action_card(cand: dict):
    aid = cand["application_id"]
    rev = cand.get("open_review") or {}
    chk = cand.get("latest_check") or {}
    status_label_str = cand.get("identity_status", "FAILED")

    with st.container(border=True):
        col_hdr1, col_hdr2 = st.columns([3, 1])
        with col_hdr1:
            st.markdown(f"#### {cand['candidate_name']}")
            C.badges(
                identity_status_badge(status_label_str),
                backend_badge(chk.get("backend", "demo")),
                C.status_badge(cand["application_status"])
            )
        with col_hdr2:
            st.caption(f"Application: **#{aid}**")
            if cand.get("slot"):
                st.caption(f"Slot: {H.fmt_dt(cand['slot']['start'])}")

        st.markdown(f"**Flagged Reason:** {rev.get('reason') or chk.get('reason') or 'Verification check requires recruiter review.'}")

        with st.form(f"resolve_form_{aid}"):
            res_choice = st.selectbox(
                "Recruiter Resolution Decision",
                list(RESOLUTIONS.keys()),
                format_func=lambda k: RESOLUTIONS[k][0],
                key=f"res_choice_{aid}"
            )
            st.caption(RESOLUTIONS[res_choice][1])
            notes = st.text_input("Resolution Justification Note (Required for manual approval or decline)", placeholder="e.g. Verified via direct video call with official ID", key=f"res_notes_{aid}")
            sub = st.form_submit_button("Confirm Resolution Decision", type="primary")

        if sub:
            if res_choice != "approve_retry" and not notes.strip():
                C.callout("error", "Note Required", "A justification note is mandatory for manual approval or decline.")
            else:
                ok, res_data = api.request("POST", f"/reviews/{rev['id']}/resolve", json={"resolution": res_choice, "notes": notes.strip()})
                if ok:
                    api.flash("success", "Review Resolved", f"Candidate #{aid} resolution '{res_choice}' recorded.")
                    st.rerun()
                else:
                    C.callout("error", "Failed to resolve review", res_data)


# ==============================================================================
# TAB 3: INTERVIEW SESSIONS
# ==============================================================================
def sessions_tab(job_id: int, job_title: str):
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    sessions_eligible = [a for a in apps if a["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS", "INTERVIEW_COMPLETE", "ASSESSED", "DECIDED")]

    with st.container(border=True):
        st.markdown(f"#### Active & Completed Interview Sessions: {job_title}")
        if not sessions_eligible:
            C.empty_state("No interview sessions yet", "Shortlist and schedule candidates to manage their interview sessions.")
            return

        C.table(
            [("name", "Candidate", "strong"), ("status", "Interview Status"), ("resume_score", "Resume Score"), ("action", "Next Step")],
            [{"name": a.get("name") or f"Application #{a['application_id']}",
              "status": C.status_badge(a["status"]),
              "resume_score": f"{a['resume_score']:.1f} / 10" if a.get("resume_score") is not None else "-",
              "action": "Generate Assessment" if a["status"] == "INTERVIEW_COMPLETE" else ("Assessed & Ready for Decision" if a["status"] in ("ASSESSED", "DECIDED") else "Ready for Interview")}
             for a in sessions_eligible]
        )

        st.markdown("---")
        st.markdown("##### Conduct Spoken Interview")
        st.caption("Select a scheduled candidate to conduct their AI-assisted interview session and generate competency assessments.")
        sched_or_passed = [a for a in sessions_eligible if a["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS")]
        if sched_or_passed:
            pick_app = st.selectbox(
                "Select Candidate",
                [a["application_id"] for a in sched_or_passed],
                format_func=lambda i: next(f"{a.get('name') or 'Candidate'} (#{i}) - {H.status_label(a['status'])[0]}" for a in sched_or_passed if a["application_id"] == i),
                key="conduct_cand_pick"
            )
            col_b, _ = st.columns([2, 3])
            with col_b:
                if st.button("Conduct Interview & Generate Assessment", type="primary", key="btn_conduct_interview", use_container_width=True):
                    with st.spinner("Conducting interview session and generating assessment..."):
                        res = api.call("POST", f"/applications/{pick_app}/conduct-interview")
                        if res:
                            api.flash("success", "Interview Completed & Assessed", f"Application #{pick_app} successfully completed interview and generated assessment report.")
                            st.rerun()
        else:
            st.caption("All candidates for this job have completed their interview or are awaiting shortlisting.")
