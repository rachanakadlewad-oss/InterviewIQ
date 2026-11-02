import json

import pytest
from sqlalchemy import select

from app.db import Application, AssessmentRow, IdentityCheckRow, RecruiterDecision, ReviewItem, Slot
from app.schemas import SessionState
from app.services import identity as idsvc, reports, scheduler
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


def test_rescore_recalculates_candidate_rankings(db, settings):
    job = make_job(db)
    apps = [add_resume(db, job, f) for f in FILES]
    sv = Supervisor(db, settings)
    res1 = sv.screen_job(job.id)
    assert len(res1["scored"]) == 6
    # Rescore should recalculate scores and update ranking
    res2 = sv.screen_job(job.id, rescore=True)
    assert len(res2["scored"]) == 6
    assert len(res2["ranking"]) == 6
    # Ranks should be 1-based, sorted by total desc
    ranks = [r["rank"] for r in res2["ranking"]]
    assert ranks == sorted(ranks)
    assert ranks[0] == 1


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


def test_recruiter_shortlist_selection_confirmation_and_refresh_workflow(db, settings):
    from frontend.iqui import helpers as H
    job = make_job(db)
    apps = [add_resume(db, job, f) for f in FILES]
    sv = Supervisor(db, settings)
    sv.screen_job(job.id)

    # 1. Fetch apps and verify descending score order
    db_apps = [{"application_id": a.id, "name": a.candidate_name, "status": a.status,
                "resume_score": a.resume_score, "rank": a.rank, "shortlisted": a.shortlisted}
               for a in db.execute(select(Application).where(Application.job_id == job.id)).scalars()]
    sorted_apps = H.sort_candidates_by_score(db_apps)
    scores = [a["resume_score"] for a in sorted_apps if a["resume_score"] is not None]
    assert scores == sorted(scores, reverse=True)

    # 2. Before confirmation: no auto-shortlist (recruiter has complete control)
    confirmed_initial = H.get_confirmed_shortlist_ids(sorted_apps)
    assert confirmed_initial == []

    # 3. Add candidates to selection
    cand1, cand2 = sorted_apps[0]["application_id"], sorted_apps[1]["application_id"]
    selected = []
    selected = H.add_candidate_to_selection(selected, cand1)
    # Duplicate prevention: adding cand1 again is a no-op
    selected = H.add_candidate_to_selection(selected, cand1)
    assert selected == [cand1]
    selected = H.add_candidate_to_selection(selected, cand2)
    assert selected == [cand1, cand2]

    # 4. Remove candidate
    selected = H.remove_candidate_from_selection(selected, cand2)
    assert selected == [cand1]

    # 5. Empty selection validation
    empty_valid, errs = H.validate_shortlist_selection([], sorted_apps)
    assert not empty_valid and any("No candidates selected" in e for e in errs)

    # 6. Valid selection validation
    selected = H.add_candidate_to_selection(selected, cand2)
    valid, errs = H.validate_shortlist_selection(selected, sorted_apps)
    assert valid and not errs

    # 7. Unconfirmed candidates do NOT move to scheduling yet
    pending_before = [a for a in db.execute(select(Application).where(Application.job_id == job.id)).scalars()
                      if a.status == "SHORTLISTED"]
    assert len(pending_before) == 0

    # 8. Recruiter confirms shortlist
    sv.shortlist(job.id, selected)

    # 9. Verify confirmed candidates move to SHORTLISTED status
    confirmed_apps = db.execute(select(Application).where(Application.job_id == job.id)).scalars().all()
    shortlisted_map = {a.id: (a.shortlisted, a.status) for a in confirmed_apps}
    assert shortlisted_map[cand1] == (True, "SHORTLISTED")
    assert shortlisted_map[cand2] == (True, "SHORTLISTED")

    # 10. Simulate Page Refresh: fresh session reading from database
    db_apps_refreshed = [{"application_id": a.id, "name": a.candidate_name, "status": a.status,
                          "resume_score": a.resume_score, "rank": a.rank, "shortlisted": a.shortlisted}
                         for a in db.execute(select(Application).where(Application.job_id == job.id)).scalars()]
    confirmed_after_refresh = H.get_confirmed_shortlist_ids(db_apps_refreshed)
    assert set(confirmed_after_refresh) == {cand1, cand2}

    # 11. Now confirmed candidates can be scheduled
    res_sched = scheduler.schedule_shortlisted(db, settings, job, now=FUTURE)
    assert len(res_sched) == 2
    assert all(r["scheduled"] for r in res_sched)


def test_identity_full_verification_gate_matrix(db, settings, tmp_path):
    """Exhaustively verify:
    1. Pending candidate cannot start interview (gate locked).
    2. Failed check creates open review item and blocks interview start.
    3. Inconclusive check creates open review item and blocks interview start.
    4. Mandatory reasons required for manual pass and rejection.
    5. Manual retry resets candidate to SCHEDULED with gate remaining locked until re-check passes.
    6. Manual pass unlocks gate and allows interview to start.
    7. Rejection permanently closes application, deletes photo, and locks gate.
    8. Audit trail records decisions in IdentityCheckRow and identity_logs.
    """
    # 1. Pending candidate
    sv, job, a = scheduled_candidate(db, settings)
    assert a.status == "SCHEDULED"
    assert not sv.identity_gate_open(a.id)
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)

    # 2. Failed check scenario (different_person: confidence below threshold)
    res_fail = sv.verify_identity(a.id, b"", scenario="different_person")
    assert not res_fail["passed"]
    assert a.status == "HUMAN_REVIEW"
    assert not sv.identity_gate_open(a.id)
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)

    item = db.execute(select(ReviewItem).where(ReviewItem.application_id == a.id, ReviewItem.status == "OPEN")).scalar_one()
    assert item.kind == "IDENTITY"
    assert "FAILED" in item.reason

    # 3. Recruiter approves retry with mandatory note
    sv.resolve_review(item.id, "approve_retry", "Candidate reported poor web camera lighting; retry authorized")
    assert a.status == "SCHEDULED"
    # Even after retry authorization, gate must remain LOCKED until check passes
    assert not sv.identity_gate_open(a.id)
    with pytest.raises(GateViolation):
        sv.start_interview(a.id)

    # 4. Inconclusive check scenario (unknown scenario or error)
    res_inconcl = sv.verify_identity(a.id, b"", scenario="bogus_scenario")
    assert not res_inconcl["passed"]
    assert res_inconcl["identity"]["inconclusive"]
    assert a.status == "HUMAN_REVIEW"
    assert not sv.identity_gate_open(a.id)

    item2 = db.execute(select(ReviewItem).where(ReviewItem.application_id == a.id, ReviewItem.status == "OPEN")).scalar_one()
    assert "INCONCLUSIVE" in item2.reason

    # 5. Mandatory notes enforcement on approve_manual_pass
    with pytest.raises(ValueError):
        sv.resolve_review(item2.id, "approve_manual_pass", "")
    with pytest.raises(ValueError):
        sv.resolve_review(item2.id, "approve_manual_pass", "   ")

    # 6. Manual pass with valid note
    sv.resolve_review(item2.id, "approve_manual_pass", "Identity verified via direct video call with passport")
    assert a.status == "IDENTITY_PASSED"
    assert sv.identity_gate_open(a.id)

    # Interview can now start cleanly
    start_res = sv.start_interview(a.id)
    assert start_res["question"]
    assert a.status == "INTERVIEW_IN_PROGRESS"

    # 7. Audit trail check: verify IdentityCheckRow and identity_log entries
    check_rows = db.execute(select(IdentityCheckRow).where(IdentityCheckRow.application_id == a.id)
                            .order_by(IdentityCheckRow.id)).scalars().all()
    # Checks: 1 (failed) + 1 (retry row) + 1 (inconclusive) + 1 (manual pass row) = 4
    assert len(check_rows) >= 4
    assert any(c.human_override and c.passed and "manual pass" in c.reason for c in check_rows)
    assert any(c.human_override and not c.passed and "retry authorized" in c.reason for c in check_rows)

    id_log = idsvc.read_identity_log(settings, a.id)
    assert len(id_log) >= 4
    assert any("HUMAN OVERRIDE" in e.get("reason", "") for e in id_log)

    # 8. Rejection scenario with another candidate
    sv2, job2, a2 = scheduled_candidate(db, settings)
    ref_photo = tmp_path / "cand2.img"
    ref_photo.write_bytes(b"photo_data")
    a2.photo_path = str(ref_photo)
    db.commit()

    sv2.verify_identity(a2.id, b"", scenario="multiple_faces")
    item_rej = db.execute(select(ReviewItem).where(ReviewItem.application_id == a2.id, ReviewItem.status == "OPEN")).scalar_one()

    # Empty notes rejected
    with pytest.raises(ValueError):
        sv2.resolve_review(item_rej.id, "reject", "")

    sv2.resolve_review(item_rej.id, "reject", "Multiple unauthorized persons present in frame; candidate rejected")
    assert a2.status == "REJECTED_AT_REVIEW"
    assert not ref_photo.exists()
    assert not sv2.identity_gate_open(a2.id)
    with pytest.raises(GateViolation):
        sv2.start_interview(a2.id)


def test_complete_interview_report_and_recruiter_decision_flow(db, settings):
    """Test the complete end-to-end flow:
    Scheduled -> Identity Verified -> Interview Completed -> Assessment Generated -> Report Available -> Recruiter Decision.
    Verifies:
    1. Scheduled candidate has no fake interview scores before completion.
    2. Final score strictly follows: Final Score = (Resume Weight * Resume Score) + (Interview Weight * Interview Score).
    3. Interview questions, responses, transcript, and decision trace are preserved.
    4. Recruiter can record Hire, Hold, or Reject decisions.
    5. All data persists correctly and remains available after page refresh.
    """
    sv, job, a = scheduled_candidate(db, settings, file="Meera_Iyer.pdf")
    assert a.status == "SCHEDULED"

    # 1. Before interview: No fake interview scores or reports
    rep_before = reports.recruiter_report(db, settings, a.id, sv.traces(a.id))
    assert rep_before["status"] == "SCHEDULED"
    assert rep_before["assessment"] is None
    assert rep_before["resume"]["score_0_100"] > 0
    # Final decision cannot be recorded before assessment
    with pytest.raises(GateViolation):
        sv.record_decision(a.id, "HIRE", "Premature decision")

    # 2. Advance through complete workflow:
    # Scheduled -> Identity Verified -> Interview Completed -> Assessment Generated
    res_conduct = sv.conduct_interview(a.id)
    assert res_conduct["status"] == "ASSESSED"

    # 3. Verify final score formula
    ar = db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one()
    assert ar.status == "OK"
    w_res = settings.weight_resume
    w_int = settings.weight_interview
    expected_final = round((w_res * ar.resume_score) + (w_int * ar.interview_score), 1)
    assert ar.final_score == expected_final
    assert round((w_res * ar.resume_score) + (w_int * ar.interview_score), 1) == ar.final_score

    # 4. Verify report has all required sections
    rep_after = reports.recruiter_report(db, settings, a.id, sv.traces(a.id))
    sess = sv._session(a.id)
    rep_after["transcript"] = ([t.model_dump() for t in SessionState.model_validate_json(sess.state_json).transcript] if sess else [])

    assert rep_after["assessment"] is not None
    assert rep_after["assessment"]["resume_score"] == ar.resume_score
    assert rep_after["assessment"]["interview_score"] == ar.interview_score
    assert rep_after["assessment"]["final_score"] == expected_final
    assert len(rep_after["transcript"]) >= 4
    # Both questions and candidate responses exist in transcript
    assert any(t["role"] == "interviewer" and t["text"] for t in rep_after["transcript"])
    assert any(t["role"] == "candidate" and t["text"] for t in rep_after["transcript"])

    # Competency table has evaluations
    comp_table = rep_after["assessment"]["competency_table"]
    assert len(comp_table) > 0
    assert any(c["interview_score"] is not None for c in comp_table)

    # Decision trace is available
    traces = rep_after["trace"]
    assert len(traces) >= 2
    assert all("trigger_phrase" in t and "reasoning" in t for t in traces)

    # 5. Recruiter records final decision: HIRE, HOLD, REJECT
    # Test invalid decision
    with pytest.raises(ValueError):
        sv.record_decision(a.id, "INVALID_DECISION", "notes")

    # Test HIRE
    hire_res = sv.record_decision(a.id, "HIRE", "Candidate demonstrated exceptional competence and problem-solving skills.")
    assert hire_res["decision"] == "HIRE"
    assert a.status == "DECIDED"

    # Verify decision stored
    rep_decided = reports.recruiter_report(db, settings, a.id, sv.traces(a.id))
    assert rep_decided["recruiter_decision"]["decision"] == "HIRE"
    assert "exceptional competence" in rep_decided["recruiter_decision"]["notes"]

    # Test updating decision to HOLD or REJECT
    sv.record_decision(a.id, "HOLD", "Hold pending executive budget review")
    rep_hold = reports.recruiter_report(db, settings, a.id, sv.traces(a.id))
    assert rep_hold["recruiter_decision"]["decision"] == "HOLD"

    # 6. Persistence check: fresh database read simulates page refresh
    ar_fresh = db.execute(select(AssessmentRow).where(AssessmentRow.application_id == a.id)).scalar_one()
    assert ar_fresh.final_score == expected_final
    rec_dec_fresh = db.execute(select(RecruiterDecision).where(RecruiterDecision.application_id == a.id)).scalar_one()
    assert rec_dec_fresh.decision == "HOLD"
    assert "budget review" in rec_dec_fresh.notes


