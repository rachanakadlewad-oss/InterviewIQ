"""Application status machine - the single source of truth for which transitions are legal.
The identity gate is enforced here: INTERVIEW_IN_PROGRESS is reachable ONLY from IDENTITY_PASSED."""

TRANSITIONS = {
    "APPLIED": {"PARSED", "PENDING_REVIEW", "SCORED", "REJECTED"},
    "PARSED": {"SCORED", "SCORING_FAILED", "PENDING_REVIEW", "UNDER_REVIEW", "SHORTLISTED", "REJECTED"},
    "PENDING_REVIEW": {"SCORED", "SCORING_FAILED", "UNDER_REVIEW", "SHORTLISTED", "REJECTED", "ACCEPTED"},
    "UNDER_REVIEW": {"SCORED", "SHORTLISTED", "PENDING_REVIEW", "REJECTED", "ACCEPTED"},
    "SCORING_FAILED": {"SCORED", "SCORING_FAILED", "REJECTED"},
    "SCORED": {"SHORTLISTED", "SCORED", "PENDING_REVIEW", "UNDER_REVIEW", "REJECTED", "ACCEPTED"},
    "SHORTLISTED": {"SCHEDULED", "SCORED", "PENDING_REVIEW", "UNDER_REVIEW", "REJECTED", "ACCEPTED"},
    "ACCEPTED": {"SCHEDULED", "SHORTLISTED", "DECIDED", "REJECTED"},
    "SCHEDULED": {"IDENTITY_PASSED", "HUMAN_REVIEW", "SCHEDULED", "REJECTED"},
    "HUMAN_REVIEW": {"SCHEDULED", "IDENTITY_PASSED", "REJECTED_AT_REVIEW", "REJECTED", "INTERVIEW_IN_PROGRESS"},
    "IDENTITY_PASSED": {"INTERVIEW_IN_PROGRESS", "HUMAN_REVIEW", "REJECTED"},
    "INTERVIEW_IN_PROGRESS": {"HUMAN_REVIEW", "INTERVIEW_COMPLETE"},
    "INTERVIEW_COMPLETE": {"ASSESSED", "ASSESSMENT_FAILED"},
    "ASSESSMENT_FAILED": {"ASSESSED", "ASSESSMENT_FAILED"},
    "ASSESSED": {"DECIDED", "ACCEPTED", "REJECTED"},
    "DECIDED": {"DECIDED", "ACCEPTED", "REJECTED"},
    "REJECTED_AT_REVIEW": {"REJECTED"},
    "REJECTED": {"PENDING_REVIEW", "UNDER_REVIEW", "SHORTLISTED"},
}


class GateViolation(Exception):
    """An operation was attempted that the pipeline forbids (e.g. interview before identity pass)."""


def transition(app, new_status: str):
    allowed = TRANSITIONS.get(app.status, set())
    if new_status not in allowed:
        raise GateViolation(f"illegal transition {app.status} -> {new_status}")
    app.status = new_status
