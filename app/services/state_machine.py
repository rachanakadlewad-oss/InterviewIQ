"""Application status machine - the single source of truth for which transitions are legal.
The identity gate is enforced here: INTERVIEW_IN_PROGRESS is reachable ONLY from IDENTITY_PASSED."""

TRANSITIONS = {
    "PARSED": {"SCORED", "SCORING_FAILED"},
    "SCORING_FAILED": {"SCORED", "SCORING_FAILED"},
    "SCORED": {"SHORTLISTED", "SCORED"},
    "SHORTLISTED": {"SCHEDULED", "SCORED"},
    "SCHEDULED": {"IDENTITY_PASSED", "HUMAN_REVIEW", "SCHEDULED"},
    "HUMAN_REVIEW": {"SCHEDULED", "IDENTITY_PASSED", "REJECTED_AT_REVIEW", "INTERVIEW_IN_PROGRESS"},
    "IDENTITY_PASSED": {"INTERVIEW_IN_PROGRESS", "HUMAN_REVIEW"},
    "INTERVIEW_IN_PROGRESS": {"HUMAN_REVIEW", "INTERVIEW_COMPLETE"},
    "INTERVIEW_COMPLETE": {"ASSESSED", "ASSESSMENT_FAILED"},
    "ASSESSMENT_FAILED": {"ASSESSED", "ASSESSMENT_FAILED"},
    "ASSESSED": {"DECIDED"},
    "DECIDED": {"DECIDED"},
    "REJECTED_AT_REVIEW": set(),
}


class GateViolation(Exception):
    """An operation was attempted that the pipeline forbids (e.g. interview before identity pass)."""


def transition(app, new_status: str):
    allowed = TRANSITIONS.get(app.status, set())
    if new_status not in allowed:
        raise GateViolation(f"illegal transition {app.status} -> {new_status}")
    app.status = new_status
