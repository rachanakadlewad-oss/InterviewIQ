import streamlit as st

from .. import api, components as C, helpers as H

RESOLUTIONS = {
    "approve_manual_pass": ("Verify manually and approve", "You vouch for the candidate's identity (e.g. direct video call or verified ID document). Overrides the identity gate and allows the interview to start. A mandatory reason is logged."),
    "approve_retry": ("Allow another attempt (Retry)", "Authorizes the candidate to retake the identity verification check. The interview gate remains locked until a verification check passes. A mandatory reason is logged."),
    "reject": ("Close application (Reject)", "Terminates the application and deletes the stored reference photo. The interview gate is closed permanently. A mandatory reason is logged."),
}

RESOLUTION_TONES = {
    "approve_manual_pass": ("Manually Approved", "success"),
    "approve_retry": ("Retry Authorized", "warning"),
    "reject": ("Application Rejected", "error"),
}


def backend_badge(backend: str):
    b = (backend or "").lower()
    if "demo" in b:
        return C.badge("Demo Adapter (Simulated - Non-Biometric)", "warning", dot=False)
    elif "opencv" in b:
        return C.badge("OpenCV Heuristic (Non-Biometric Grade)", "neutral", dot=False)
    elif "human" in b or "reviewer" in b:
        return C.badge("Recruiter Manual Override", "info", dot=False)
    elif "biometric" in b:
        return C.badge("Biometric Verification", "success", dot=False)
    return C.badge(backend or "Automated Check", "neutral", dot=False)


def identity_status_badge(status: str):
    s = (status or "").upper()
    if s == "PASSED":
        return C.badge("Passed", "success")
    elif s == "FAILED":
        return C.badge("Failed", "error")
    elif s == "INCONCLUSIVE":
        return C.badge("Inconclusive", "warning")
    elif s == "PENDING":
        return C.badge("Pending", "info")
    return C.badge(status or "Unknown", "neutral")


def render():
    C.page_header(
        "Identity Review",
        "Monitor verification status across all candidates, inspect verification evidence, and resolve failed or inconclusive cases with mandatory accountability.",
        "Recruiter workspace"
    )

    data = api.call("GET", "/identity/candidates", quiet=True)
    if not data:
        # Fallback to /reviews
        open_reviews = api.call("GET", "/reviews", params={"status": "OPEN"}) or []
        resolved_reviews = api.call("GET", "/reviews", params={"status": "RESOLVED"}) or []
        cfg = api.config() or {}
        data = {
            "threshold": cfg.get("identity_threshold", 0.70),
            "backend": cfg.get("identity_backend", "demo"),
            "is_demo": cfg.get("identity_is_demo", True),
            "action_required": [{"application_id": r["application_id"], "candidate_name": r["candidate"],
                                 "email": r.get("email", ""), "job_title": r.get("job_title", ""),
                                 "application_status": r.get("application_status", "HUMAN_REVIEW"),
                                 "identity_status": "INCONCLUSIVE" if "inconclusive" in r["reason"].lower() else "FAILED",
                                 "open_review": r, "slot": r.get("slot"), "attempts": 1, "all_checks": []}
                                for r in open_reviews],
            "pending": [],
            "passed": [],
            "resolved": resolved_reviews,
        }

    thr = data.get("threshold", 0.70)
    is_demo = data.get("is_demo", True)
    backend_mode = data.get("backend", "demo")

    # Disclaimer banner: clearly distinguishing simulated demo vs opencv heuristic vs real biometric
    if is_demo:
        C.callout(
            "warning",
            "DEMO ADAPTER ACTIVE - SIMULATED VERIFICATION ONLY",
            "Identity checks are running on the demo adapter where outcomes are driven by predefined test scenarios (e.g. match, no_face, multiple_faces). "
            "NO actual biometric facial recognition or scanning is performed. The security gate, review queue, and audit trail are fully functional."
        )
    elif backend_mode == "opencv_basic":
        C.callout(
            "info",
            "OpenCV Basic Heuristic Active (Non-Biometric Grade)",
            f"Uses OpenCV Haar cascades for face detection and local binary pattern histograms for comparison (threshold {thr:.2f}). "
            "This heuristic is designed for demonstration and is NOT biometric grade. Human review is recommended for any ambiguous cases."
        )
    else:
        C.callout("info", "Biometric Verification Active", f"Verification threshold set to {thr:.2f}.")

    action_list = data.get("action_required", [])
    pending_list = data.get("pending", [])
    passed_list = data.get("passed", [])
    resolved_list = data.get("resolved", [])

    tab_action, tab_pending, tab_passed, tab_resolved = st.tabs([
        f"Action Required ({len(action_list)})",
        f"Pending Verification ({len(pending_list)})",
        f"Verified ({len(passed_list)})",
        f"Resolved Audit Trail ({len(resolved_list)})"
    ])

    with tab_action:
        render_action_required(action_list, thr, is_demo)

    with tab_pending:
        render_pending_candidates(pending_list)

    with tab_passed:
        render_passed_candidates(passed_list, thr)

    with tab_resolved:
        render_resolved_audit(resolved_list)


def render_action_required(candidates, threshold, is_demo):
    if not candidates:
        C.empty_state(
            "No Identity Reviews Waiting",
            "All candidate identity checks are currently verified or pending. Candidates whose automated checks fail or return inconclusive results will appear here."
        )
        return

    st.markdown(
        f"**{len(candidates)} candidate{'s' if len(candidates) != 1 else ''} require manual recruiter disposition.** "
        "The interview cannot start or continue until you approve manual pass or authorize a retry."
    )

    for cand in candidates:
        render_review_card(cand, threshold, is_demo)


def render_review_card(cand, threshold, is_demo):
    app_id = cand["application_id"]
    rev = cand.get("open_review")
    rev_id = rev["id"] if rev else None
    id_status = cand.get("identity_status", "FAILED")
    latest_check = cand.get("latest_check")
    card_cls = "iq-id-card inconclusive" if id_status == "INCONCLUSIVE" else "iq-id-card failed"

    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            C.badges(
                identity_status_badge(id_status),
                backend_badge(latest_check.get("backend") if latest_check else ("demo_adapter" if is_demo else "opencv_basic")),
                C.badge(cand.get("job_title") or "Candidate", "neutral", dot=False)
            )
            st.markdown(f"### {cand.get('candidate_name') or f'Application #{app_id}'}")
        with col2:
            st.caption(f"App ID: **#{app_id}**")
            if cand.get("email"):
                st.caption(f"Email: {cand.get('email')}")

        # Basic metadata
        slot_info = cand.get("slot")
        slot_str = f"{H.fmt_dt(slot_info['start'])} ({slot_info['resource']})" if slot_info else "Not yet booked"
        raised_str = H.fmt_dt(rev["created_at"]) if rev else (H.fmt_dt(latest_check["timestamp"]) if latest_check else "-")
        reason_str = rev["reason"] if rev else (latest_check.get("reason", "Verification failed") if latest_check else "Verification failed")

        C.kv([
            ("Scheduled Slot", slot_str),
            ("Flagged At", raised_str),
            ("Attempts", str(cand.get("attempts", 1))),
            ("Flag Reason", reason_str)
        ])

        # Verification Evidence Section
        st.markdown("**Verification Evidence & Metrics**")
        if latest_check:
            faces_val = f"{latest_check.get('face_count', 0)} detected"
            conf_val = f"{latest_check.get('confidence', 0.0):.2f} (required: {latest_check.get('threshold', threshold):.2f})"
            check_time = H.fmt_dt(latest_check.get("timestamp"))
            check_type = (latest_check.get("check_type") or "pre_interview").replace("_", " ").title()
            backend_method = latest_check.get("backend", "demo_adapter")
        else:
            faces_val = "Not recorded"
            conf_val = f"Below {threshold:.2f}"
            check_time = raised_str
            check_type = "Pre-Interview"
            backend_method = "demo_adapter" if is_demo else "opencv_basic"

        st.markdown(
            f'<div class="iq-id-evidence">'
            f'<div class="iq-id-evidence-grid">'
            f'<div class="iq-id-evidence-item"><span class="iq-id-evidence-label">Face Count</span><span class="iq-id-evidence-val">{faces_val}</span></div>'
            f'<div class="iq-id-evidence-item"><span class="iq-id-evidence-label">Confidence Score</span><span class="iq-id-evidence-val">{conf_val}</span></div>'
            f'<div class="iq-id-evidence-item"><span class="iq-id-evidence-label">Check Type</span><span class="iq-id-evidence-val">{check_type}</span></div>'
            f'<div class="iq-id-evidence-item"><span class="iq-id-evidence-label">Timestamp</span><span class="iq-id-evidence-val">{check_time}</span></div>'
            f'<div class="iq-id-evidence-item"><span class="iq-id-evidence-label">Method</span><span class="iq-id-evidence-val">{backend_method}</span></div>'
            f'</div>'
            f'<div class="iq-id-notice">⚠️ Note: Verification method is not biometric grade. Do not treat simulated demo or heuristic output as biometric proof.</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        # Full check history if multiple checks exist
        all_checks = cand.get("all_checks", [])
        if len(all_checks) > 1:
            with st.expander(f"View Full Verification History ({len(all_checks)} checks)", expanded=False):
                identity_history_table(all_checks)

        st.markdown("---")
        st.markdown("#### Recruiter Review Disposition")

        key_suffix = f"_{rev_id or app_id}"
        chosen_res = st.radio(
            "Select action",
            list(RESOLUTIONS.keys()),
            key=f"res{key_suffix}",
            format_func=lambda k: RESOLUTIONS[k][0],
            horizontal=False
        )
        st.caption(RESOLUTIONS[chosen_res][1])

        notes = st.text_area(
            "Mandatory Justification / Reviewer Reason *",
            placeholder="Explain why you are approving, authorizing retry, or closing this case (e.g., 'Verified identity via direct video call with passport ID' or 'Poor lighting caused inconclusive detection; authorizing candidate to retry in better lighting').",
            key=f"notes{key_suffix}",
            help="This note is permanently recorded in the audit log for compliance and accountability."
        )

        col_btn, _ = st.columns([2, 3])
        with col_btn:
            if st.button("Apply Decision", key=f"apply{key_suffix}", type="primary", use_container_width=True):
                if not notes.strip():
                    C.callout("error", "Mandatory Reason Required", "You must provide a clear reason or justification for this disposition to maintain audit compliance.")
                elif rev_id:
                    res = api.call("POST", f"/reviews/{rev_id}/resolve", json={"resolution": chosen_res, "notes": notes.strip()})
                    if res:
                        api.flash("success", "Review Resolved", f"{RESOLUTIONS[chosen_res][0]} applied for {cand.get('candidate_name')}.")
                        st.rerun()
                else:
                    C.callout("error", "Missing Review Item", "Could not locate open review item for this application.")


def render_pending_candidates(candidates):
    if not candidates:
        C.empty_state(
            "No Candidates Pending Verification",
            "There are currently no scheduled candidates awaiting pre-interview identity verification."
        )
        return

    st.markdown(
        f"**{len(candidates)} candidate{'s' if len(candidates) != 1 else ''} scheduled for interview and awaiting identity check.** "
        "The interview gate remains locked until the candidate performs verification and passes."
    )

    for cand in candidates:
        app_id = cand["application_id"]
        slot_info = cand.get("slot")
        slot_str = f"{H.fmt_dt(slot_info['start'])} ({slot_info['resource']})" if slot_info else "Slot not booked"

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                C.badges(
                    identity_status_badge("PENDING"),
                    C.badge("Gate Locked", "error", dot=True),
                    C.badge(cand.get("job_title") or "Candidate", "neutral", dot=False)
                )
                st.markdown(f"### {cand.get('candidate_name') or f'Application #{app_id}'}")
            with col2:
                st.caption(f"App ID: **#{app_id}**")
                if cand.get("email"):
                    st.caption(f"Email: {cand.get('email')}")

            C.kv([
                ("Interview Slot", slot_str),
                ("Verification Status", "Pending Pre-Interview Check"),
                ("Attempts", str(cand.get("attempts", 0))),
                ("Interview Gate", "🔒 Locked - Candidate must pass verification before interview begins")
            ])


def render_passed_candidates(candidates, threshold):
    if not candidates:
        C.empty_state(
            "No Verified Candidates",
            "Candidates who have successfully satisfied identity verification requirements will appear here."
        )
        return

    st.markdown(
        f"**{len(candidates)} candidate{'s' if len(candidates) != 1 else ''} verified with interview gate clearance.**"
    )

    for cand in candidates:
        app_id = cand["application_id"]
        latest_check = cand.get("latest_check")
        is_override = bool(latest_check and latest_check.get("human_override"))
        method_str = "Recruiter Manual Override" if is_override else (latest_check.get("backend") if latest_check else "Automated Check")

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                C.badges(
                    identity_status_badge("PASSED"),
                    backend_badge(method_str),
                    C.badge("Gate Clearance Granted", "success", dot=True),
                    C.badge(cand.get("job_title") or "Candidate", "neutral", dot=False)
                )
                st.markdown(f"### {cand.get('candidate_name') or f'Application #{app_id}'}")
            with col2:
                st.caption(f"App ID: **#{app_id}**")
                if cand.get("email"):
                    st.caption(f"Email: {cand.get('email')}")

            verified_time = H.fmt_dt(latest_check["timestamp"]) if latest_check else "-"
            conf_display = f"{latest_check.get('confidence', 0.0):.2f} (min: {latest_check.get('threshold', threshold):.2f})" if latest_check and not is_override else "Manual Pass"

            C.kv([
                ("Status", cand.get("application_status", "IDENTITY_PASSED")),
                ("Verified At", verified_time),
                ("Method", method_str),
                ("Confidence", conf_display),
                ("Clearance", "🔓 Gate Open - Ready for Interview")
            ])

            all_checks = cand.get("all_checks", [])
            if all_checks:
                with st.expander(f"View Check History ({len(all_checks)})", expanded=False):
                    identity_history_table(all_checks)


def render_resolved_audit(resolved_items):
    if not resolved_items:
        C.empty_state(
            "No Resolved Reviews Yet",
            "When recruiters resolve failed or inconclusive cases, detailed audit records and justifications will appear here."
        )
        return

    st.markdown(
        f"**Audit Trail: {len(resolved_items)} historical recruiter review decision{'s' if len(resolved_items) != 1 else ''}.**"
    )

    for item in resolved_items:
        res_key = item.get("resolution", "")
        res_label, res_tone = RESOLUTION_TONES.get(res_key, (res_key.replace("_", " ").title(), "neutral"))

        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                C.badges(
                    C.badge(res_label, res_tone),
                    C.badge(item.get("job_title") or "Candidate", "neutral", dot=False)
                )
                candidate_name = item.get("candidate_name") or f"Application #{item.get('application_id')}"
                st.markdown(f"### {candidate_name}")

            with col2:
                st.caption(f"Resolved: **{H.fmt_dt(item.get('resolved_at'))}**")
                st.caption(f"Review ID: #{item.get('id')}")

            C.kv([
                ("Application", f"#{item.get('application_id')}"),
                ("Original Flag Reason", item.get("reason", "-")),
                ("Decision", res_label),
                ("Resolved Timestamp", H.fmt_dt(item.get("resolved_at"))),
            ])

            notes_val = item.get("notes") or "No justification provided."
            st.markdown(
                f'<div class="iq-quote"><b>Mandatory Recruiter Justification:</b><br>{C.esc(notes_val)}</div>',
                unsafe_allow_html=True
            )

            all_checks = item.get("all_checks", [])
            if all_checks:
                with st.expander(f"Candidate Verification Check History ({len(all_checks)})", expanded=False):
                    identity_history_table(all_checks)


def identity_history_table(checks):
    if not checks:
        st.caption("No identity checks logged.")
        return

    rows = []
    for c in checks:
        is_pass = c.get("passed", False)
        is_inconcl = c.get("inconclusive", False)
        is_override = c.get("human_override", False)

        if is_override:
            res_b = C.badge("Manual Pass", "success") if is_pass else C.badge("Manual Decision", "neutral")
        elif is_pass:
            res_b = C.badge("Passed", "success")
        elif is_inconcl:
            res_b = C.badge("Inconclusive", "warning")
        else:
            res_b = C.badge("Failed", "error")

        rows.append({
            "t": H.fmt_dt(c.get("timestamp")),
            "type": (c.get("check_type") or "check").replace("_", " ").title(),
            "backend": c.get("backend", "-"),
            "faces": str(c.get("face_count", 0)),
            "conf": f"{c.get('confidence', 0.0):.2f} / {c.get('threshold', 0.0):.2f}" if not is_override else "-",
            "res": res_b,
            "why": c.get("reason", "-")
        })

    C.table([
        ("t", "Timestamp", "strong"),
        ("type", "Check Type"),
        ("backend", "Method"),
        ("faces", "Faces", "r"),
        ("conf", "Confidence / Threshold"),
        ("res", "Result"),
        ("why", "Reason / Explanation")
    ], rows)


identity_table = identity_history_table


