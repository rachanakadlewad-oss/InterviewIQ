import json

import streamlit as st

from .. import api, components as C, helpers as H
from .identity_review import identity_table


def render():
    C.page_header("Interview Reports & Decisions", "Review the evidence, compare AI recommendation with your own judgement, and record the final decision.", "Recruiter workspace")
    job_id = api.job_picker()
    if not job_id:
        return
    apps = api.call("GET", f"/jobs/{job_id}/applications") or []
    if not apps:
        C.empty_state("No candidates for this job yet")
        return
    pick = st.selectbox("Candidate", [a["application_id"] for a in apps], key="rep_pick",
                        format_func=lambda i: next(f"{a['name'] or 'Application'} - {H.status_label(a['status'])[0]}" for a in apps if a["application_id"] == i))
    rep = api.call("GET", f"/applications/{pick}/report")
    if not rep:
        return
    job = api.call("GET", f"/jobs/{job_id}") or {"competencies": []}
    header(rep)
    asm = rep["assessment"]
    if rep.get("assessment_error"):
        C.callout("error", "The Assessment Agent failed for this interview", rep["assessment_error"])
        if st.button("Retry assessment", type="primary"):
            if api.call("POST", f"/applications/{pick}/assessment/retry"):
                st.rerun()
    if not asm:
        waiting(rep)
    scores(rep, asm)
    tabs = st.tabs(["Summary", "Competencies", "Interview transcript", "Decision trace", "Identity", "Resume profile"])
    with tabs[0]:
        summary_tab(asm)
    with tabs[1]:
        competency_tab(rep, asm, job)
    with tabs[2]:
        transcript_tab(rep)
    with tabs[3]:
        if rep["trace"]:
            st.caption("Each turn records what the candidate said that triggered the decision, a short rationale, and the question asked.")
            C.trace(rep["trace"], {c["id"]: c["name"] for c in job["competencies"]})
        else:
            C.empty_state("No interview yet", "The decision trace appears once the interview starts.")
    with tabs[4]:
        if rep["identity_log"]:
            identity_table(rep["identity_log"])
        else:
            C.empty_state("No identity checks yet")
    with tabs[5]:
        p = rep["profile"]
        C.kv([("Name", p.get("name")), ("Email", p.get("email")), ("Experience (years)", p.get("experience_years") or "not stated")])
        if p.get("skills"):
            st.markdown("**Skills detected in resume**")
            C.badges(*[C.badge(s, "neutral", dot=False) for s in p["skills"]])
        if p.get("experience"):
            st.markdown("**Experience & roles**")
            for ex in p["experience"]:
                C.quote(ex)
        if p.get("projects"):
            st.markdown("**Projects & deliverables**")
            for pr in p["projects"]:
                C.quote(pr)
        if p.get("education"):
            st.markdown("**Education**")
            for ed in p["education"]:
                C.quote(ed)
        if p.get("summary"):
            st.markdown("**Summary**")
            C.quote(p["summary"])
    decision_panel(rep, pick)
    st.download_button("Download this report (JSON)", json.dumps(rep, indent=2, default=str), file_name=f"interviewiq_report_{pick}.json", mime="application/json")


def header(rep):
    st.markdown(f"### {rep['candidate'] or 'Application #' + str(rep['application_id'])}")
    bs = [C.status_badge(rep["status"]), C.badge(rep["job"], "neutral", dot=False)]
    rl, rt = H.source_label(rep["resume"]["source"])
    bs.append(C.badge(f"Resume scored by: {rl}", rt, dot=False))
    if rep["assessment"]:
        al, at = H.source_label(rep["assessment"]["source"])
        bs.append(C.badge(f"Interview assessed by: {al}", at, dot=False))
    C.badges(*bs)
    if rep["llm_mode"] == "demo":
        C.callout("warning", "Demo mode report", "Scores and interview decisions were produced by deterministic rules, not an LLM.")


def waiting(rep):
    msg = {"SCORED": "Not shortlisted yet.", "SHORTLISTED": "Shortlisted, waiting to be scheduled.", "SCHEDULED": "Scheduled; the candidate has not completed identity verification.",
           "HUMAN_REVIEW": "Blocked by an identity review (see the Identity Review page).", "IDENTITY_PASSED": "Identity verified; the interview has not started.",
           "INTERVIEW_IN_PROGRESS": "The interview is in progress.", "REJECTED_AT_REVIEW": "Application closed at identity review."}.get(rep["status"], "No assessment is available yet.")
    C.callout("info", "No interview assessment yet", msg)


def scores(rep, asm):
    resume = rep["resume"]["score_0_100"]
    w = (asm or {}).get("weights", {})
    C.metric_grid([
        {"label": "Resume score", "value": H.fmt_score(resume), "hint": f"out of 100 - rank {rep['resume']['rank'] or '-'}"},
        {"label": "Interview score", "value": H.fmt_score(asm["interview_score"]) if asm else "-", "hint": "out of 100, planned competencies assessed"},
        {"label": "Final weighted score", "value": H.fmt_score(asm["final_score"]) if asm else "-",
         "hint": f"{w.get('resume', '-')} x resume + {w.get('interview', '-')} x interview" if asm else "after the interview"},
    ])


def summary_tab(asm):
    if not asm:
        C.empty_state("Summary appears after the interview")
        return
    label, tone = H.RECOMMENDATION.get(asm["label"], (asm["label"], "neutral"))
    with st.container(border=True):
        st.markdown("**AI recommendation (advisory only)**")
        C.badges(C.badge(label, tone))
        st.write(asm["recommendation_rationale"])
        st.caption("Computed from the score thresholds in your settings. It does not decide anything.")
    st.markdown("**Assessment summary**")
    st.write(asm["recruiter_summary"])
    a, b = st.columns(2)
    with a:
        st.markdown("**Strengths**")
        for s in asm["strengths"] or ["None highlighted"]:
            st.markdown(f"- {s}")
    with b:
        st.markdown("**Weaknesses / gaps**")
        for s in asm["weaknesses"] or ["None highlighted"]:
            st.markdown(f"- {s}")
    gaps = [r["name"] for r in asm["competency_table"] if r["interview_score"] is None]
    if gaps:
        C.callout("info", "Competencies not covered in this interview",
                  "The interview probes the highest-priority competencies, so these were scored from the resume only: " + ", ".join(gaps) +
                  ". Their weight is excluded from the interview score. If one matters for this hire, consider a follow-up interview.")
    for f in asm["flags"]:
        C.callout("warning" if "DEMO" in f or "NOT assessed" in f else "info", f)  # flags come straight from the assessment record


def competency_tab(rep, asm, job):
    rs = {s["competency_id"]: s for s in rep["resume"]["per_competency"]}
    if not rs and not asm:
        C.empty_state("Not scored yet")
        return
    rows = asm["competency_table"] if asm else [{"competency_id": c["id"], "name": c["name"], "weight": c["weight"], "resume_score": rs.get(c["id"], {}).get("score"),
                                               "interview_score": None, "interview_evidence": [], "interview_rationale": ""} for c in job["competencies"]]
    C.table([("name", "Competency", "strong"), ("weight", "Weight"), ("resume", "Resume (0-10)"), ("interview", "Interview (0-10)")],
            [{"name": r["name"], "weight": r["weight"], "resume": C.score_bar(r["resume_score"]), "interview": C.score_bar(r["interview_score"])} for r in rows])
    st.markdown("")
    for r in rows:
        with st.expander(r["name"]):
            st.markdown("**From the resume**")
            s = rs.get(r["competency_id"])
            if s and s["evidence"]:
                st.caption(s["justification"])
                for e in s["evidence"]:
                    C.quote(e)
            else:
                st.caption("No resume evidence found.")
            st.markdown("**From the interview**")
            if r["interview_evidence"]:
                st.caption(r["interview_rationale"])
                for e in r["interview_evidence"]:
                    C.quote(e)
            else:
                st.caption("Not assessed in the interview." if r["interview_score"] is None else r["interview_rationale"])
    for x in (asm or {}).get("extra_competencies_explored", []):
        C.callout("success", f"Unplanned competency explored: {x['competency_id'].replace('extra_', '').replace('_', ' ')}",
                  f"Opened by a BROAD_PIVOT from the candidate's own answer. Score {x['score']:.1f}/10 (reported, not part of the weighted interview score). {x['rationale']}")


def transcript_tab(rep):
    if not rep.get("transcript"):
        C.empty_state("No interview transcript", "The conversation appears here once the interview starts.")
        return
    for t in rep["transcript"]:
        with st.chat_message("assistant" if t["role"] == "interviewer" else "user"):
            st.write(t["text"])


def decision_panel(rep, app_id):
    C.section("Your decision", "The recommendation above is advisory. You make the hiring decision.")
    d = rep["recruiter_decision"]
    if d:
        tone = {"ADVANCE": "success", "HOLD": "warning", "REJECT": "error"}[d["decision"]]
        C.callout(tone, f"Recorded decision: {d['decision'].title()}", d["notes"] or "No notes.")
    if rep["status"] not in ("ASSESSED", "DECIDED"):
        C.callout("info", "Decision not available yet", "You can record a decision once the interview has been assessed.")
        return
    choice = st.radio("Decision", ["ADVANCE", "HOLD", "REJECT"], horizontal=True, format_func=str.title, key=f"dec{app_id}")
    notes = st.text_input("Notes (kept with the record)", key=f"decn{app_id}")
    if st.button("Update decision" if d else "Record decision", type="primary", key=f"decb{app_id}"):
        if api.call("POST", f"/applications/{app_id}/decision", json={"decision": choice, "notes": notes}):
            st.rerun()
