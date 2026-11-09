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
def test_interview_coverage_separates_performance_from_coverage():
    planned = ["python", "databases", "api_design", "testing"]
    assessed = ["python", "databases"]
    # 2 of 4 assessed = 50% coverage
    coverage = scoring.interview_coverage(planned, assessed)
    assert coverage == 0.5
    assert not scoring.is_coverage_sufficient(planned, assessed, min_coverage=0.75)

    # 3 of 4 assessed = 75% coverage
    assessed_3 = ["python", "databases", "api_design"]
    assert scoring.interview_coverage(planned, assessed_3) == 0.75
    assert scoring.is_coverage_sufficient(planned, assessed_3, min_coverage=0.75)

    # Unplanned/pivot competencies do not artificially inflate coverage
    assessed_with_extra = ["python", "databases", "unplanned_leadership"]
    assert scoring.interview_coverage(planned, assessed_with_extra) == 0.5


def test_weighted_interview_coverage(job_in):
    planned = ["python", "databases", "testing"]
    # python weight 1.5, databases weight 1.2, testing weight 1.0 -> total = 3.7
    assessed = ["python", "databases"]  # 1.5 + 1.2 = 2.7 / 3.7 = 0.73
    w_cov = scoring.weighted_interview_coverage(job_in, planned, assessed)
    assert w_cov == round(2.7 / 3.7, 2)


def test_incomplete_interview_prevents_misleading_advance_recommendation():
    s = Settings(min_interview_coverage=0.75, recommend_advance_min=70.0, recommend_review_min=50.0)
    # High score (85.0) that normally qualifies for RECOMMEND_ADVANCE
    # With complete coverage (1.0 >= 0.75): awards RECOMMEND_ADVANCE
    assert scoring.recommendation_label(85.0, s, coverage=1.0) == "RECOMMEND_ADVANCE"

    # With incomplete coverage (0.5 < 0.75): MUST NOT award RECOMMEND_ADVANCE
    # Must require recruiter review (provisional)
    label_incomplete = scoring.recommendation_label(85.0, s, coverage=0.5)
    assert label_incomplete == "BORDERLINE_RECRUITER_REVIEW"
    assert label_incomplete != "RECOMMEND_ADVANCE"

    # Low score with incomplete coverage still yields NOT_RECOMMENDED
    assert scoring.recommendation_label(30.0, s, coverage=0.5) == "NOT_RECOMMENDED"


def test_unassessed_competency_not_treated_as_poor_ability(job_in):
    # When an interview is incomplete, unassessed planned competencies are not penalized as 0 in interview performance
    planned = ["python", "databases", "system_design", "testing"]
    # Only python was assessed (scored 8.0)
    scores = {"python": 8.0}
    total = scoring.interview_total(job_in, scores, planned)
    # Should equal 80.0 (performance on assessed competency), not 20.0 (penalizing unassessed as 0)
    assert total == 80.0
