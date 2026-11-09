"""Deterministic score aggregation (NOT an agent). Weights are configurable via environment variables."""
from typing import Dict, List, Optional

from app.schemas import JobIn


def resume_total(job: JobIn, scores: Dict[str, float]) -> float:
    """Weighted mean of per-competency resume scores over ALL JD competencies, scaled to 0-100."""
    tw = sum(c.weight for c in job.competencies)
    return round(sum(c.weight * scores.get(c.id, 0.0) for c in job.competencies) / tw * 10, 1)


def interview_total(job: JobIn, scores: Dict[str, float], planned: List[str]) -> Optional[float]:
    """Weighted mean over the PLANNED competencies that were actually assessed (renormalised), 0-100.
    Unplanned/pivot competencies are reported separately and do not affect this number.
    Unassessed planned competencies are not penalized as 0 here (performance is separated from coverage)."""
    assessed = [c for c in job.competencies if c.id in planned and c.id in scores]
    if not assessed:
        return None
    tw = sum(c.weight for c in assessed)
    return round(sum(c.weight * scores[c.id] for c in assessed) / tw * 10, 1)


def interview_coverage(planned: List[str], assessed: List[str]) -> float:
    """Proportion of planned competencies that were assessed (0.0 - 1.0).
    Separates interview performance from assessment coverage."""
    if not planned:
        return 1.0
    assessed_set = set(assessed)
    planned_set = set(planned)
    return round(len(planned_set & assessed_set) / len(planned_set), 2)


def weighted_interview_coverage(job: JobIn, planned: List[str], assessed: List[str]) -> float:
    """Weighted coverage of planned competencies based on job competency weights."""
    planned_comps = [c for c in job.competencies if c.id in planned]
    if not planned_comps:
        return 1.0
    tw = sum(c.weight for c in planned_comps)
    aw = sum(c.weight for c in planned_comps if c.id in assessed)
    return round(aw / tw, 2)


def is_coverage_sufficient(planned: List[str], assessed: List[str], min_coverage: float = 0.75) -> bool:
    """Determines if interview coverage meets the configurable minimum requirement."""
    return interview_coverage(planned, assessed) >= min_coverage


def combine(resume: float, interview: Optional[float], w_resume: float, w_interview: float) -> float:
    if interview is None:
        return round(resume, 1)
    return round(w_resume * resume + w_interview * interview, 1)


def recommendation_label(final: float, settings, coverage: Optional[float] = None) -> str:
    """Determines recommendation label based on final score and assessment coverage.

    Incomplete interviews (coverage < min_interview_coverage) are marked as provisional
    and require recruiter review (never receive RECOMMEND_ADVANCE).
    """
    min_cov = getattr(settings, "min_interview_coverage", 0.75)
    if coverage is not None and coverage < min_cov:
        if final >= settings.recommend_review_min:
            return "BORDERLINE_RECRUITER_REVIEW"
        return "NOT_RECOMMENDED"
    if final >= settings.recommend_advance_min:
        return "RECOMMEND_ADVANCE"
    if final >= settings.recommend_review_min:
        return "BORDERLINE_RECRUITER_REVIEW"
    return "NOT_RECOMMENDED"


def rank(items: List[dict]) -> List[dict]:
    """items: [{application_id, total}] -> sorted desc, with 1-based rank (ties share rank, stable by id)."""
    items = sorted(items, key=lambda x: (-x["total"], x["application_id"]))
    prev, r = None, 0
    for i, it in enumerate(items, 1):
        if it["total"] != prev:
            r, prev = i, it["total"]
        it["rank"] = r
    return items


def propose_shortlist(ranked: List[dict], top_n: int, min_score: float) -> List[int]:
    return [x["application_id"] for x in ranked if x["total"] >= min_score][:top_n]
