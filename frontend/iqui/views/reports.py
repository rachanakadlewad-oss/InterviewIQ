import json

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import identity_table

DECISION_OPTIONS = {
    "HIRE": ("Hire", "Advance candidate to offer or subsequent hiring stage."),
    "HOLD": ("Hold", "Place candidate on hold for further comparison or secondary review."),
    "REJECT": ("Reject", "Decline candidate application."),
}


def render():
    C.page_header(
        "Reports",
        "Review candidate performance across resume and interview dimensions, inspect competency evidence, and record your final hiring decision.",
        "Recruiter workspace"
    )

    job_id = api.job_picker()
    if not job_id:
        return

    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    if not apps:
        C.empty_state("No candidates for this job yet", "Upload resumes and screen candidates to view their evaluation reports.")
        return

    pick = st.selectbox(
        "Select Candidate",
        [a["application_id"] for a in apps],
        key="rep_pick",
        format_func=lambda i: next(
            f"{a['name'] or 'Candidate #' + str(a['application_id'])} — {H.status_label(a['status'])[0]} "
            f"(Score: {a.get('resume_score') or 0:.1f} / 10)"
            for a in apps if a["application_id"] == i
        )
    )

    rep = api.call("GET", f"/applications/{pick}/report")
    if not rep:
        C.empty_state("Could not load report", f"Report for application #{pick} could not be retrieved.")
        return

    job = api.call("GET", f"/jobs/{job_id}") or {"competencies": []}

    # Header with candidate info and workflow stepper
    header(rep)

    asm = rep.get("assessment")

    # Assessment failure retry handler
    if rep.get("assessment_error") or rep["status"] in ("ASSESSMENT_FAILED", "INTERVIEW_COMPLETE"):
        if rep.get("assessment_error"):
            C.callout("error", "Assessment Generation Issue", rep["assessment_error"])
        else:
            C.callout("info", "Interview Completed", "Interview has concluded and is ready for assessment generation.")
        c_ret, _ = st.columns([2, 3])
        with c_ret:
            if st.button("Generate / Retry Assessment", type="primary", key=f"btn_retry_asm_{pick}"):
                with st.spinner("Generating competency assessment..."):
                    if api.call("POST", f"/applications/{pick}/assessment/retry"):
                        api.flash("success", "Assessment Generated", "Assessment generated successfully.")
                        st.rerun()

    # Flow branching: before interview assessment vs after interview assessment
    if not asm:
        pending_interview_view(rep, pick, job)
    else:
        completed_report_view(rep, pick, job, asm)

    # Technical audit trail and data export kept cleanly in an expander at bottom
    with st.expander("Technical Audit Trail & Raw Report Export"):
        st.markdown("##### Turn-by-Turn Decision Trace")
        trace_tab(rep, job)
        if rep.get("identity_log"):
            st.markdown("##### Identity Verification Audit Trail")
            identity_table(rep["identity_log"])
        st.markdown("##### Export Report")
        st.download_button(
            "Download Full Report (JSON)",
            json.dumps(rep, indent=2, default=str),
            file_name=f"interviewiq_report_{pick}.json",
            mime="application/json"
        )


def header(rep):
    col1, col2 = st.columns([3.5, 1.5])
    with col1:
        st.markdown(f"### {rep['candidate'] or 'Application #' + str(rep['application_id'])}")
        bs = [
            C.status_badge(rep["status"]),
            C.badge(rep["job"] or "Position", "neutral", dot=False)
        ]
        rl, rt = H.source_label(rep["resume"]["source"])
        bs.append(C.badge(f"Resume: {rl}", rt, dot=False))
        if rep.get("assessment"):
            al, at = H.source_label(rep["assessment"]["source"])
            bs.append(C.badge(f"Interview: {al}", at, dot=False))
        C.badges(*bs)
    with col2:
        st.caption(f"Application: **#{rep['application_id']}**")
        if rep.get("email"):
            st.caption(f"Email: {rep['email']}")

    C.stepper(H.recruiter_workflow_steps(rep["status"]))


def pending_interview_view(rep, app_id, job):
    resume_score = rep["resume"]["score_0_100"] or 0.0
    cfg_weights = rep.get("configured_weights", {"resume": 0.4, "interview": 0.6})
    w_res = cfg_weights.get("resume", 0.4)
    w_int = cfg_weights.get("interview", 0.6)

    # 1. Scores Grid
    int_score_val = "Pending"
    int_score_hint = "Awaiting interview session"
    if rep["status"] == "INTERVIEW_COMPLETE":
        int_score_val = "Ready"
        int_score_hint = "Ready for assessment generation"
    elif rep["status"] == "ASSESSMENT_FAILED":
        int_score_val = "Needs Retry"
        int_score_hint = "Assessment failed - click retry below"

    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": int_score_val, "hint": int_score_hint},
        {"label": "Final Combined Score", "value": "Pending", "hint": f"Calculated after interview ({w_res*100:.0f}% / {w_int*100:.0f}%)"},
    ])

    # 2. Status message
    status_messages = {
        "SCORED": "Candidate is scored but not yet shortlisted or scheduled.",
        "SHORTLISTED": "Candidate is shortlisted. Waiting to be scheduled into an interview slot.",
        "SCHEDULED": "Candidate is scheduled for an interview slot. Identity verification and the interview session must be conducted before final scores are generated.",
        "HUMAN_REVIEW": "Candidate is currently flagged for Identity Review.",
        "IDENTITY_PASSED": "Identity verification has passed. Candidate is ready for the interview session.",
        "INTERVIEW_IN_PROGRESS": "The interview session is currently in progress.",
        "INTERVIEW_COMPLETE": "The candidate has completed their interview session. Click 'Generate Assessment' below to evaluate answers against competency rubrics.",
        "ASSESSMENT_FAILED": "Interview was completed, but automated assessment generation encountered an error. Click 'Retry Assessment' below to re-evaluate.",
        "REJECTED_AT_REVIEW": "Application was closed at identity review stage.",
    }
    explanation = status_messages.get(rep["status"], "Interview assessment has not been completed yet.")
    callout_tone = "error" if rep["status"] == "ASSESSMENT_FAILED" else ("warning" if rep["status"] == "INTERVIEW_COMPLETE" else "info")
    callout_title = "Assessment Ready to Generate" if rep["status"] in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED") else "Interview Assessment Pending"
    C.callout(callout_tone, callout_title, explanation)

    # 3. Interactive Action: Conduct Interview & Generate Assessment
    if rep["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS"):
        with st.container(border=True):
            st.markdown("#### Progress Candidate")
            st.write("Conduct the interview session and generate the competency assessment report.")
            col_act, _ = st.columns([2, 3])
            with col_act:
                if st.button("Conduct Interview & Generate Assessment", type="primary", use_container_width=True, key=f"btn_cond_{app_id}"):
                    with st.spinner("Conducting interview session and generating assessment..."):
                        res = api.call("POST", f"/applications/{app_id}/conduct-interview")
                        if res:
                            api.flash("success", "Workflow Advanced", "Interview completed and assessment generated successfully.")
                            st.rerun()
    elif rep["status"] in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED"):
        with st.container(border=True):
            st.markdown("#### Generate Candidate Assessment")
            st.write("The interview session has been recorded. Generate the competency assessment to score each skill area.")
            col_act, _ = st.columns([2, 3])
            with col_act:
                btn_lbl = "Retry Assessment Generation" if rep["status"] == "ASSESSMENT_FAILED" else "Generate Competency Assessment"
                if st.button(btn_lbl, type="primary", use_container_width=True, key=f"btn_run_asm_{app_id}"):
                    with st.spinner("Evaluating interview responses against job competencies..."):
                        res = api.call("POST", f"/applications/{app_id}/assessment/retry")
                        if res:
                            api.flash("success", "Assessment Completed", "Competency scores and candidate feedback generated successfully.")
                            st.rerun()

    profile_tab(rep)


def completed_report_view(rep, app_id, job, asm):
    resume_score = rep["resume"]["score_0_100"] or 0.0
    interview_score = asm.get("interview_score") or 0.0
    final_score = asm.get("final_score") or 0.0

    w = asm.get("weights") or rep.get("configured_weights") or {"resume": 0.4, "interview": 0.6}
    w_res = float(w.get("resume", 0.4))
    w_int = float(w.get("interview", 0.6))

    # 1. Score Cards
    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": f"{interview_score:.1f}", "hint": "All competencies evaluated · Out of 100"},
        {"label": "Final Combined Score", "value": f"{final_score:.1f}", "hint": f"Total combined out of 100"},
    ])

    # 2. Formula Breakdown Callout
    C.callout(
        "info",
        "Final Score Calculation",
        f"Combined Score = ({w_res*100:.0f}% × {resume_score:.1f} Resume) + ({w_int*100:.0f}% × {interview_score:.1f} Interview) = <b>{final_score:.1f} / 100</b>"
    )

    # 3. Organized Tabs
    tabs = st.tabs([
        "Executive Summary",
        "Competency Breakdown",
        "Interview Q&A Transcript",
        "Candidate Profile",
        "Candidate Feedback Preview"
    ])

    with tabs[0]:
        summary_tab(asm, rep)

    with tabs[1]:
        competency_tab(rep, asm, job)

    with tabs[2]:
        qa_transcript_tab(rep, job)

    with tabs[3]:
        profile_tab(rep)

    with tabs[4]:
        feedback_preview_tab(rep, asm)

    # 4. Recruiter's Final Hiring Decision Panel
    decision_panel(rep, app_id)


def summary_tab(asm, rep):
    label, tone = H.RECOMMENDATION.get(asm.get("label"), (asm.get("label", "Neutral"), "neutral"))

    with st.container(border=True):
        st.markdown("#### Evaluation Recommendation & Rationale")
        C.badges(C.badge(label, tone))
        if asm.get("recommendation_rationale"):
            st.write(asm.get("recommendation_rationale"))
        st.caption("Advisory recommendation based on verified candidate competencies.")

    with st.container(border=True):
        st.markdown("#### Executive Summary")
        st.write(asm.get("recruiter_summary", "No summary provided."))

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("#### Key Strengths")
            for s in asm.get("strengths", []):
                st.markdown(f"• {s}")
    with c2:
        with st.container(border=True):
            st.markdown("#### Areas for Growth")
            for w in asm.get("weaknesses", []):
                st.markdown(f"• {w}")


def competency_tab(rep, asm, job):
    table = asm.get("competency_table", [])
    if not table:
        C.empty_state("No Competency Table Available")
        return

    C.table(
        [("name", "Competency", "strong"), ("weight", "Weight"), ("resume", "Resume Score"), ("interview", "Interview Score"), ("status", "Evidence Status")],
        [{"name": row["name"], "weight": f"{row['weight']:.1f}x",
          "resume": f"{row['resume_score']:.1f} / 10" if row.get("resume_score") is not None else "-",
          "interview": f"{row['interview_score']:.1f} / 10" if row.get("interview_score") is not None else "Not assessed",
          "status": C.badge("Direct Evidence", "success") if (row.get("interview_score") or 0) >= 6 else (C.badge("Partial", "warning") if row.get("interview_score") else C.badge("Pending", "neutral"))}
         for row in table]
    )

    st.markdown("#### Verbatim Interview Citations by Competency")
    for row in table:
        with st.expander(f"{row['name']} — Interview Score: {row.get('interview_score') or 'N/A'}/10"):
            st.markdown(f"**Assessor Rationale:** {row.get('interview_rationale', '')}")
            ev = row.get("interview_evidence", [])
            if ev:
                st.markdown("**Verbatim Excerpts:**")
                for quote in ev:
                    C.quote(quote)
            else:
                st.caption("No specific verbatim quote cited for this competency.")


def qa_transcript_tab(rep, job):
    transcript = rep.get("transcript", [])
    if not transcript:
        C.empty_state("No Transcript Available", "Interview transcript was not recorded or interview is pending.")
        return

    st.markdown(f"**Total Conversation Turns:** {len(transcript)}")
    for turn in transcript:
        role = turn.get("role", "assistant")
        text = turn.get("text", "")
        comp = turn.get("competency", "")
        with st.chat_message("assistant" if role == "interviewer" else "user"):
            if comp:
                st.caption(f"Topic: {comp}")
            st.write(text)


def feedback_preview_tab(rep, asm):
    fb = asm.get("candidate_feedback")
    if not fb:
        C.empty_state("Candidate Feedback Not Available", "Candidate feedback has not been compiled yet.")
        return

    st.markdown("#### Candidate Feedback Portal Preview")
    st.caption("This is the exact constructive feedback displayed to the candidate in their Candidate Portal (private scores and rankings are excluded).")

    with st.container(border=True):
        st.markdown("**Feedback Summary:**")
        st.write(fb.get("summary", ""))

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**Strengths Recognized:**")
            for s in fb.get("strengths", []):
                st.markdown(f"• {s}")
    with c2:
        with st.container(border=True):
            st.markdown("**Areas for Improvement:**")
            for w in fb.get("weaknesses", []):
                st.markdown(f"• {w}")

    if fb.get("improvement_areas"):
        with st.container(border=True):
            st.markdown("**Recommended Practice Areas:**")
            for imp in fb.get("improvement_areas", []):
                st.markdown(f"• {imp}")


def profile_tab(rep):
    p = rep.get("profile", {})
    with st.container(border=True):
        st.markdown("#### Parsed Resume Profile")
        C.kv([
            ("Candidate Name", p.get("name")),
            ("Email", p.get("email")),
            ("Phone", p.get("phone")),
            ("Experience (Years)", str(p.get("experience_years", "Not stated"))),
        ])
        if p.get("skills"):
            st.markdown("##### Extracted Skills")
            C.badges(*[C.badge(s, "neutral", dot=False) for s in p["skills"]])
        if p.get("experience"):
            st.markdown("##### Professional Experience")
            for ex in p["experience"]:
                C.quote(ex)
        if p.get("projects"):
            st.markdown("##### Projects")
            for pr in p["projects"]:
                C.quote(pr)
        if p.get("education"):
            st.markdown("##### Education")
            for ed in p["education"]:
                C.quote(ed)


def trace_tab(rep, job):
    traces = rep.get("trace", [])
    if not traces:
        st.caption("No decision trace recorded.")
        return
    for t in traces:
        with st.container(border=True):
            st.markdown(f"**Turn {t.get('turn', 0)}:** Decision `{t.get('decision')}` (Source: `{t.get('source')}`)")
            st.write(f"Reasoning: {t.get('reasoning')}")
            if t.get("trigger_phrase"):
                st.caption(f"Trigger: \"{t.get('trigger_phrase')}\"")
            if t.get("guard_note"):
                st.caption(f"Supervisor Guard Note: {t.get('guard_note')}")


def decision_panel(rep, app_id):
    st.markdown("---")
    st.markdown("### Recruiter Hiring Decision")
    dec_info = rep.get("recruiter_decision")

    if dec_info:
        st.markdown(
            f'<div class="iq-callout success">'
            f'<div><div class="t">Decision Recorded: {dec_info["decision"]}</div>'
            f'<div class="b">Notes: {dec_info.get("notes") or "None"}<br>'
            f'Recorded At: {H.fmt_dt(dec_info.get("at"))}</div></div></div>',
            unsafe_allow_html=True
        )

    with st.form(f"decision_form_{app_id}"):
        dec = st.selectbox(
            "Final Decision",
            list(DECISION_OPTIONS.keys()),
            format_func=lambda k: f"{k} - {DECISION_OPTIONS[k][0]} ({DECISION_OPTIONS[k][1]})",
            index=0 if not dec_info else list(DECISION_OPTIONS.keys()).index(dec_info["decision"]) if dec_info["decision"] in DECISION_OPTIONS else 0
        )
        notes = st.text_area("Decision Notes & Offer Recommendation", value=dec_info.get("notes", "") if dec_info else "", placeholder="Justification for hiring decision...")
        sub = st.form_submit_button("Record Final Decision", type="primary")

    if sub:
        ok, res = api.request("POST", f"/applications/{app_id}/decision", json={"decision": dec, "notes": notes.strip()})
        if ok:
            api.flash("success", "Decision Recorded", f"Final decision '{dec}' successfully saved for application #{app_id}.")
            st.rerun()
        else:
            C.callout("error", "Failed to record decision", res)
