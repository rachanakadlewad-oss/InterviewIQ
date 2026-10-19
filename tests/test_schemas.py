import pytest
from pydantic import ValidationError

from app.schemas import (AssessmentOutput, Competency, InterviewerDecision, JobIn, ResumeScoringOutput, CompetencyScore)


def test_decision_requires_question_unless_conclude():
    with pytest.raises(ValidationError):
        InterviewerDecision(trigger_phrase="x", reasoning="because", decision="NARROW_FOLLOW_UP")
    d = InterviewerDecision(trigger_phrase="x", reasoning="because", decision="CONCLUDE")
    assert d.question is None


def test_decision_question_must_be_speakable():
    with pytest.raises(ValidationError):
        InterviewerDecision(trigger_phrase="x", reasoning="because", decision="NEXT_COMPETENCY",
                            question=" ".join(["word"] * 60))


def test_broad_pivot_requires_target():
    with pytest.raises(ValidationError):
        InterviewerDecision(trigger_phrase="x", reasoning="because", decision="BROAD_PIVOT", question="Tell me more?")


def test_unknown_decision_rejected():
    with pytest.raises(ValidationError):
        InterviewerDecision(trigger_phrase="x", reasoning="because", decision="MAYBE", question="q?")


def test_job_requires_unique_competency_ids():
    c = {"id": "a", "name": "A"}
    with pytest.raises(ValidationError):
        JobIn(title="Job", competencies=[c, c])


def test_score_bounds_and_duplicates():
    with pytest.raises(ValidationError):
        CompetencyScore(competency_id="a", score=11, justification="abc")
    s = {"competency_id": "a", "score": 5, "justification": "abc"}
    with pytest.raises(ValidationError):
        ResumeScoringOutput(scores=[s, s])
