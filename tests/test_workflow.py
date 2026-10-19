import json

import pytest
from sqlalchemy import select

from app.db import AssessmentRow, IdentityCheckRow, ReviewItem, Slot
from app.services import reports, scheduler
from app.services.state_machine import GateViolation
from app.workflow.supervisor import Supervisor
from tests.helpers import ANSWERS, FUTURE, FakeLLM, add_resume, make_job

FILES = ["Aarav_Mehta.docx", "Priya_Nair.pdf", "Rohan_Gupta.docx", "Sneha_Kulkarni.pdf", "Karan_Shah.docx", "Meera_Iyer.pdf"]


def scheduled_candidate(db, settings, sv=None, file="Meera_Iyer.pdf"):
    job = make_job(db)
    apps = [add_resume(db, job, f) for f in FILES]
    sv = sv or Supervisor(db, settings)
    res = sv.screen_job(job.id)
    target = next(a for a in apps if a.resume_filename == file)
    sv.shortlist(job.id, [target.id])
    scheduler.schedule_shortlisted(db, settings, job, now=FUTURE)
    return sv, job, target


def run_full_interview(sv, a, answers=ANSWERS):
    q = sv.start_interview(a.id)
    i = 0
    while True:
        r = sv.submit_answer(a.id, answers[i % len(answers)])
        i += 1
        if r["concluded"]:
            return r


# ------------------------------------------------------------------ screening
def test_screening_ranks_and_proposes_shortlist(db, settings):
    job = make_job(db)
    [add_resume(db, job, f) for f in FILES]
    res = Supervisor(db, settings).screen_job(job.id)
    names = [r["name"] for r in res["ranking"]]
    assert len(names) == 6 and not res["failed"]
    assert names[-1] in ("Karan Shah", "Sneha Kulkarni")
    assert set(names[:2]) <= {"Aarav Mehta", "Meera Iyer", "Priya Nair"}
    assert len(res["proposed_shortlist"]) <= settings.shortlist_top_n


def test_scoring_failure_marks_application_not_crash(db, settings):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    sv = Supervisor(db, settings, llm=FakeLLM(["garbage"]))
    res = sv.screen_job(job.id)
    assert res["failed"] and db.get(type(a), a.id).status == "SCORING_FAILED"


def test_cannot_shortlist_unscored_application(db, settings):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    with pytest.raises(GateViolation):
        Supervisor(db, settings).shortlist(job.id, [a.id])


def test_only_shortlisted_get_scheduled(db, settings):
    sv, job, target = scheduled_candidate(db, settings)
    booked = db.execute(select(Slot).where(Slot.application_id.is_not(None))).scalars().all()
    assert [s.application_id for s in booked] == [target.id] and target.status == "SCHEDULED"


# ------------------------------------------------------------------ identity gate
def test_interview_cannot_start_before_identity_check(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)


def test_interview_cannot_start_for_unscheduled_candidate(db, settings):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    with pytest.raises(GateViolation):
        Supervisor(db, settings).verify_identity(a.id, b"", "match")


def test_failed_identity_goes_to_human_review_and_blocks_interview(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    r = sv.verify_identity(a.id, b"", "different_person")
    assert r["passed"] is False and r["status"] == "HUMAN_REVIEW"
    assert db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all()
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)                       # hard gate: does not start automatically


def test_no_face_also_gated(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    assert sv.verify_identity(a.id, b"", "no_face")["passed"] is False
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)


def test_identity_pass_then_interview_starts_and_log_written(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    r = sv.verify_identity(a.id, b"", "match")
    assert r["passed"] and r["status"] == "IDENTITY_PASSED"
    q = sv.start_interview(a.id)
    assert q["question"]
    log = json.loads((settings.subdir("identity_logs") / f"identity_log_{a.id}.json").read_text())
    assert log[0]["passed"] is True and log[0]["timestamp"] and "match_confidence" in log[0]
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)                       # cannot start twice


def test_mid_session_swap_suspends_interview(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    sv.start_interview(a.id)
    sv.submit_answer(a.id, ANSWERS[0])
    r = sv.verify_identity(a.id, b"", "swap_mid_session", check_type="mid_session")
    assert r["passed"] is False and r["status"] == "HUMAN_REVIEW"
    with pytest.raises(GateViolation):
        sv.submit_answer(a.id, ANSWERS[1])


def test_manual_pass_resumes_suspended_interview_and_requires_notes(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    sv.start_interview(a.id)
    sv.submit_answer(a.id, ANSWERS[0])
    sv.verify_identity(a.id, b"", "swap_mid_session", check_type="mid_session")
    item = db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all()[0]
    with pytest.raises(ValueError):
        sv.resolve_review(item.id, "approve_manual_pass", "")
    sv.resolve_review(item.id, "approve_manual_pass", "Verified by video call with ID document")
    assert sv.submit_answer(a.id, ANSWERS[1])["questions_asked"] >= 2


def test_review_reject_ends_application_and_deletes_photo(db, settings, tmp_path):
    sv, job, a = scheduled_candidate(db, settings)
    p = tmp_path / "ref.img"
    p.write_bytes(b"x")
    a.photo_path = str(p)
    db.commit()
    sv.verify_identity(a.id, b"", "no_face")
    item = db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all()[0]
    sv.resolve_review(item.id, "reject", "could not confirm identity")
    assert a.status == "REJECTED_AT_REVIEW" and not p.exists()
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)


def test_approve_retry_allows_second_identity_attempt(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "no_face")
    item = db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all()[0]
    sv.resolve_review(item.id, "approve_retry", "")
    assert sv.verify_identity(a.id, b"", "match")["passed"]


# ------------------------------------------------------------------ interview + assessment (demo mode)
def test_full_pipeline_demo_mode(db, settings, tmp_path):
    sv, job, a = scheduled_candidate(db, settings)
    p = tmp_path / "ref.img"
    p.write_bytes(b"x")
    a.photo_path = str(p)
    db.commit()
    sv.verify_identity(a.id, b"", "match")
    final = run_full_interview(sv, a)
    assert final["concluded"] and a.status == "ASSESSED"
    assert not p.exists() and a.photo_path is None                     # biometric data minimised
    rep = reports.recruiter_report(db, settings, a.id, sv.traces(a.id))
    asm = rep["assessment"]
    assert 0 <= asm["final_score"] <= 100 and asm["label"] in ("RECOMMEND_ADVANCE", "BORDERLINE_RECRUITER_REVIEW", "NOT_RECOMMENDED")
    assert asm["weights"] == {"resume": 0.4, "interview": 0.6}
    expected = round(0.4 * asm["resume_score"] + 0.6 * asm["interview_score"], 1)
    assert asm["final_score"] == expected
    assert any("DEMO MODE" in f for f in asm["flags"])
    assert rep["trace"] and all(t["trigger_phrase"] and t["reasoning"] and t["decision"] for t in rep["trace"])
    assert (settings.subdir("traces") / f"interview_trace_{a.id}.json").exists()
    assert "disclaimer" in rep and rep["recruiter_decision"] is None
    fb = reports.candidate_feedback(db, a.id)
    assert fb["available"] and fb["strengths"] and "final_score" not in fb and "label" not in fb
    # no scores leak to the candidate: narrative fields contain no digits; per-competency notes carry only a
    # qualitative level + the candidate's OWN words (verbatim from their answers)
    narrative = {k: fb[k] for k in ("summary", "strengths", "weaknesses", "improvement_areas")}
    assert not any(ch.isdigit() for ch in json.dumps(narrative))
    for c in fb["competencies"]:
        assert set(c) == {"name", "level", "evidence"} and c["level"] in ("Strong evidence", "Developing", "Needs more evidence")


def test_answer_after_conclusion_is_blocked(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    run_full_interview(sv, a)
    with pytest.raises(GateViolation):
        sv.submit_answer(a.id, "one more thing")


def test_empty_answer_rejected(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    sv.start_interview(a.id)
    with pytest.raises(ValueError):
        sv.submit_answer(a.id, "   ")


def test_recruiter_decision_requires_assessment_and_is_separate(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    with pytest.raises(GateViolation):
        sv.record_decision(a.id, "ADVANCE", "too early")
    sv.verify_identity(a.id, b"", "match")
    run_full_interview(sv, a)
    with pytest.raises(ValueError):
        sv.record_decision(a.id, "HIRE_NOW", "")
    sv.record_decision(a.id, "HOLD", "want a second interview")
    assert a.status == "DECIDED"
    assert reports.recruiter_report(db, settings, a.id, [])["recruiter_decision"]["decision"] == "HOLD"


# ------------------------------------------------------------------ real-LLM-mode failure handling (scripted fake LLM)
def test_interviewer_failure_uses_labelled_fallback_and_interview_still_completes(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    sv.start_interview(a.id)
    sv.interviewer.llm = FakeLLM(["not json"])          # real-LLM mode whose model keeps returning garbage
    for i in range(20):
        r = sv.submit_answer(a.id, ANSWERS[i % len(ANSWERS)])
        if r["concluded"]:
            break
    assert r["concluded"] and a.status == "ASSESSED"
    traces = sv.traces(a.id)
    assert any(t["source"] == "fallback" for t in traces)


def test_assessment_failure_is_recorded_and_retry_works(db, settings):
    sv, job, a = scheduled_candidate(db, settings)
    sv.verify_identity(a.id, b"", "match")
    from app.llm.client import DemoLLM
    good_assessor = sv.assessor.llm
    sv.assessor.llm = FakeLLM(["{bad"])
    run_full_interview(sv, a)
    assert a.status == "ASSESSMENT_FAILED"
    row = db.execute(select(AssessmentRow)).scalars().all()[0]
    assert row.status == "FAILED" and row.error
    assert reports.candidate_feedback(db, a.id)["available"] is False
    sv.assessor.llm = good_assessor
    sv.retry_assessment(a.id)
    assert a.status == "ASSESSED"
    with pytest.raises(GateViolation):
        sv.retry_assessment(a.id)
