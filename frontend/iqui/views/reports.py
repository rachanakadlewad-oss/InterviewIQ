import json
import re
from typing import Dict, List, Optional

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import identity_table

DECISION_OPTIONS = {
    "HIRE": ("Hire", "Advance candidate to offer or subsequent hiring stage."),
    "HOLD": ("Hold", "Place candidate on hold for further comparison or secondary review."),
    "REJECT": ("Reject", "Decline candidate application."),
}

REPORTS_CSS = """
<style>
/* Hero Assessment Dossier */
.iq-report-hero {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.5rem 1.75rem;
  margin: 1.25rem 0 1.75rem;
  box-shadow: var(--shadow-sm);
}

.iq-report-rec-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  padding-bottom: 1.1rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 1.1rem;
}

.iq-report-rec-title {
  font-size: 1.05rem;
  font-weight: 650;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.iq-report-rec-note {
  font-size: 0.85rem;
  color: var(--muted);
}

.iq-report-rationale-box {
  background: rgba(37, 99, 235, 0.05);
  border-left: 3px solid var(--primary);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  padding: 0.9rem 1.15rem;
  margin-bottom: 1.15rem;
  font-size: 0.92rem;
  color: var(--text);
  line-height: 1.6;
}

.iq-report-summary-box {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1.1rem 1.25rem;
  margin-bottom: 1.25rem;
}

.iq-report-summary-title {
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin-bottom: 0.5rem;
}

.iq-report-summary-text {
  font-size: 0.93rem;
  color: var(--text);
  line-height: 1.65;
}

.iq-report-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1.25rem;
}

@media (max-width: 768px) {
  .iq-report-grid {
    grid-template-columns: 1fr;
  }
}

.iq-report-col {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 1.1rem 1.25rem;
}

.iq-report-col-header {
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.75rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.iq-report-col.strengths .iq-report-col-header {
  color: var(--success);
}

.iq-report-col.growth .iq-report-col-header {
  color: var(--warning);
}

.iq-report-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.iq-report-list li {
  font-size: 0.91rem;
  line-height: 1.55;
  color: var(--text2);
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
}

.iq-report-list li i {
  font-style: normal;
  font-weight: 700;
  font-size: 0.95rem;
  line-height: 1.35;
  flex-shrink: 0;
}

.iq-report-col.strengths .iq-report-list li i {
  color: var(--success);
}

.iq-report-col.growth .iq-report-list li i {
  color: var(--warning);
}

.iq-report-empty-note {
  font-size: 0.91rem;
  line-height: 1.55;
  color: var(--muted);
  font-style: italic;
  padding: 0.35rem 0;
}

/* Secondary Tab & Expander Polish */
.iq-citation-rationale {
  font-size: 0.92rem;
  line-height: 1.6;
  color: var(--text);
  margin-bottom: 0.75rem;
}

.iq-detail-section-title {
  font-size: 0.82rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--muted);
  margin: 0.75rem 0 0.4rem;
}
</style>
"""


# ==============================================================================
# RECRUITER-FRIENDLY WORDING HELPERS (PURE)
# ==============================================================================
def clean_demo_wording(text: str) -> str:
    """Strip technical demo-mode boilerplate while preserving the substantive rationale."""
    if not text:
        return ""
    t = text
    t = re.sub(r"\s*\(demo\s+heuristic\)\.?\s*", ". ", t, flags=re.IGNORECASE)
    t = re.sub(r"\[Demo\s+Heuristic\s*-\s*[^\]]+\]\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bDemo-mode\s+heuristic\s+assessment\b", "Candidate evaluation", t, flags=re.IGNORECASE)
    t = re.sub(r"\bheuristic\s+assessment\b", "evaluation", t, flags=re.IGNORECASE)
    t = re.sub(r"\bDemo\s+heuristic\s+scoring[;:]?\s*", "Evaluation ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*\.\s*\.", ".", t)
    return t.strip()


def format_recruiter_summary(summary: Optional[str], strengths: List[str], weaknesses: List[str], table: List[dict]) -> str:
    """Format technical demo-mode wording into clear, recruiter-friendly executive summary text.
    Dynamically accounts for any number of competencies, strengths, and growth areas across all candidates."""
    assessed = [row for row in table if row.get("interview_score") is not None]
    n_assessed = len(assessed) if assessed else len(table)
    n_total = len(table)

    s_count = len(strengths)
    w_count = len(weaknesses)

    # Detect the standard demo-mode summary pattern:
    # "Demo-mode heuristic assessment of X competencies. Strengths: Y, weaknesses: Z. Review the evidence excerpts before deciding."
    pattern = r"demo-mode\s+heuristic\s+assessment\s+of\s+(\d+)\s+competencies(?:\.\s*Strengths:\s*(\d+),\s*weaknesses:\s*(\d+))?"
    match = re.search(pattern, summary or "", re.IGNORECASE)
    if match:
        n_comps = match.group(1) or str(n_assessed)
        if match.group(2) is not None:
            s_count = int(match.group(2))
        if match.group(3) is not None:
            w_count = int(match.group(3))

        s_phrase = f"{s_count} demonstrated strength{'s' if s_count != 1 else ''}"
        if w_count == 0:
            w_phrase = "no critical competency gaps"
        else:
            w_phrase = f"{w_count} area{'s' if w_count != 1 else ''} for growth"

        scope_str = f"{n_comps} core competencies"
        if n_total > int(n_comps):
            scope_str += f" ({n_total} total in job profile)"

        return (
            f"Evaluation completed across {scope_str}, identifying {s_phrase} and {w_phrase}. "
            "Review the detailed competency evidence below before making your hiring decision."
        )

    # Handle missing or empty summary
    if not summary:
        s_phrase = f"{s_count} demonstrated strength{'s' if s_count != 1 else ''}"
        w_phrase = f"{w_count} area{'s' if w_count != 1 else ''} for growth" if w_count > 0 else "no critical competency gaps"
        return (
            f"Evaluation completed across {n_assessed} core competencies, identifying {s_phrase} and {w_phrase}. "
            "Review the detailed competency breakdown and citations below before recording your decision."
        )

    # For real LLM assessments or other summaries, clean any stray technical terminology
    return clean_demo_wording(summary)


# ==============================================================================
# MAIN VIEW RENDER
# ==============================================================================
def render():
    st.markdown(REPORTS_CSS, unsafe_allow_html=True)
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

    # 1. Candidate Selection
    col_sel, col_stat = st.columns([3.5, 1.5], vertical_alignment="center")
    with col_sel:
        pick = st.selectbox(
            "Select Candidate",
            [a["application_id"] for a in apps],
            key="rep_pick",
            format_func=lambda i: next(
                f"{a['name'] or 'Candidate #' + str(a['application_id'])} — {H.status_label(a['status'])[0]} "
                f"(Resume: {a.get('resume_score') or 0:.1f} / 10)"
                for a in apps if a["application_id"] == i
            )
        )
    with col_stat:
        st.caption(f"**{len(apps)}** candidate(s) in position pipeline")

    rep = api.call("GET", f"/applications/{pick}/report")
    if not rep:
        C.empty_state("Could not load report", f"Report for application #{pick} could not be retrieved.")
        return

    job = api.call("GET", f"/jobs/{job_id}") or {"competencies": []}

    # 2. Header with candidate metadata and pipeline stage
    header(rep)

    asm = rep.get("assessment")

    # Assessment failure / retry notification
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

    # Flow branching: pending interview vs completed assessment report
    if not asm:
        pending_interview_view(rep, pick, job)
    else:
        completed_report_view(rep, pick, job, asm)

    # Technical audit trail and data export cleanly accessible at bottom
    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)
    with st.expander("Technical Audit Trail & Report Export", expanded=False):
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
    col1, col2 = st.columns([3.5, 1.5], vertical_alignment="center")
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


# ==============================================================================
# PENDING INTERVIEW VIEW
# ==============================================================================
def pending_interview_view(rep, app_id, job):
    resume_score = rep["resume"]["score_0_100"] or 0.0
    cfg_weights = rep.get("configured_weights", {"resume": 0.4, "interview": 0.6})
    w_res = cfg_weights.get("resume", 0.4)
    w_int = cfg_weights.get("interview", 0.6)

    int_score_val = "Pending"
    int_score_hint = "Awaiting interview session"
    if rep["status"] == "INTERVIEW_COMPLETE":
        int_score_val = "Ready"
        int_score_hint = "Ready for assessment generation"
    elif rep["status"] == "ASSESSMENT_FAILED":
        int_score_val = "Needs Retry"
        int_score_hint = "Assessment failed - click retry below"

    # Score Metrics
    st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
    C.metric_grid([
        {"label": f"Resume Score ({w_res * 100:.0f}%)", "value": f"{resume_score:.1f}", "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"},
        {"label": f"Interview Score ({w_int * 100:.0f}%)", "value": int_score_val, "hint": int_score_hint},
        {"label": "Final Combined Score", "value": "Pending", "hint": f"Calculated after interview ({w_res*100:.0f}% / {w_int*100:.0f}%)"},
    ])

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

    # Action to progress interview
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

    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    with st.expander("Parsed Resume Profile", expanded=False):
        profile_tab(rep)


# ==============================================================================
# COMPLETED REPORT VIEW
# ==============================================================================
def completed_report_view(rep, app_id, job, asm):
    resume_score = rep["resume"]["score_0_100"] or 0.0
    interview_score = asm.get("interview_score")
    final_score = asm.get("final_score") or 0.0

    w = asm.get("weights") or rep.get("configured_weights") or {"resume": 0.4, "interview": 0.6}
    w_res = float(w.get("resume", 0.4))
    w_int = float(w.get("interview", 0.6))

    # 1. Score Metrics
    st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
    int_score_val = f"{interview_score:.1f}" if interview_score is not None else "Not assessed"
    C.metric_grid([
        {
            "label": f"Resume Score ({w_res * 100:.0f}%)",
            "value": f"{resume_score:.1f}",
            "hint": f"Rank #{rep['resume']['rank'] or '-'} · Out of 100"
        },
        {
            "label": f"Interview Score ({w_int * 100:.0f}%)",
            "value": int_score_val,
            "hint": "All competencies evaluated · Out of 100"
        },
        {
            "label": "Final Combined Score",
            "value": f"{final_score:.1f}",
            "hint": f"Combined ({w_res*100:.0f}% Resume + {w_int*100:.0f}% Interview)",
            "tone": "success" if final_score >= 70 else ("warning" if final_score >= 50 else "error")
        },
    ])

    # 2. Final Score Calculation (clean text, no HTML tags)
    if interview_score is not None:
        calc_text = (
            f"Combined Score = ({w_res * 100:.0f}% × {resume_score:.1f} Resume) + "
            f"({w_int * 100:.0f}% × {interview_score:.1f} Interview) = {final_score:.1f} / 100"
        )
    else:
        calc_text = f"Combined Score = Resume Score only ({resume_score:.1f} / 100) — Interview session unassessed"

    clean_calc = re.sub(r"<[^>]+>", "", calc_text)
    C.callout("info", "Final Score Calculation", clean_calc)

    # 3. Overall Candidate Assessment & AI Recommendation
    rec_label, rec_tone = H.RECOMMENDATION.get(asm.get("label"), (asm.get("label", "Neutral"), "neutral"))
    rationale_raw = asm.get("recommendation_rationale")
    if rationale_raw:
        rationale_text = clean_demo_wording(rationale_raw)
    else:
        rationale_text = "Advisory recommendation derived from weighted resume and interview competency scores. Final hiring decision rests with the recruiter."

    comp_table = asm.get("competency_table", [])
    summary_raw = asm.get("recruiter_summary", "")
    summary_text = format_recruiter_summary(summary_raw, asm.get("strengths", []), asm.get("weaknesses", []), comp_table)

    strengths = asm.get("strengths", [])
    weaknesses = asm.get("weaknesses", [])

    if strengths:
        strengths_content = (
            '<ul class="iq-report-list">' +
            "".join(f"<li><i>✓</i><span>{C.esc(s)}</span></li>" for s in strengths) +
            '</ul>'
        )
    else:
        strengths_content = (
            '<div class="iq-report-empty-note">'
            'Candidate engaged with all interview questions; no standout strengths were specifically flagged above baseline. Review the detailed competency scores below.'
            '</div>'
        )

    if weaknesses:
        growth_content = (
            '<ul class="iq-report-list">' +
            "".join(f"<li><i>!</i><span>{C.esc(w)}</span></li>" for w in weaknesses) +
            '</ul>'
        )
    else:
        growth_content = (
            '<div class="iq-report-empty-note">'
            'No significant growth areas or competency gaps were identified during this assessment. '
            'The candidate demonstrated solid proficiency across all evaluated topics.'
            '</div>'
        )

    st.markdown(
        f'<div class="iq-report-hero">'
        f'<div class="iq-report-rec-bar">'
        f'<div class="iq-report-rec-title"><span>AI Advisory Recommendation</span>{C.badge(rec_label, rec_tone, dot=True)}</div>'
        f'<span class="iq-report-rec-note">Advisory verdict · Final decision rests with human recruiter</span>'
        f'</div>'
        f'<div class="iq-report-rationale-box"><b>Recommendation Rationale:</b> {C.esc(rationale_text)}</div>'
        f'<div class="iq-report-summary-box">'
        f'<div class="iq-report-summary-title">Executive Summary</div>'
        f'<div class="iq-report-summary-text">{C.esc(summary_text)}</div>'
        f'</div>'
        f'<div class="iq-report-grid">'
        f'<div class="iq-report-col strengths">'
        f'<div class="iq-report-col-header"><span>✓</span><span>Key Strengths</span></div>'
        f'{strengths_content}'
        f'</div>'
        f'<div class="iq-report-col growth">'
        f'<div class="iq-report-col-header"><span>!</span><span>Areas for Growth</span></div>'
        f'{growth_content}'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True
    )

    # 4. Recruiter's Final Hiring Decision Panel
    decision_panel(rep, app_id)

    # 5. Detailed Secondary Information (Tabbed & Comfortably Spaced)
    st.markdown("<div style='height: 1.5rem'></div>", unsafe_allow_html=True)
    C.section("Evaluation Details & Evidence", "Inspect detailed competency rubrics, verbatim citations, interview transcript, and candidate profile.")

    tabs = st.tabs([
        "Competency Breakdown",
        "Interview Q&A Transcript",
        "Candidate Feedback Preview",
        "Parsed Resume Profile"
    ])

    with tabs[0]:
        competency_tab(rep, asm, job)

    with tabs[1]:
        qa_transcript_tab(rep, job)

    with tabs[2]:
        feedback_preview_tab(rep, asm)

    with tabs[3]:
        profile_tab(rep)


# ==============================================================================
# SECONDARY DETAIL COMPONENTS
# ==============================================================================
def competency_tab(rep, asm, job):
    table = asm.get("competency_table", [])
    if not table:
        C.empty_state("No Competency Table Available", "Competency scores have not been calculated yet.")
        return

    def _comp_status_badge(score: Optional[float]) -> C.Raw:
        if score is None:
            return C.badge("Not Assessed", "neutral")
        if score >= 7.0:
            return C.badge("Strong Evidence", "success")
        elif score >= 5.0:
            return C.badge("Direct Evidence", "success")
        elif score >= 3.0:
            return C.badge("Partial Evidence", "warning")
        return C.badge("Limited Evidence", "error")

    C.table(
        [
            ("name", "Competency", "strong"),
            ("weight", "Weight"),
            ("resume", "Resume Score"),
            ("interview", "Interview Score"),
            ("status", "Evidence Status")
        ],
        [
            {
                "name": row["name"],
                "weight": f"{row['weight']:.1f}x",
                "resume": f"{row['resume_score']:.1f} / 10" if row.get("resume_score") is not None else "-",
                "interview": f"{row['interview_score']:.1f} / 10" if row.get("interview_score") is not None else "Not assessed",
                "status": _comp_status_badge(row.get("interview_score"))
            }
            for row in table
        ]
    )

    st.markdown("<div style='height: 0.75rem'></div>", unsafe_allow_html=True)
    st.markdown("##### Verbatim Citations by Competency")
    for row in table:
        has_score = row.get("interview_score") is not None
        score_header = f"{row['interview_score']:.1f} / 10" if has_score else "Not Assessed"
        with st.expander(f"{row['name']} — Interview Score: {score_header}", expanded=False):
            raw_rat = row.get("interview_rationale", "")
            if raw_rat and raw_rat != "not assessed":
                clean_rat = clean_demo_wording(raw_rat)
                st.markdown(f'<div class="iq-citation-rationale"><b>Assessor Rationale:</b> {C.esc(clean_rat)}</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="iq-citation-rationale" style="color:var(--muted);font-style:italic;">This competency was not assessed during the interview session.</div>', unsafe_allow_html=True)

            ev = row.get("interview_evidence", [])
            if ev:
                st.markdown('<div class="iq-detail-section-title">Verbatim Excerpts</div>', unsafe_allow_html=True)
                for quote in ev:
                    C.quote(quote)
            else:
                if has_score:
                    st.caption("No specific verbatim quotes were cited for this competency.")
                else:
                    st.caption("Not applicable — competency was not probed in this session.")


def qa_transcript_tab(rep, job):
    transcript = rep.get("transcript", [])
    if not transcript:
        C.empty_state("No Transcript Available", "Interview transcript was not recorded or interview is pending.")
        return

    st.caption(f"**Total Conversation Turns:** {len(transcript)}")
    st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)
    for turn in transcript:
        role = turn.get("role", "assistant")
        text = turn.get("text", "")
        comp = turn.get("competency", "")
        with st.chat_message("assistant" if role == "interviewer" else "user"):
            if comp:
                st.caption(f"Competency: {comp}")
            st.write(text)


def feedback_preview_tab(rep, asm):
    fb = asm.get("candidate_feedback")
    if not fb:
        C.empty_state("Candidate Feedback Not Available", "Personalized feedback has not been compiled for this candidate yet.")
        return

    st.caption("This is the constructive feedback displayed to the candidate in their Candidate Portal (private scores and rankings are excluded).")
    st.markdown("<div style='height: 0.5rem'></div>", unsafe_allow_html=True)

    summary_text = fb.get("summary", "").strip() or "Thank you for completing your interview. Your personalized feedback is based on your responses in this session."
    with st.container(border=True):
        st.markdown("**Feedback Summary:**")
        st.write(summary_text)

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("**Strengths Recognized:**")
            fb_strengths = fb.get("strengths", [])
            if fb_strengths:
                for s in fb_strengths:
                    st.markdown(f"• {s}")
            else:
                st.markdown("<div class='iq-report-empty-note'>Engaged constructively across all interview questions.</div>", unsafe_allow_html=True)
    with c2:
        with st.container(border=True):
            st.markdown("**Areas for Improvement:**")
            fb_weaknesses = fb.get("weaknesses", [])
            if fb_weaknesses:
                for w in fb_weaknesses:
                    st.markdown(f"• {w}")
            else:
                st.markdown("<div class='iq-report-empty-note'>No critical areas for improvement were identified during this session.</div>", unsafe_allow_html=True)

    if fb.get("improvement_areas"):
        with st.container(border=True):
            st.markdown("**Recommended Practice Areas:**")
            for imp in fb.get("improvement_areas", []):
                st.markdown(f"• {imp}")


def profile_tab(rep):
    p = rep.get("profile", {})
    if not p or not any(p.values()):
        C.empty_state("No Profile Data Available", "Resume parsing did not extract profile information for this candidate.")
        return

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
        C.empty_state("No Decision Trace Recorded", "No supervisor decision entries exist for this candidate.")
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
    st.markdown("<div style='height: 1rem'></div>", unsafe_allow_html=True)
    C.section("Recruiter Final Decision", "Record or update your official hiring determination and recommendation notes.")
    dec_info = rep.get("recruiter_decision")

    if dec_info:
        C.callout(
            "success",
            f"Decision Recorded: {dec_info['decision']}",
            f"Notes: {dec_info.get('notes') or 'None'} · Recorded At: {H.fmt_dt(dec_info.get('at'))}"
        )

    with st.form(f"decision_form_{app_id}"):
        dec = st.selectbox(
            "Final Determination",
            list(DECISION_OPTIONS.keys()),
            format_func=lambda k: f"{k} - {DECISION_OPTIONS[k][0]} ({DECISION_OPTIONS[k][1]})",
            index=0 if not dec_info else list(DECISION_OPTIONS.keys()).index(dec_info["decision"]) if dec_info["decision"] in DECISION_OPTIONS else 0
        )
        notes = st.text_area(
            "Decision Notes & Justification",
            value=dec_info.get("notes", "") if dec_info else "",
            placeholder="Document rationale, offer recommendations, or feedback..."
        )
        sub = st.form_submit_button("Record Final Decision", type="primary")

    if sub:
        ok, res = api.request("POST", f"/applications/{app_id}/decision", json={"decision": dec, "notes": notes.strip()})
        if ok:
            api.flash("success", "Decision Recorded", f"Final decision '{dec}' successfully saved for application #{app_id}.")
            st.rerun()
        else:
            C.callout("error", "Failed to record decision", res)
