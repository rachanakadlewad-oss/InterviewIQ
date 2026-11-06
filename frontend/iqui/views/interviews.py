from datetime import date, datetime
from typing import Optional

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import RESOLUTIONS, RESOLUTION_TONES, backend_badge, identity_status_badge

# Scoped styling refinements for recruiter Interviews screen
INTERVIEWS_CSS = """
<style>
.iq-empty-compact {
  border: 1px dashed var(--border);
  border-radius: var(--radius-sm);
  padding: 1.1rem 1.25rem !important;
  text-align: center;
  background: rgba(17, 27, 48, 0.35);
  margin: 0.35rem 0 0.65rem !important;
}
.iq-empty-compact .icon {
  font-size: 1.25rem !important;
  margin-bottom: 0.2rem !important;
  opacity: 0.8;
}
.iq-empty-compact .t {
  font-weight: 650;
  color: var(--text);
  font-size: 0.88rem !important;
}
.iq-empty-compact .b {
  color: var(--muted);
  font-size: 0.8rem !important;
  margin-top: 0.15rem !important;
  max-width: 520px;
  margin-left: auto;
  margin-right: auto;
  line-height: 1.45;
}
.iq-cal-metrics .iq-metric {
  padding: 0.65rem 0.95rem !important;
}
.iq-cal-metrics .iq-metric .l {
  font-size: 0.68rem !important;
  letter-spacing: 0.04em !important;
}
.iq-cal-metrics .iq-metric .v {
  font-size: 1.45rem !important;
  margin: 0.15rem 0 0.05rem !important;
}
.iq-cal-metrics .iq-metric .h {
  font-size: 0.72rem !important;
}
</style>
"""

INTERVIEW_TABLE_COLUMNS = [
    ("candidate", "Candidate", "strong"),
    ("slot", "Interview Slot"),
    ("status", "Interview Status"),
    ("identity", "Identity Clearance"),
    ("score", "Resume Score"),
    ("step", "Next Step")
]


def render():
    st.markdown(INTERVIEWS_CSS, unsafe_allow_html=True)
    C.page_header(
        "Interviews",
        "Monitor upcoming and completed interview sessions, track identity verification clearance, and manage schedule capacity.",
        "Recruiter workspace"
    )
    job_id = api.job_picker()
    if not job_id:
        return
    job = api.call("GET", f"/jobs/{job_id}") or {}
    job_title = job.get("title", f"Job #{job_id}")
    cfg = api.config() or {}

    t_interviews, t_identity, t_calendar = st.tabs([
        "Interviews",
        "Identity Review",
        "Calendar & Capacity"
    ])

    with t_interviews:
        interviews_tab(job_id, job_title, cfg)

    with t_identity:
        identity_tab(job_id, cfg)

    with t_calendar:
        calendar_tab(job_id, job_title, cfg)


# ==============================================================================
# TAB 1: INTERVIEWS (UPCOMING & COMPLETED)
# ==============================================================================
def interviews_tab(job_id: int, job_title: str, cfg: dict):
    apps_list = api.call("GET", f"/jobs/{job_id}/applications") or []
    slots = api.call("GET", "/slots") or []
    id_data = api.call("GET", "/identity/candidates", quiet=True) or {}

    slots_by_app = {s["application_id"]: s for s in slots if s.get("application_id")}

    id_by_app = {}
    for group in ("action_required", "pending", "passed"):
        for cand in id_data.get(group, []):
            id_by_app[cand["application_id"]] = cand

    # Shortlisted candidates awaiting calendar slot assignment
    pending_sched = [a for a in apps_list if a["status"] == "SHORTLISTED"]
    if pending_sched:
        col_msg, col_btn = st.columns([3.8, 1.2], vertical_alignment="center")
        with col_msg:
            cand_names = ", ".join(a.get("name") or f"#{a['application_id']}" for a in pending_sched)
            C.callout(
                "info",
                f"{len(pending_sched)} Shortlisted Candidate{'s' if len(pending_sched) != 1 else ''} Ready to Schedule",
                f"Assign interview slots to advance candidates: {cand_names}"
            )
        with col_btn:
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
                    api.flash("warning", "Insufficient Slots", "Could not schedule: " + "; ".join(failed) + ". Generate more slots in Calendar & Capacity.")
                st.rerun()

    # Partition into upcoming vs completed
    upcoming = [
        a for a in apps_list
        if a["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS")
        or (a["application_id"] in slots_by_app and a["status"] not in ("INTERVIEW_COMPLETE", "ASSESSED", "DECIDED", "REJECTED"))
    ]
    completed = [
        a for a in apps_list
        if a["status"] in ("INTERVIEW_COMPLETE", "ASSESSED", "DECIDED")
    ]

    if not upcoming and not completed and not pending_sched:
        _compact_empty_state(
            "No Interviews Scheduled",
            "Shortlist candidates on the Candidates page to begin assigning interview slots.",
            icon="🎙️"
        )
        return

    # 1. Upcoming Interviews
    if upcoming:
        C.section("Upcoming Interviews", "Scheduled candidate sessions and pre-interview verification clearance.")
        C.table(
            INTERSECTION_COLUMNS if False else INTERVIEW_TABLE_COLUMNS,
            [
                {
                    "candidate": a.get("name") or f"Application #{a['application_id']}",
                    "slot": f"{H.fmt_dt(slots_by_app[a['application_id']]['start'])} ({slots_by_app[a['application_id']]['resource']})" if a["application_id"] in slots_by_app else "Slot not assigned",
                    "status": _interview_status_badge(a["status"]),
                    "identity": _identity_status_badge(a["application_id"], a["status"], id_by_app),
                    "score": f"{a['resume_score']:.1f} / 10" if a.get("resume_score") is not None else "-",
                    "step": _next_step_label(a["application_id"], a["status"], id_by_app)
                }
                for a in upcoming
            ]
        )

        # Restrained actions & access details (collapsible)
        sched_or_passed = [a for a in upcoming if a["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS")]
        if sched_or_passed:
            with st.expander("Conduct Spoken Interview Session", expanded=False):
                st.caption("Select a scheduled candidate to run their AI-assisted interview session and generate competency assessments.")
                col_pick, col_go = st.columns([3.2, 1.8], vertical_alignment="bottom")
                with col_pick:
                    pick_app = st.selectbox(
                        "Candidate to Interview",
                        [a["application_id"] for a in sched_or_passed],
                        format_func=lambda i: next(
                            f"{a.get('name') or 'Candidate'} (#{i}) — {_interview_status_text(a['status'])}"
                            for a in sched_or_passed if a["application_id"] == i
                        ),
                        key=f"conduct_cand_pick_{job_id}"
                    )
                with col_go:
                    if st.button("Conduct Interview & Assessment", type="primary", key=f"btn_conduct_{job_id}", use_container_width=True):
                        with st.spinner("Conducting interview session and generating assessment..."):
                            res = api.call("POST", f"/applications/{pick_app}/conduct-interview")
                            if res:
                                api.flash("success", "Interview Completed & Assessed", f"Application #{pick_app} successfully completed interview and generated assessment report.")
                                st.rerun()

        with st.expander("Candidate Portal Access Links", expanded=False):
            st.caption("Private single-use access links for candidates to join their pre-interview check and interview room.")
            show_tok = st.checkbox("Reveal secret tokens", key=f"rev_tokens_{job_id}")
            for a in upcoming:
                tok = a.get("access_token", "")
                tok_str = tok if show_tok else "••••••••••••••••"
                st.markdown(f"• **{a.get('name') or '#' + str(a['application_id'])}**: `{tok_str}`")

    # 2. Completed Interviews
    if completed:
        if upcoming:
            st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
        C.section("Completed Interviews", "Finished interview sessions with generated competency reports.")
        C.table(
            INTERVIEW_TABLE_COLUMNS,
            [
                {
                    "candidate": a.get("name") or f"Application #{a['application_id']}",
                    "slot": H.fmt_dt(slots_by_app[a['application_id']]["start"]) if a["application_id"] in slots_by_app else "-",
                    "status": _interview_status_badge(a["status"]),
                    "identity": _identity_status_badge(a["application_id"], a["status"], id_by_app),
                    "score": f"{a['resume_score']:.1f} / 10" if a.get("resume_score") is not None else "-",
                    "step": "Assessed — Ready for decision" if a["status"] in ("ASSESSED", "DECIDED") else "Awaiting assessment generation"
                }
                for a in completed
            ]
        )
        col_nav, _ = st.columns([2.2, 2.8])
        with col_nav:
            st.button("Open Evaluation Reports", on_click=api.go, args=("Reports",), key="btn_go_reports", use_container_width=True)


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

    C.section("Identity Verification Queue", "Monitor identity clearance, review flagged exceptions, and inspect resolution history.")

    sub_action, sub_pending, sub_passed, sub_audit = st.tabs([
        f"Needs Review ({len(action_list)})",
        f"Pending Verification ({len(pending_list)})",
        f"Verified ({len(passed_list)})",
        f"Resolution History ({len(resolved_list)})"
    ])

    with sub_action:
        if not action_list:
            _compact_empty_state(
                "No Identity Reviews Pending",
                "All candidates with scheduled interviews have verified identity or are progressing normally.",
                icon="✓"
            )
        else:
            C.callout(
                "warning",
                f"{len(action_list)} Candidate(s) Require Identity Review",
                "The interview gate remains locked until you approve manual pass, authorize retry, or reject."
            )
            for cand in action_list:
                render_action_card(cand)

    with sub_pending:
        if not pending_list:
            _compact_empty_state("No Pending Checks", "No candidates are currently waiting to complete verification.", icon="✓")
        else:
            st.caption("Candidates who have interview slots booked and have yet to complete their pre-interview camera check.")
            C.table(
                [
                    ("name", "Candidate", "strong"),
                    ("job", "Job Title"),
                    ("status", "Interview Status"),
                    ("slot", "Scheduled Slot")
                ],
                [
                    {
                        "name": c["candidate_name"],
                        "job": c["job_title"],
                        "status": _interview_status_badge(c["application_status"]),
                        "slot": H.fmt_dt(c["slot"]["start"]) if c.get("slot") else "-"
                    }
                    for c in pending_list
                ]
            )

    with sub_passed:
        if not passed_list:
            _compact_empty_state("No Verified Candidates Yet", "Candidates who pass verification will appear here.", icon="ℹ️")
        else:
            st.caption("Candidates whose identity has been verified through automated checks or recruiter override.")
            C.table(
                [
                    ("name", "Candidate", "strong"),
                    ("job", "Job Title"),
                    ("status", "Interview Status"),
                    ("attempts", "Attempts"),
                    ("backend", "Verification Method")
                ],
                [
                    {
                        "name": c["candidate_name"],
                        "job": c["job_title"],
                        "status": _interview_status_badge(c["application_status"]),
                        "attempts": c.get("attempts", 1),
                        "backend": backend_badge(c["latest_check"]["backend"] if c.get("latest_check") else "automated")
                    }
                    for c in passed_list
                ]
            )

    with sub_audit:
        if not resolved_list:
            _compact_empty_state("No Resolution History Yet", "Resolved identity reviews will appear here.", icon="ℹ️")
        else:
            st.caption("Audit trail of manual recruiter identity decisions.")
            C.table(
                [
                    ("name", "Candidate", "strong"),
                    ("job", "Job Title"),
                    ("res", "Resolution"),
                    ("notes", "Recruiter Justification"),
                    ("at", "Resolved Date")
                ],
                [
                    {
                        "name": r["candidate_name"],
                        "job": r["job_title"],
                        "res": C.badge(
                            RESOLUTION_TONES.get(r["resolution"], (r["resolution"], "neutral"))[0],
                            RESOLUTION_TONES.get(r["resolution"], (r["resolution"], "neutral"))[1],
                            dot=False
                        ),
                        "notes": r.get("notes") or "-",
                        "at": H.fmt_dt(r.get("resolved_at"))
                    }
                    for r in resolved_list
                ]
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
                _interview_status_badge(cand["application_status"])
            )
        with col_hdr2:
            st.caption(f"Application: **#{aid}**")
            if cand.get("slot"):
                st.caption(f"Slot: {H.fmt_dt(cand['slot']['start'])}")

        flag_reason = rev.get("reason") or chk.get("reason") or "Verification check requires recruiter review."
        C.callout("warning", "Flagged Reason", flag_reason)

        with st.form(f"resolve_form_{aid}"):
            res_choice = st.selectbox(
                "Recruiter Resolution Decision",
                list(RESOLUTIONS.keys()),
                format_func=lambda k: RESOLUTIONS[k][0],
                key=f"res_choice_{aid}"
            )
            st.caption(RESOLUTIONS[res_choice][1])
            notes = st.text_input(
                "Resolution Justification Note (Required for manual approval or decline)",
                placeholder="e.g. Verified via direct video call with official ID",
                key=f"res_notes_{aid}"
            )
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
# TAB 3: CALENDAR & CAPACITY
# ==============================================================================
def calendar_tab(job_id: int, job_title: str, cfg: dict):
    slots = api.call("GET", "/slots") or []
    now_iso = datetime.now().isoformat()
    upcoming_slots = [s for s in slots if s["start"] >= now_iso]
    free_upcoming = [s for s in upcoming_slots if s["application_id"] is None]
    booked_upcoming = [s for s in upcoming_slots if s["application_id"] is not None]

    C.section("Schedule Capacity", "Monitor room availability, generate upcoming booking slots, and inspect daily schedules.")

    st.markdown('<div class="iq-cal-metrics">', unsafe_allow_html=True)
    C.metric_grid([
        {"label": "Available Free Slots", "value": len(free_upcoming), "hint": "Ready for booking"},
        {"label": "Booked Slots", "value": len(booked_upcoming), "hint": "Reserved for candidates"},
        {"label": "Total Upcoming", "value": len(upcoming_slots), "hint": "Next 5+ working days"},
    ])
    st.markdown('</div>', unsafe_allow_html=True)

    if not free_upcoming:
        C.callout("warning", "No upcoming free slots", "All upcoming slots are booked or elapsed. Generate more slots below.")

    col_g1, col_g2, _ = st.columns([1.8, 1.4, 1.8])
    with col_g1:
        if st.button("Generate Next 5 Working Days", key="btn_gen_5d", use_container_width=True):
            n = api.call("POST", "/calendar/generate")
            if n is not None:
                api.flash("success", "Calendar Updated", f"{n.get('slots_added', 0)} new slot(s) added.")
                st.rerun()
    with col_g2:
        if st.button("Load Sample Calendar", key="btn_mock_cal", use_container_width=True):
            if api.call("POST", "/calendar/load") is not None:
                api.flash("success", "Sample Calendar Loaded", "Loaded interview slots from sample calendar.")
                st.rerun()

    # Day Schedule Breakdown
    days = sorted({s["start"][:10] for s in slots})
    if days:
        st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
        C.section("Daily Schedule Breakdown", "View room allocation and booked candidates by date.")
        pick_day = st.selectbox(
            "Select Date",
            days,
            format_func=lambda d: date.fromisoformat(d).strftime("%A, %d %B %Y"),
            key="interviews_cal_day"
        )
        raw_day_slots = [s for s in slots if s["start"].startswith(pick_day)]
        dedup_map = {}
        for s in raw_day_slots:
            key = (s["resource"], s["start"], s["end"])
            if key not in dedup_map or (s.get("application_id") and not dedup_map[key].get("application_id")):
                dedup_map[key] = s
        day_slots = list(dedup_map.values())
        day_slots.sort(key=lambda s: (s["start"], s["resource"], s["id"]))
        C.table(
            [
                ("time", "Time Slot", "strong"),
                ("room", "Resource / Room"),
                ("status", "Booking Status"),
                ("job", "Position")
            ],
            [
                {
                    "time": f"{H.fmt_dt(s['start'], False)} - {H.fmt_dt(s['end'], False)}",
                    "room": s["resource"],
                    "status": C.badge(f"Booked: {s['candidate']}", "info", dot=True) if s["application_id"] else C.badge("Available", "success", dot=True),
                    "job": s.get("job_title") or ("-" if not s["application_id"] else "Other Position")
                }
                for s in day_slots
            ]
        )


# ==============================================================================
# PRESENTATION HELPERS (PURE)
# ==============================================================================
def _compact_empty_state(title: str, body: str = "", icon: str = "✓"):
    st.markdown(
        f'<div class="iq-empty-compact">'
        f'<div class="icon">{C.esc(icon)}</div>'
        f'<div class="t">{C.esc(title)}</div>'
        f'{f"<div class=b>{C.esc(body)}</div>" if body else ""}'
        f'</div>',
        unsafe_allow_html=True
    )


def _identity_status_badge(app_id: int, app_status: str, id_by_app: dict) -> C.Raw:
    cand_id = id_by_app.get(app_id)
    if cand_id:
        st_val = (cand_id.get("identity_status") or "").upper()
        if st_val == "PASSED":
            return C.badge("Verified", "success", dot=True)
        elif st_val == "INCONCLUSIVE":
            return C.badge("Review: Inconclusive", "warning", dot=True)
        elif st_val == "FAILED":
            return C.badge("Review: Failed", "error", dot=True)
        elif st_val == "PENDING":
            return C.badge("Pending Check", "info", dot=True)

    if app_status in ("IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS", "INTERVIEW_COMPLETE", "ASSESSED", "DECIDED"):
        return C.badge("Verified", "success", dot=True)
    elif app_status == "SCHEDULED":
        return C.badge("Pending Check", "info", dot=True)
    return C.badge("Not Scheduled", "neutral", dot=False)


def _interview_status_badge(status: str) -> C.Raw:
    s = (status or "").upper()
    if s == "SHORTLISTED":
        return C.badge("Awaiting Slot", "warning", dot=True)
    elif s == "SCHEDULED":
        return C.badge("Scheduled", "info", dot=True)
    elif s == "IDENTITY_PASSED":
        return C.badge("Cleared to Start", "success", dot=True)
    elif s == "INTERVIEW_IN_PROGRESS":
        return C.badge("In Progress", "warning", dot=True)
    elif s == "INTERVIEW_COMPLETE":
        return C.badge("Completed", "info", dot=True)
    elif s == "ASSESSED":
        return C.badge("Assessed", "success", dot=True)
    elif s == "DECIDED":
        return C.badge("Decision Recorded", "neutral", dot=True)
    return C.status_badge(status)


def _interview_status_text(status: str) -> str:
    s = (status or "").upper()
    if s == "SCHEDULED":
        return "Scheduled"
    elif s == "IDENTITY_PASSED":
        return "Cleared to Start"
    elif s == "INTERVIEW_IN_PROGRESS":
        return "In Progress"
    elif s == "INTERVIEW_COMPLETE":
        return "Completed"
    elif s == "ASSESSED":
        return "Assessed"
    elif s == "DECIDED":
        return "Decision Recorded"
    return H.status_label(status)[0]


def _next_step_label(app_id: int, app_status: str, id_by_app: dict) -> str:
    cand_id = id_by_app.get(app_id)
    if cand_id and cand_id.get("identity_status") in ("FAILED", "INCONCLUSIVE"):
        return "Review required (Identity tab)"
    if app_status == "IDENTITY_PASSED":
        return "Ready for interview"
    elif app_status == "SCHEDULED":
        return "Awaiting candidate check-in"
    elif app_status == "INTERVIEW_IN_PROGRESS":
        return "Interview active"
    return "Ready"
