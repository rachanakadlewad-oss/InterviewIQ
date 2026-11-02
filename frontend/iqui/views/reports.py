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
        "Interview Reports & Decisions",
        "Review candidate performance across resume and interview dimensions, inspect verification and decision evidence, and record the final hiring decision.",
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
            f"{a['name'] or 'Candidate #' + str(a['application_id'])} - {H.status_label(a['status'])[0]} "
            f"(Resume: {a.get('resume_score') or 0:.0f}/100)"
            for a in apps if a["application_id"] == i
        )
    )

    rep = api.call("GET", f"/applications/{pick}/report")
    if not rep:
        C.empty_state("Could not load report", f"Report for application #{pick} could not be retrieved.")
        return

    job = api.call("GET", f"/jobs/{job_id}") or {"competencies": []}

    # Header with candidate info and 6-stage workflow stepper
    header(rep)

    asm = rep.get("assessment")

    # Assessment failure retry handler
    if rep.get("assessment_error"):
        C.callout("error", "The Assessment Agent failed for this interview", rep["assessment_error"])
        if st.button("Retry assessment", type="primary"):
            if api.call("POST", f"/applications/{pick}/assessment/retry"):
                api.flash("success", "Assessment retried", "Assessment rerun successfully.")
                st.rerun()

    # Flow branching: before interview assessment vs after interview assessment
    if not asm:
        pending_interview_view(rep, pick, job)
    else:
        completed_report_view(rep, pick, job, asm)

    st.markdown("---")
    st.download_button(
        "Download Full Report (JSON)",
        json.dumps(rep, indent=2, default=str),
        file_name=f"interviewiq_report_{pick}.json",
        mime="application/json"
    )


def header(rep):
    col1, col2 = st.columns([3, 1])
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
        st.caption(f"App ID: **#{rep['application_id']}**")
        if rep.get("email"):
            st.caption(f"Email: {rep['email']}")

    # 6-Stage Workflow Progress Stepper
    st.markdown("##### Assessment Workflow Pipeline")
    C.stepper(H.recruiter_workflow_steps(rep["status"]))

    if rep.get("llm_mode") == "demo":
        C.callout(
            "warning",
            "Demo Mode Pipeline Active",
            "Resume and interview evaluations in this demo environment run via deterministic rules and heuristics. Real LLM assessment requires configured API credentials."
        )


def pending_interview_view(rep, app_id, job):
    resume_score = rep["resume"]["score_0_100"] or 0.0
    cfg_weights = rep.get("configured_weights", {"resume": 0.4, "interview": 0.6})
    w_res = cfg_weights.get("resume", 0.4)
    w_int = cfg_weights.get("interview", 0.6)

    # 1. Scores Grid: Real resume score, pending interview score (no fake scores!)
    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": "Pending", "hint": "Awaiting interview session"},
        {"label": "Final Weighted Score", "value": "Pending", "hint": f"Calculated after interview assessment"},
    ])

    # 2. Configured Formula Banner
    st.markdown(
        f'<div class="iq-callout info" style="margin-top:0.6rem;margin-bottom:1.2rem;">'
        f'<div><div class="t">Configured Scoring Formula</div>'
        f'<div class="b"><b>Final Score = (Resume Weight × Resume Score) + (Interview Weight × Interview Score)</b><br>'
        f'= ({w_res:.2f} × {resume_score:.1f}) + ({w_int:.2f} × Interview Score)<br>'
        f'<i>Interview score and final score will be calculated once the interview is conducted.</i>'
        f'</div></div></div>',
        unsafe_allow_html=True
    )

    # 3. Status explanation
    status_messages = {
        "SCORED": "Candidate is scored but not yet shortlisted or scheduled.",
        "SHORTLISTED": "Candidate is shortlisted. Waiting to be scheduled into an interview slot.",
        "SCHEDULED": "Candidate is scheduled for an interview slot. Identity verification and the interview session must be conducted before interview assessment and final scores are generated.",
        "HUMAN_REVIEW": "Candidate is currently blocked in Identity Review queue.",
        "IDENTITY_PASSED": "Identity verification has passed. Candidate is ready for the interview session.",
        "INTERVIEW_IN_PROGRESS": "The interview session is currently in progress.",
        "REJECTED_AT_REVIEW": "Application was closed at identity review stage.",
    }
    explanation = status_messages.get(rep["status"], "Interview assessment has not been completed yet.")
    C.callout("info", "No Interview Assessment Yet", explanation)

    # 4. Interactive Action: Conduct Interview & Generate Assessment
    if rep["status"] in ("SCHEDULED", "IDENTITY_PASSED", "INTERVIEW_IN_PROGRESS"):
        with st.container(border=True):
            st.markdown("#### Advance Candidate Workflow")
            st.write(
                "Progress this candidate through identity verification, conduct the interview session with planned job competencies, "
                "and generate the competency assessment report."
            )
            col_act, _ = st.columns([2, 3])
            with col_act:
                if st.button("Conduct Interview & Generate Assessment", type="primary", use_container_width=True):
                    with st.spinner("Conducting interview session and generating assessment..."):
                        res = api.call("POST", f"/applications/{app_id}/conduct-interview")
                        if res:
                            api.flash("success", "Workflow Advanced", "Interview completed and assessment generated successfully.")
                            st.rerun()

    # 5. Inspection tabs for pre-interview candidate details
    tabs = st.tabs(["Resume Profile & Information", "Identity Check History"])
    with tabs[0]:
        profile_tab(rep)
    with tabs[1]:
        if rep.get("identity_log"):
            identity_table(rep["identity_log"])
        else:
            C.empty_state("No Identity Checks Yet", "Identity checks will appear here once candidate undertakes verification.")


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
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": f"{interview_score:.1f}", "hint": "Planned competencies assessed · Out of 100"},
        {"label": "Final Weighted Score", "value": f"{final_score:.1f}", "hint": f"Combined total out of 100"},
    ])

    # 2. Configured Formula Breakdown Banner
    st.markdown(
        f'<div class="iq-callout info" style="margin-top:0.6rem;margin-bottom:1.2rem;">'
        f'<div><div class="t">Final Score Calculation Formula</div>'
        f'<div class="b"><b>Final Score = (Resume Weight × Resume Score) + (Interview Weight × Interview Score)</b><br>'
        f'= ({w_res:.2f} × {resume_score:.1f}) + ({w_int:.2f} × {interview_score:.1f}) = <b>{final_score:.1f} / 100</b>'
        f'</div></div></div>',
        unsafe_allow_html=True
    )

    # 3. Organized Tabs
    tabs = st.tabs([
        "Executive Summary",
        "Competency Performance",
        "Interview Q&A & Transcript",
        "Decision Trace",
        "Candidate Profile & Resume",
        "Identity Verification"
    ])

    with tabs[0]:
        summary_tab(asm, rep)

    with tabs[1]:
        competency_tab(rep, asm, job)

    with tabs[2]:
        qa_transcript_tab(rep, job)

    with tabs[3]:
        trace_tab(rep, job)

    with tabs[4]:
        profile_tab(rep)

    with tabs[5]:
        if rep.get("identity_log"):
            identity_table(rep["identity_log"])
        else:
            C.empty_state("No Identity Checks Logged")

    # 4. Recruiter's Final Hiring Decision Panel
    decision_panel(rep, app_id)


def summary_tab(asm, rep):
    is_real_llm = rep.get("llm_mode") != "demo" and asm.get("source") != "demo_rules"
    label, tone = H.RECOMMENDATION.get(asm.get("label"), (asm.get("label", "Neutral"), "neutral"))

    # Requirement 9: AI recommendation ONLY when actual LLM assessment is configured
    if is_real_llm:
        with st.container(border=True):
            st.markdown("#### AI Recommendation (Advisory Only)")
            C.badges(C.badge(label, tone))
            st.write(asm.get("recommendation_rationale", ""))
            st.caption("AI-generated assessment recommendation based on interview evidence. Advisory only.")
    else:
        with st.container(border=True):
            st.markdown("#### Advisory Score Benchmark (Rule-Based Cutoff - Demo Rules)")
            C.badges(C.badge(label, tone, dot=False))
            st.write(asm.get("recommendation_rationale", ""))
            st.caption("⚠️ Real LLM assessment is not active. This benchmark is derived from deterministic score cutoffs, NOT AI reasoning.")

    C.callout(
        "neutral",
        "Recruiter Authority Principle",
        "The recruiter always retains final hiring authority. All recommendations and benchmarks remain non-binding decision support."
    )

    st.markdown("#### Assessment Summary")
    st.write(asm.get("recruiter_summary", "No recruiter summary available."))

    col_s, col_w = st.columns(2)
    with col_s:
        st.markdown("**Demonstrated Strengths**")
        for s in asm.get("strengths") or ["None highlighted"]:
            st.markdown(f"- {s}")
    with col_w:
        st.markdown("**Weaknesses & Gaps**")
        for w in asm.get("weaknesses") or ["None highlighted"]:
            st.markdown(f"- {w}")

    # Competency gaps / unassessed warnings
    gaps = [r["name"] for r in asm.get("competency_table", []) if r.get("interview_score") is None]
    if gaps:
        C.callout(
            "info",
            "Competencies Not Covered in Interview",
            "The interview probed highest-priority planned competencies. These were scored from resume only: " +
            ", ".join(gaps) + ". Their weight is excluded from interview score."
        )

    for f in asm.get("flags", []):
        tone = "warning" if "DEMO" in f or "NOT assessed" in f else "info"
        C.callout(tone, f)


def competency_tab(rep, asm, job):
    rs = {s["competency_id"]: s for s in rep.get("resume", {}).get("per_competency", [])}
    rows = asm.get("competency_table", []) if asm else []

    if not rows and job.get("competencies"):
        rows = [
            {"competency_id": c["id"], "name": c["name"], "weight": c["weight"],
             "resume_score": rs.get(c["id"], {}).get("score"), "interview_score": None,
             "interview_evidence": [], "interview_rationale": "Not assessed in interview."}
            for c in job["competencies"]
        ]

    # Competency Table
    table_rows = []
    for r in rows:
        table_rows.append({
            "name": r["name"],
            "weight": f"{r['weight']:.1f}",
            "resume": C.score_bar(r.get("resume_score")),
            "interview": C.score_bar(r.get("interview_score")),
            "rating": "Strong" if (r.get("interview_score") or 0) >= 7.0 else (
                "Moderate" if (r.get("interview_score") or 0) >= 5.0 else (
                    "Limited" if r.get("interview_score") is not None else "Resume Only"
                )
            )
        })

    C.table([
        ("name", "Competency", "strong"),
        ("weight", "Weight", "r"),
        ("resume", "Resume (0-10)"),
        ("interview", "Interview (0-10)"),
        ("rating", "Performance Band")
    ], table_rows)

    st.markdown("---")
    st.markdown("#### Detailed Competency Evidence & Evaluations")

    for r in rows:
        with st.expander(f"{r['name']} (Weight: {r['weight']:.1f})", expanded=False):
            st.markdown("**Resume Evidence & Justification**")
            s = rs.get(r["competency_id"])
            if s and s.get("evidence"):
                st.caption(s.get("justification", ""))
                for e in s.get("evidence", []):
                    C.quote(e)
            else:
                st.caption("No direct resume evidence found.")

            st.markdown("**Interview Evidence & Evaluation Rationale**")
            if r.get("interview_evidence"):
                st.caption(f"**Rationale:** {r.get('interview_rationale', '')}")
                st.markdown("**Candidate Interview Quotes:**")
                for e in r.get("interview_evidence", []):
                    C.quote(e)
            else:
                st.caption("Not assessed in the interview." if r.get("interview_score") is None else r.get("interview_rationale", ""))

    for x in (asm or {}).get("extra_competencies_explored", []):
        comp_name = x['competency_id'].replace('extra_', '').replace('_', ' ').title()
        C.callout(
            "success",
            f"Unplanned Competency Explored: {comp_name}",
            f"Opened by a BROAD_PIVOT from candidate answer. Score {x['score']:.1f}/10 (reported separately, not part of core weighted score). {x['rationale']}"
        )


def qa_transcript_tab(rep, job):
    transcript = rep.get("transcript") or []
    if not transcript:
        C.empty_state("No Interview Transcript", "Conversation records will appear here once the interview starts.")
        return

    # 1. Paired Questions & Candidate Responses
    st.markdown("#### Interview Questions & Candidate Responses")
    pairs = []
    i = 0
    while i < len(transcript):
        t = transcript[i]
        if t.get("role") == "interviewer":
            q_text = t.get("text", "")
            comp_id = t.get("competency", "")
            ans_text = ""
            if i + 1 < len(transcript) and transcript[i + 1].get("role") == "candidate":
                ans_text = transcript[i + 1].get("text", "")
                i += 2
            else:
                i += 1
            pairs.append((len(pairs) + 1, comp_id, q_text, ans_text))
        else:
            i += 1

    for q_num, comp_id, q_text, ans_text in pairs:
        comp_label = comp_id.replace("_", " ").title() if comp_id else "General"
        with st.container(border=True):
            col_q, col_badge = st.columns([4, 1])
            with col_q:
                st.markdown(f"**Question {q_num}:** {q_text}")
            with col_badge:
                C.badge(comp_label, "info", dot=False)

            if ans_text:
                st.markdown(
                    f'<div style="background:rgba(22,119,255,0.04);border-left:3px solid var(--primary);'
                    f'padding:0.7rem 1rem;border-radius:4px;margin-top:0.5rem;">'
                    f'<b>Candidate Response:</b><br>{C.esc(ans_text)}</div>',
                    unsafe_allow_html=True
                )
            else:
                st.caption("No response recorded.")

    st.markdown("---")
    st.markdown("#### Full Chronological Chat Transcript")
    for t in transcript:
        with st.chat_message("assistant" if t.get("role") == "interviewer" else "user"):
            st.write(t.get("text", ""))


def trace_tab(rep, job):
    traces = rep.get("trace") or []
    if not traces:
        C.empty_state("No Decision Trace Yet", "Turn-by-turn interviewer decisions appear once the interview starts.")
        return

    st.caption("Each turn records what the candidate said that triggered the decision, the evaluator rationale, and the question asked.")
    names = {c["id"]: c["name"] for c in job.get("competencies", [])}
    C.trace(traces, names)


def profile_tab(rep):
    p = rep.get("profile") or {}
    C.kv([
        ("Candidate Name", p.get("name")),
        ("Email Address", p.get("email")),
        ("Experience (years)", p.get("experience_years") or "Not stated")
    ])

    if p.get("skills"):
        st.markdown("**Skills Extracted From Resume**")
        C.badges(*[C.badge(s, "neutral", dot=False) for s in p["skills"]])

    if p.get("experience"):
        st.markdown("**Experience & Roles**")
        for ex in p["experience"]:
            C.quote(ex)

    if p.get("projects"):
        st.markdown("**Projects & Deliverables**")
        for pr in p["projects"]:
            C.quote(pr)

    if p.get("education"):
        st.markdown("**Education**")
        for ed in p["education"]:
            C.quote(ed)

    if p.get("summary"):
        st.markdown("**Professional Summary**")
        C.quote(p["summary"])


def decision_panel(rep, app_id):
    st.markdown("---")
    C.section(
        "Recruiter Final Hiring Decision",
        "The recruiter always retains final hiring authority. AI recommendations remain advisory decision support."
    )

    d = rep.get("recruiter_decision")
    if d:
        dec_name = d.get("decision", "").upper()
        if dec_name == "ADVANCE":
            dec_name = "HIRE"
        tone = {"HIRE": "success", "HOLD": "warning", "REJECT": "error"}.get(dec_name, "neutral")
        label_text = DECISION_OPTIONS.get(dec_name, (dec_name.title(), ""))[0]
        C.callout(
            tone,
            f"Recorded Hiring Decision: {label_text.upper()}",
            f"**Notes:** {d.get('notes') or 'No notes recorded.'}\n\n**Decided At:** {H.fmt_dt(d.get('at'))}"
        )

    if rep.get("status") not in ("ASSESSED", "DECIDED"):
        C.callout("info", "Decision Locked", "Final decision can be recorded once the candidate interview has been assessed.")
        return

    default_choice = "HIRE"
    if d:
        prev = d.get("decision", "HIRE").upper()
        default_choice = "HIRE" if prev in ("HIRE", "ADVANCE") else prev

    choice = st.radio(
        "Select Hiring Decision",
        list(DECISION_OPTIONS.keys()),
        index=list(DECISION_OPTIONS.keys()).index(default_choice) if default_choice in DECISION_OPTIONS else 0,
        format_func=lambda k: f"{DECISION_OPTIONS[k][0]} - {DECISION_OPTIONS[k][1]}",
        horizontal=False,
        key=f"dec_choice_{app_id}"
    )

    notes = st.text_area(
        "Recruiter Decision Notes / Justification *",
        value=d.get("notes", "") if d else "",
        placeholder="Provide your rationale for hiring, holding, or rejecting this candidate. This note is permanently stored in the hiring audit record.",
        key=f"decn_{app_id}"
    )

    col_btn, _ = st.columns([2, 3])
    with col_btn:
        btn_label = "Update Hiring Decision" if d else "Record Hiring Decision"
        if st.button(btn_label, type="primary", key=f"decb_{app_id}", use_container_width=True):
            if not notes.strip():
                C.callout("error", "Decision Notes Required", "Please provide a brief justification for your hiring decision.")
            else:
                res = api.call("POST", f"/applications/{app_id}/decision", json={"decision": choice, "notes": notes.strip()})
                if res:
                    api.flash("success", "Decision Recorded", f"Hiring decision '{DECISION_OPTIONS[choice][0]}' saved successfully.")
                    st.rerun()
