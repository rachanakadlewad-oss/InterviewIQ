"""Separate outputs: a detailed RECRUITER report and a restricted CANDIDATE feedback view."""
from sqlalchemy import select

from app.db import Application, AssessmentRow, Job, RecruiterDecision, jload
from app.schemas import AssessmentOutput, JobIn, SessionState
from app.services import identity as idsvc
from app.services import interview_engine as eng

DISCLAIMER = ("This report is decision SUPPORT only. The recommendation label is computed from configurable score "
              "thresholds; the hiring decision is made by the human recruiter.")


def recruiter_report(db, settings, application_id: int, traces: list) -> dict:
    a = db.get(Application, application_id)
    job_row = db.get(Job, a.job_id)
    job = JobIn.model_validate({"title": job_row.title, "description": job_row.description,
                                "competencies": jload(job_row.competencies_json, [])})
    rs = jload(a.resume_scores_json, {}) or {}
    rs_by = {s["competency_id"]: s for s in rs.get("scores", [])}
    ar = db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one_or_none()
    dec = db.execute(select(RecruiterDecision).where(RecruiterDecision.application_id == a.id)).scalar_one_or_none()
    rep = {
        "application_id": a.id, "candidate": a.candidate_name, "email": a.email, "job": job.title, "status": a.status,
        "configured_weights": {"resume": settings.weight_resume, "interview": settings.weight_interview},
        "profile": jload(a.profile_json, {}), "resume": {"score_0_100": a.resume_score, "rank": a.rank,
                                                         "source": a.scoring_source, "summary": a.resume_summary,
                                                         "per_competency": rs.get("scores", [])},
        "identity_log": idsvc.read_identity_log(settings, a.id),
        "trace": traces, "disclaimer": DISCLAIMER,
        "recruiter_decision": ({"decision": dec.decision, "notes": dec.notes, "at": dec.decided_at.isoformat()} if dec else None),
        "llm_mode": settings.llm_provider, "assessment": None,
    }
    if ar and ar.status == "OK":
        out = AssessmentOutput.model_validate_json(ar.output_json)
        iscores = jload(ar.interview_scores_json, {})
        by_c = {c.competency_id: c for c in out.competencies}
        table = []
        for c in job.competencies:
            table.append({"competency_id": c.id, "name": c.name, "weight": c.weight,
                          "resume_score": rs_by.get(c.id, {}).get("score"),
                          "interview_score": iscores.get(c.id),
                          "interview_evidence": by_c[c.id].evidence if c.id in by_c else [],
                          "interview_rationale": by_c[c.id].rationale if c.id in by_c else "not assessed"})
        planned = {c.id for c in job.competencies}
        extras = [{"competency_id": k, "score": v.score, "evidence": v.evidence, "rationale": v.rationale}
                  for k, v in by_c.items() if k not in planned]
        rep["assessment"] = {
            "source": ar.source, "resume_score": ar.resume_score, "interview_score": ar.interview_score,
            "final_score": ar.final_score, "weights": jload(ar.weights_json, {}), "label": ar.label,
            "flags": jload(ar.flags_json, []), "competency_table": table, "extra_competencies_explored": extras,
            "recruiter_summary": out.recruiter_summary, "recommendation_rationale": out.recommendation_rationale,
            "strengths": out.strengths, "weaknesses": out.weaknesses,
            "candidate_feedback": out.candidate_feedback.model_dump() if out.candidate_feedback else None}
    elif ar:
        rep["assessment_error"] = ar.error
    return rep


def level_label(score: float) -> str:
    """Qualitative band derived from the real 0-10 interview score (the number itself is never shown to candidates)."""
    if score >= 7:
        return "Strong evidence"
    if score >= 4.5:
        return "Developing"
    return "Needs more evidence"


def candidate_feedback(db, application_id: int) -> dict:
    """Candidate-facing: strengths / weaknesses / improvement areas only. No scores, rank, or hiring decision."""
    a = db.get(Application, application_id)
    ar = db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one_or_none()
    if not ar or ar.status != "OK":
        return {"available": False, "message": "Your feedback is not ready yet."}
    out = AssessmentOutput.model_validate_json(ar.output_json)
    fb = out.candidate_feedback
    job_row = db.get(Job, a.job_id)
    names = {c["id"]: c["name"] for c in jload(job_row.competencies_json, [])}
    from app.db import InterviewSessionRow
    sess = db.execute(select(InterviewSessionRow).where(InterviewSessionRow.application_id == a.id)).scalar_one_or_none()
    if sess:
        names.update(SessionState.model_validate_json(sess.state_json).extra)
    notes = [{"name": names.get(c.competency_id, c.competency_id), "level": level_label(c.score),
              "evidence": [e[:240] for e in c.evidence]} for c in out.competencies]
    return {"available": True, "job": job_row.title, **fb.model_dump(), "competencies": notes,
            "note": "This feedback reflects only your answers in this interview. A human recruiter makes all hiring decisions."}
