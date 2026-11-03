with open('app/services/reports.py', 'r', encoding='utf-8') as f:
    c = f.read()

old_target = '''    elif ar:
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
        return {"available": False, "message": "Your feedback is not ready yet."}'''

new_replacement = '''    elif ar:
        rep["assessment_status"] = ar.status
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
    if not a:
        return {"available": False, "status": "NOT_FOUND", "message": "Application record not found."}
    ar = db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one_or_none()
    if not ar or ar.status != "OK":
        if a.status in ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED"):
            return {
                "available": False,
                "status": "PROCESSING" if a.status == "INTERVIEW_COMPLETE" else "FAILED",
                "message": "Your interview has completed. Your personalized competency feedback is currently being finalized. Please check back shortly.",
            }
        return {
            "available": False,
            "status": "NOT_READY",
            "message": "Your feedback will be accessible here once you complete your interview session."
        }'''

assert old_target in c, 'old_target not found'
c = c.replace(old_target, new_replacement)
with open('app/services/reports.py', 'w', encoding='utf-8') as f:
    f.write(c)
print('Successfully updated app/services/reports.py')
