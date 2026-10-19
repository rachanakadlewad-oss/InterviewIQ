import pytest

from app.config import Settings
from app.services import scoring


def test_resume_total_is_weighted_mean(job_in):
    scores = {c.id: 10.0 for c in job_in.competencies}
    assert scoring.resume_total(job_in, scores) == 100.0
    assert scoring.resume_total(job_in, {}) == 0.0


def test_interview_total_renormalises_over_assessed_planned(job_in):
    planned = ["python", "databases"]
    total = scoring.interview_total(job_in, {"python": 8.0, "databases": 4.0, "security": 10.0}, planned)
    # weights 1.5 and 1.2: (1.5*8 + 1.2*4)/2.7*10; the unplanned 'security' score is ignored
    assert total == round((1.5 * 8 + 1.2 * 4) / 2.7 * 10, 1)
    assert scoring.interview_total(job_in, {}, planned) is None


def test_combine_uses_documented_weights():
    assert scoring.combine(50, 100, 0.4, 0.6) == 80.0
    assert scoring.combine(50, None, 0.4, 0.6) == 50.0


def test_label_thresholds():
    s = Settings()
    assert scoring.recommendation_label(75, s) == "RECOMMEND_ADVANCE"
    assert scoring.recommendation_label(55, s) == "BORDERLINE_RECRUITER_REVIEW"
    assert scoring.recommendation_label(10, s) == "NOT_RECOMMENDED"


def test_rank_ties_share_rank():
    r = scoring.rank([{"application_id": 1, "total": 50}, {"application_id": 2, "total": 70}, {"application_id": 3, "total": 50}])
    assert [x["application_id"] for x in r] == [2, 1, 3]
    assert [x["rank"] for x in r] == [1, 2, 2]


def test_shortlist_proposal_respects_top_n_and_min():
    ranked = scoring.rank([{"application_id": i, "total": t} for i, t in enumerate([90, 80, 70, 30], 1)])
    assert scoring.propose_shortlist(ranked, 3, 40) == [1, 2, 3]
    assert scoring.propose_shortlist(ranked, 10, 75) == [1, 2]


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Settings(weight_resume=0.5, weight_interview=0.6).validate()


def test_real_provider_requires_key():
    with pytest.raises(ValueError):
        Settings(llm_provider="openai").validate()
