from datetime import date, datetime
from typing import Optional

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import RESOLUTIONS, RESOLUTION_TONES, backend_badge, identity_status_badge, identity_table


def render():
    C.page_header(
        "Interviews",
        "Manage interview scheduling, calendar availability, identity verification security gates, and active interview sessions.",
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
        "🛡️  Identity Verification & Approvals",
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

    # 1. Booking Action Card
    with st.container(border=True):
        st.markdown("#### Automated Slot Assignment")
        if pending_sched:
            C.callout(
                "info",
                f"{len(pending_sched)} confirmed candidate(s) awaiting interview slots",
                ", ".join(a.get("name") or f"#{a['application_id']}" for a in pending_sched)
            )
        else:
            st.caption("All confirmed shortlisted candidates currently have booked interview slots.")

        c_btn, _ = st.columns([2, 3])
        with c_btn:
            if st.button("Schedule Shortlisted Candidates", type="primary", disabled=not pending_sched, key=f"btn_sched_{job_id}", use_container_width=True):
                with st.spinner("Assigning earliest available calendar slots..."):
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
                    api.flash("success", "Interviews Booked", f"Successfully scheduled {len(booked)} candidate(s): " + ", ".join(booked))
                if failed:
                    api.flash("warning", "Insufficient Slots", f"Could not schedule: " + "; ".join(failed) + ". Generate more slots below.")
                st.rerun()

    # 2. Booked Interviews for this Job
    slots = api.call("GET", "/slots") or []
    booked_for_job = [s for s in slots if s.get("application_id") in apps]

    with st.container(border=True):
        st.markdown(f"#### Booked Interviews for {job_title}")
        if booked_for_job:
            C.table(
                [("when", "Slot Time", "strong"), ("who", "Candidate"), ("room", "Resource"), ("status", "Application Status"), ("conf", "Confirmation File")],
                [{"when": H.fmt_dt(s["start"]), "who": s.get("candidate") or "-", "room": s.get("resource"),
                  "status": C.status_badge(s.get("application_status")),
                  "conf": C.badge("Saved locally", "success", dot=False) if s.get("confirmation_file") else C.badge("Missing", "warning", dot=False)}
                 for s in booked_for_job]
            )
            with st.expander("Candidate Portal Access Tokens (Share privately with candidates)"):
                show = st.checkbox("Reveal access tokens", key=f"rev_tokens_{job_id}")
                for s in booked_for_job:
                    a = apps.get(s["application_id"])
                    if a:
                        st.markdown(f"• **{a.get('name') or '#' + str(a['application_id'])}**: `{a['access_token'] if show else '************'}`")
        else:
            C.empty_state("No interviews booked for this job yet", "Shortlist candidates on the Candidates page and click Schedule above.", icon="📅")

    # 3. Calendar Capacity & Daily Breakdown
    with st.container(border=True):
        now_iso = datetime.now().isoformat()
        upcoming_slots = [s for s in slots if s["start"] >= now_iso]
        free_upcoming = [s for s in upcoming_slots if s["application_id"] is None]
        booked_upcoming = [s for s in upcoming_slots if s["application_id"] is not None]

        st.markdown("#### Calendar Capacity & Generation")
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f'<div class="iq-sl-pill"><i></i><span>Upcoming Free Slots: <b>{len(free_upcoming)}</b></span></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="iq-sl-pill"><span style="color:var(--primary)">●</span>&nbsp;<span>Booked Slots: <b>{len(booked_upcoming)}</b></span></div>', unsafe_allow_html=True)
        with m3:
            st.markdown(f'<div class="iq-sl-pill"><span style="color:var(--muted)">■</span>&nbsp;<span>Total Upcoming Slots: <b>{len(upcoming_slots)}</b></span></div>', unsafe_allow_html=True)

        if not free_upcoming:
            C.callout("warning", "No upcoming free slots", "All upcoming slots are booked or elapsed. Generate more slots below.")

        c_gen1, c_gen2 = st.columns([2, 1])
        with c_gen1:
            if st.button("Generate interview slots for next 5 working days", key="btn_gen_5d", use_container_width=True):
                n = api.call("POST", "/calendar/generate")
                if n is not None:
                    api.flash("success", "Calendar Updated", f"{n.get('slots_added', 0)} new slot(s) added.")
                    st.rerun()
        with c_gen2:
            if st.button("Load mock calendar", key="btn_mock_cal", use_container_width=True):
                if api.call("POST", "/calendar/load") is not None:
                    api.flash("success", "Mock Calendar Loaded", "Loaded interview slots from mock calendar.")
                    st.rerun()

        # Day Schedule Breakdown
        days = sorted({s["start"][:10] for s in slots})
        if days:
            st.markdown("##### Day Schedule Breakdown")
            pick_day = st.selectbox("Select day", days, format_func=lambda d: date.fromisoformat(d).strftime("%A %d %B %Y"), key="interviews_cal_day")
            day_slots = [s for s in slots if s["start"].startswith(pick_day)]
            day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))
            C.table(
                [("t", "Time", "strong"), ("room", "Resource"), ("state", "State"), ("job", "Job Position")],
                [{"t": f"{H.fmt_dt(s['start'], False)} - {H.fmt_dt(s['end'], False)}", "room": s["resource"],
                  "state": C.badge(f"Booked: {s['candidate']}", "info", dot=False) if s["application_id"] else C.badge("Free", "success", dot=False),
                  "job": s.get("job_title") or ("-" if not s["application_id"] else "Other Position")}
                 for s in day_slots]
            )


# ==============================================================================
# TAB 2: IDENTITY VERIFICATION & APPROVALS
# ==============================================================================
def identity_tab(job_id: int, cfg: dict):
    data = api.call("GET", "/identity/candidates", quiet=True)
    if not data:
        C.callout("info", "Identity Verification Service", "No verification records available.")
        return

    thr = data.get("threshold", 0.70)
    is_demo = data.get("is_demo", True)
    backend_mode = data.get("backend", "demo")

    if is_demo:
        C.callout(
            "warning",
            "Demo Identity Adapter Active (Simulated Verification)",
            "Identity checks run via predefined demo scenarios. Security gates, review queues, and audit logging are fully enforced."
        )
    elif backend_mode == "opencv_basic":
        C.callout(
            "info",
            f"OpenCV Basic Heuristic Active (Threshold: {thr:.2f})",
            "Real face detection and histogram comparison active for demonstration. Ambiguous cases route to human review."
        )

    action_list = data.get("action_required", [])
    pending_list = data.get("pending", [])
    passed_list = data.get("passed", [])
    resolved_list = data.get("resolved", [])

    sub1, sub2, sub3, sub4 = st.tabs([
        f"Action Required ({len(action_list)})",
        f"Pending Verification ({len(pending_list)})",
        f"Passed Verification ({len(passed_list)})",
        f"Audit History ({len(resolved_list)})"
    ])

    with sub1:
        if not action_list:
            C.empty_state("No Identity Reviews Pending", "All candidates with scheduled interviews have verified identity or are progressing normally.", icon="✅")
        else:
            C.callout("error", f"{len(action_list)} Candidate(s) Blocked at Identity Gate", "Interviews cannot start until a recruiter resolves these review items.")
            for cand in action_list:
                render_action_card(cand)

    with sub2:
        if not pending_list:
            C.empty_state("No Pending Checks", "No candidates currently waiting to undertake verification.")
        else:
            st.caption("Candidates who have interview slots booked but have not yet completed identity check.")
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
            st.caption("Candidates whose identity has been verified (automated pass or manual recruiter approval).")
            C.table(
                [("name", "Candidate", "strong"), ("job", "Job Title"), ("status", "Application Status"), ("attempts", "Attempts"), ("backend", "Verified By")],
                [{"name": c["candidate_name"], "job": c["job_title"], "status": C.status_badge(c["application_status"]),
                  "attempts": c.get("attempts", 1),
                  "backend": backend_badge(c["latest_check"]["backend"] if c.get("latest_check") else "automated")}
                 for c in passed_list]
            )

    with sub4:
        if not resolved_list:
            C.empty_state("No Resolved Reviews Yet", "Resolved identity reviews will appear here.")
        else:
            st.caption("Audit history of manual recruiter identity decisions.")
            C.table(
                [("name", "Candidate", "strong"), ("job", "Job Title"), ("res", "Resolution"), ("notes", "Recruiter Notes"), ("at", "Resolved At")],
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
    conf = chk.get("confidence", 0.0)
    thr = chk.get("threshold", 0.70)
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
            st.caption(f"App ID: **#{aid}**")
            if cand.get("slot"):
                st.caption(f"Slot: {H.fmt_dt(cand['slot']['start'])}")

        st.markdown(f"**Reason for Review:** `{rev.get('reason') or chk.get('reason') or 'Identity check below confidence threshold'}`")
        if conf > 0:
            st.write(f"Confidence score: **{conf:.2f}** (Required Threshold: **{thr:.2f}**)")

        with st.form(f"resolve_form_{aid}"):
            res_choice = st.selectbox(
                "Select Resolution",
                list(RESOLUTIONS.keys()),
                format_func=lambda k: RESOLUTIONS[k][0],
                key=f"res_choice_{aid}"
            )
            st.caption(RESOLUTIONS[res_choice][1])
            notes = st.text_input("Mandatory Resolution Notes (Reason required for audit trail)", placeholder="e.g. Verified via direct video call with passport", key=f"res_notes_{aid}")
            sub = st.form_submit_button("Submit Resolution Decision", type="primary")

        if sub:
            if res_choice != "approve_retry" and not notes.strip():
                C.callout("error", "Notes Required", "A justification note is strictly mandatory for manual pass or rejection.")
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
        st.markdown(f"#### Active & Completed Interview Sessions for {job_title}")
        if not sessions_eligible:
            C.empty_state("No interview sessions yet", "Shortlist and schedule candidates to manage their interview sessions.")
            return

        C.table(
            [("name", "Candidate", "strong"), ("status", "Application Status"), ("resume_score", "Resume Score"), ("action", "Action")],
            [{"name": a.get("name") or f"Application #{a['application_id']}",
              "status": C.status_badge(a["status"]),
              "resume_score": f"{a['resume_score']:.1f}/100" if a.get("resume_score") is not None else "-",
              "action": "Ready for Assessment" if a["status"] == "INTERVIEW_COMPLETE" else ("Assessed" if a["status"] in ("ASSESSED", "DECIDED") else "In Progress / Scheduled")}
             for a in sessions_eligible]
        )

        st.markdown("---")
        st.markdown("##### Automated Workflow Progression")
        st.write("Advance a scheduled candidate through identity verification, conduct adaptive spoken interview turns, and generate assessment.")
        sched_or_passed = [a for a in sessions_eligible if a["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS")]
        if sched_or_passed:
            pick_app = st.selectbox(
                "Select candidate to conduct interview",
                [a["application_id"] for a in sched_or_passed],
                format_func=lambda i: next(f"{a.get('name') or 'Candidate'} (#{i}) - {a['status']}" for a in sched_or_passed if a["application_id"] == i),
                key="conduct_cand_pick"
            )
            if st.button("Conduct Interview & Generate Assessment", type="primary", key="btn_conduct_interview"):
                with st.spinner("Executing interview turns and generating assessment..."):
                    res = api.call("POST", f"/applications/{pick_app}/conduct-interview")
                    if res:
                        api.flash("success", "Interview Completed & Assessed", f"Application #{pick_app} successfully completed interview and generated assessment report.")
                        st.rerun()
        else:
            st.caption("All candidates for this job have either completed their interview or are awaiting shortlist/scheduling.")
