import json
from sqlalchemy import select

from app.db import Application
from app.services import overview as ov
from tests.helpers import ANSWER_BANK, add_resume, make_job
from tests.test_workflow import FILES, run_full_interview, scheduled_candidate


def A(id, status, shortlisted=False, job=1):
    return {"id": id, "job_id": job, "status": status, "shortlisted": shortlisted}


def test_empty_system_suggests_creating_a_job():
    o = ov.build_overview([], [], 0, 0, 0)
    assert o["metrics"]["total_applicants"] == 0 and o["next_action"]["page"] == "Jobs"
    assert [f["count"] for f in o["funnel"]] == [0] * 6


def test_metrics_and_funnel_are_counted_from_statuses():
    apps = [A(1, "PARSED"), A(2, "SCORING_FAILED"), A(3, "SCORED"), A(4, "SCORED", True), A(5, "SHORTLISTED", True),
            A(6, "SCHEDULED", True), A(7, "ASSESSED", True), A(8, "DECIDED", True), A(9, "ASSESSMENT_FAILED", True)]
    o = ov.build_overview([object()], apps, booked_slots=1, free_slots=39, open_reviews=2)
    m = o["metrics"]
    assert m["total_applicants"] == 9 and m["awaiting_screening"] == 2 and m["scoring_failed"] == 1
    assert m["awaiting_review"] == 1                      # only SCORED and not shortlisted
    assert m["shortlisted"] == 6 and m["awaiting_scheduling"] == 1 and m["scheduled"] == 1
    assert m["pending_identity"] == 2 and m["awaiting_decision"] == 1 and m["completed_interviews"] == 3 and m["decided"] == 1
    assert [f["count"] for f in o["funnel"]] == [9, 7, 5, 4, 3, 1]       # cumulative, monotonically non-increasing
    assert o["next_action"]["key"] == "identity"          # most blocking item first
    assert all(a["count"] > 0 for a in o["pending_actions"])


def test_no_pending_actions_when_everything_is_done():
    o = ov.build_overview([object()], [A(1, "DECIDED", True)], 1, 0, 0)
    assert o["pending_actions"] == [] and o["next_action"] is None


def test_compute_overview_from_real_pipeline(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    o = ov.compute_overview(db)
    assert o["metrics"]["total_applicants"] == 6 and o["metrics"]["scheduled"] == 1 and o["metrics"]["shortlisted"] == 1
    assert o["metrics"]["awaiting_review"] == 5 and o["per_job"][0]["applicants"] == 6
    sv.verify_identity(a.id, b"", "different_person")
    assert ov.compute_overview(db)["metrics"]["pending_identity"] == 1
    assert ov.compute_overview(db)["next_action"]["page"] == "Identity Review"


def test_overview_reflects_completed_interview(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    run_full_interview(sv, a)
    m = ov.compute_overview(db)["metrics"]
    assert m["completed_interviews"] == 1 and m["awaiting_decision"] == 1 and m["pending_identity"] == 0
    sv.record_decision(a.id, "ADVANCE", "ok")
    assert ov.compute_overview(db)["metrics"]["decided"] == 1


def test_candidate_feedback_only_contains_own_words(db, settings):
    from app.services import reports
    from app.schemas import SessionState
    from app.db import InterviewSessionRow
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    run_full_interview(sv, a)
    fb = reports.candidate_feedback(db, a.id)
    sess = db.execute(select(InterviewSessionRow)).scalars().all()[0]
    mine = " ".join(t.text for t in SessionState.model_validate_json(sess.state_json).transcript if t.role == "candidate")
    assert fb["competencies"] and fb["job"] == job.title
    for c in fb["competencies"]:
        for e in c["evidence"]:
            assert e.rstrip(".").strip() in mine or e[:60] in mine        # quotes come from the candidate's answers



def test_job_without_applicants_asks_for_resumes_not_all_caught_up():
    o = ov.build_overview([object()], [], 0, 40, 0)
    assert o["next_action"]["key"] == "upload" and o["next_action"]["page"] == "Candidates"
