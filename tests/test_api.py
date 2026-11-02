"""HTTP-level tests. Require fastapi + httpx (see requirements.txt); skipped automatically if missing."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app.api.main import create_app  # noqa: E402
from tests.helpers import ANSWER_BANK, SAMPLE  # noqa: E402


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def upload(client, job_id, name):
    f = SAMPLE / "resumes" / name
    return client.post(f"/jobs/{job_id}/applications", files={"file": (name, f.read_bytes())})


def test_health_and_config_label_demo_mode(client):
    assert client.get("/health").json() == {"status": "ok"}
    c = client.get("/config").json()
    assert c["demo_llm"] is True and c["identity_is_demo"] is True


def test_bad_uploads_are_rejected_cleanly(client):
    job = client.post("/jobs/load-sample").json()
    r = client.post(f"/jobs/{job['id']}/applications", files={"file": ("x.exe", b"MZ")})
    assert r.status_code == 422
    assert client.post("/jobs/999/applications", files={"file": ("x.txt", b"hello world" * 10)}).status_code == 404


def test_invalid_job_payload_is_422(client):
    assert client.post("/jobs", json={"title": "x", "competencies": []}).status_code == 422


def test_recruiter_api_key_enforced(settings):
    settings.recruiter_api_key = "secret"
    c = TestClient(create_app(settings))
    assert c.get("/jobs").status_code == 401
    assert c.get("/jobs", headers={"X-API-Key": "secret"}).status_code == 200


def test_candidate_token_required(client):
    assert client.get("/portal/me").status_code == 401
    assert client.get("/portal/me", headers={"X-Access-Token": "nope"}).status_code == 401


def test_full_flow_over_http_with_gate(client):
    job = client.post("/jobs/load-sample").json()
    ids = [upload(client, job["id"], n).json()["application_id"] for n in ("Aarav_Mehta.docx", "Karan_Shah.docx")]
    ranking = client.post(f"/jobs/{job['id']}/screen").json()
    assert ranking["ranking"][0]["name"] == "Aarav Mehta"
    top = ranking["ranking"][0]["application_id"]
    assert client.post(f"/jobs/{job['id']}/shortlist", json={"application_ids": [top]}).status_code == 200
    sched = client.post(f"/jobs/{job['id']}/schedule").json()
    assert sched[0]["scheduled"], "sample calendar slots must be in the future - re-run data/generate_demo_data.py"
    H = {"X-Access-Token": sched[0]["access_token"]}
    # gate: interview refused before identity verification
    assert client.post("/portal/interview/start", headers=H).status_code == 409
    # failed identity -> human review, still blocked
    r = client.post("/portal/identity-check", headers=H, data={"scenario": "different_person"}).json()
    assert r["passed"] is False
    assert client.post("/portal/interview/start", headers=H).status_code == 409
    review = client.get("/reviews").json()[0]
    client.post(f"/reviews/{review['id']}/resolve", json={"resolution": "approve_retry"})
    assert client.post("/portal/identity-check", headers=H, data={"scenario": "match"}).json()["passed"] is True
    q = client.post("/portal/interview/start", headers=H).json()
    assert q["question"]
    out = q
    for _ in range(20):
        cid = out["competency_id"]
        out = client.post("/portal/interview/answer", headers=H, json={"answer": ANSWER_BANK.get(cid, ANSWER_BANK["_generic"])}).json()
        if out["concluded"]:
            break
    assert out["concluded"]
    rep = client.get(f"/applications/{top}/report").json()
    assert rep["assessment"]["final_score"] is not None and rep["status"] == "ASSESSED"
    fb = client.get("/portal/feedback", headers=H).json()
    assert fb["available"] and "label" not in fb and "final_score" not in fb
    assert client.post(f"/applications/{top}/decision", json={"decision": "ADVANCE", "notes": "ok"}).status_code == 200
    assert client.post("/portal/interview/answer", headers=H, json={"answer": "late"}).status_code == 409


def _prepare(client, files=("Aarav_Mehta.docx", "Priya_Nair.pdf", "Karan_Shah.docx")):
    job = client.post("/jobs/load-sample").json()
    for n in files:
        assert upload(client, job["id"], n).status_code == 200
    return job


def test_overview_reflects_real_state_and_next_action(client):
    assert client.get("/overview").json()["next_action"]["page"] == "Jobs"          # nothing exists yet
    job = _prepare(client)
    o = client.get("/overview").json()
    assert o["metrics"]["total_applicants"] == 3 and o["metrics"]["awaiting_screening"] == 3
    assert o["next_action"]["key"] == "screen" and o["metrics"]["free_slots"] > 0
    client.post(f"/jobs/{job['id']}/screen")
    o = client.get("/overview").json()
    assert o["metrics"]["awaiting_review"] == 3 and o["next_action"]["key"] == "shortlist"
    assert o["per_job"][0]["scored"] == 3 and o["funnel"][1]["count"] == 3


def test_multiple_resume_uploads_are_all_processed_and_listed(client):
    job = _prepare(client, ("Aarav_Mehta.docx", "Priya_Nair.pdf", "Rohan_Gupta.docx", "Sneha_Kulkarni.pdf"))
    res = client.post(f"/jobs/{job['id']}/screen").json()
    assert len(res["scored"]) == 4 and not res["failed"]
    apps = client.get(f"/jobs/{job['id']}/applications").json()
    assert len(apps) == 4 and all(a["resume_score"] is not None and a["scoring_source"] == "demo_rules" for a in apps)
    allapps = client.get("/applications").json()
    assert len(allapps) == 4 and allapps[0]["job_title"] == "Backend Python Engineer"


def test_slots_and_reviews_are_enriched_for_the_ui(client):
    job = _prepare(client)
    client.post(f"/jobs/{job['id']}/screen")
    top = client.get(f"/jobs/{job['id']}/applications").json()[0]["application_id"]
    client.post(f"/jobs/{job['id']}/shortlist", json={"application_ids": [top]})
    sched = client.post(f"/jobs/{job['id']}/schedule").json()
    booked = [s for s in client.get("/slots").json() if s["application_id"]]
    assert len(booked) == 1 and booked[0]["candidate"] and booked[0]["job_title"] and booked[0]["confirmation_file"] is True
    H = {"X-Access-Token": sched[0]["access_token"]}
    me = client.get("/portal/me", headers=H).json()
    assert me["job_title"] == "Backend Python Engineer" and me["max_questions"] == 8
    client.post("/portal/identity-check", headers=H, data={"scenario": "no_face"})
    r = client.get("/reviews").json()
    assert r[0]["candidate"] and r[0]["job_title"] and r[0]["status"] == "OPEN"
    client.post(f"/reviews/{r[0]['id']}/resolve", json={"resolution": "reject", "notes": "unverifiable"})
    assert client.get("/reviews").json() == [] and client.get("/reviews?status=RESOLVED").json()[0]["resolution"] == "reject"
    assert len(client.get("/reviews?status=ALL").json()) == 1


def test_report_has_transcript_and_candidate_feedback_has_no_private_fields(client):
    job = _prepare(client, ("Aarav_Mehta.docx",))
    client.post(f"/jobs/{job['id']}/screen")
    app_id = client.get(f"/jobs/{job['id']}/applications").json()[0]["application_id"]
    client.post(f"/jobs/{job['id']}/shortlist", json={"application_ids": [app_id]})
    H = {"X-Access-Token": client.post(f"/jobs/{job['id']}/schedule").json()[0]["access_token"]}
    client.post("/portal/identity-check", headers=H, data={"scenario": "match"})
    out = client.post("/portal/interview/start", headers=H).json()
    for _ in range(20):
        out = client.post("/portal/interview/answer", headers=H, json={"answer": ANSWER_BANK.get(out["competency_id"], ANSWER_BANK["_generic"])}).json()
        if out["concluded"]:
            break
    rep = client.get(f"/applications/{app_id}/report").json()
    assert rep["transcript"][0]["role"] == "interviewer" and any(t["role"] == "candidate" for t in rep["transcript"])
    fb = client.get("/portal/feedback", headers=H).json()
    blob = str(fb).lower()
    for private in ("final_score", "resume_score", "recommend", "label", "rank", "@example.com"):
        assert private not in blob
    assert fb["competencies"] and all(set(c) == {"name", "level", "evidence"} for c in fb["competencies"])


def test_candidate_cannot_reach_recruiter_routes_with_api_key_enabled(settings):
    settings.recruiter_api_key = "k"
    c = TestClient(create_app(settings))
    c.post("/jobs/load-sample", headers={"X-API-Key": "k"})
    for path in ("/overview", "/applications", "/slots", "/reviews", "/jobs"):
        assert c.get(path).status_code == 401                              # no key -> refused, token or not
    assert c.get("/overview", headers={"X-Access-Token": "anything"}).status_code == 401


def test_calendar_generation_is_idempotent_and_keeps_bookings(client):
    assert client.post("/calendar/generate").json()["slots_added"] == 40
    assert client.post("/calendar/generate").json()["slots_added"] == 0
    assert len(client.get("/slots").json()) == 40


def test_identity_candidates_endpoint_and_lifecycle(client):
    job = client.post("/jobs/load-sample").json()
    ids = [upload(client, job["id"], n).json()["application_id"] for n in ("Aarav_Mehta.docx", "Karan_Shah.docx")]
    client.post(f"/jobs/{job['id']}/screen")
    client.post(f"/jobs/{job['id']}/shortlist", json={"application_ids": ids})
    sched = client.post(f"/jobs/{job['id']}/schedule").json()
    assert len(sched) == 2

    # 1. Initially, both candidates should appear in 'pending'
    id_overview = client.get("/identity/candidates").json()
    assert id_overview["threshold"] == 0.70
    assert id_overview["is_demo"] is True
    assert len(id_overview["pending"]) >= 2
    assert len(id_overview["action_required"]) == 0

    token1 = sched[0]["access_token"]
    token2 = sched[1]["access_token"]

    # 2. Candidate 1 executes successful identity check
    client.post("/portal/identity-check", headers={"X-Access-Token": token1}, data={"scenario": "match"})

    # 3. Candidate 2 executes failed identity check
    client.post("/portal/identity-check", headers={"X-Access-Token": token2}, data={"scenario": "different_person"})

    # Check overview categorization
    overview2 = client.get("/identity/candidates").json()
    assert any(c["application_id"] == sched[0]["application_id"] for c in overview2["passed"])
    assert any(c["application_id"] == sched[1]["application_id"] for c in overview2["action_required"])

    failed_cand = next(c for c in overview2["action_required"] if c["application_id"] == sched[1]["application_id"])
    assert failed_cand["identity_status"] == "FAILED"
    assert failed_cand["latest_check"]["face_count"] == 1
    assert failed_cand["latest_check"]["confidence"] < 0.70
    assert failed_cand["open_review"] is not None

    # 4. Mandatory notes validation: empty notes should be rejected
    rev_id = failed_cand["open_review"]["id"]
    res_err = client.post(f"/reviews/{rev_id}/resolve", json={"resolution": "approve_manual_pass", "notes": ""})
    assert res_err.status_code == 400 or res_err.status_code == 422 or "notes are required" in res_err.text

    # 5. Recruiter resolves with mandatory notes
    res_ok = client.post(f"/reviews/{rev_id}/resolve", json={"resolution": "approve_manual_pass", "notes": "Approved via manual passport verification"})
    assert res_ok.status_code == 200

    # 6. Check resolved tab in overview
    overview3 = client.get("/identity/candidates").json()
    assert any(c["application_id"] == sched[1]["application_id"] for c in overview3["passed"])
    assert any(r["application_id"] == sched[1]["application_id"] for r in overview3["resolved"])
    resolved_item = next(r for r in overview3["resolved"] if r["application_id"] == sched[1]["application_id"])
    assert resolved_item["resolution"] == "approve_manual_pass"
    assert "Approved via manual passport" in resolved_item["notes"]


def test_conduct_interview_api_and_recruiter_decision(client):
    job = client.post("/jobs/load-sample").json()
    app_id = upload(client, job["id"], "Meera_Iyer.pdf").json()["application_id"]
    client.post(f"/jobs/{job['id']}/screen")
    client.post(f"/jobs/{job['id']}/shortlist", json={"application_ids": [app_id]})
    sched = client.post(f"/jobs/{job['id']}/schedule").json()
    assert len(sched) == 1

    # 1. Before interview: report shows assessment is null and decision is blocked
    rep_before = client.get(f"/applications/{app_id}/report").json()
    assert rep_before["assessment"] is None
    res_early_dec = client.post(f"/applications/{app_id}/decision", json={"decision": "HIRE", "notes": "Premature"})
    assert res_early_dec.status_code in (400, 409)

    # 2. Advance workflow via conduct-interview
    res_conduct = client.post(f"/applications/{app_id}/conduct-interview")
    assert res_conduct.status_code == 200
    assert res_conduct.json()["status"] == "ASSESSED"

    # 3. Read complete report
    rep = client.get(f"/applications/{app_id}/report").json()
    asm = rep["assessment"]
    assert asm is not None
    assert asm["resume_score"] > 0
    assert asm["interview_score"] > 0
    w_res = rep["configured_weights"]["resume"]
    w_int = rep["configured_weights"]["interview"]
    expected_final = round((w_res * asm["resume_score"]) + (w_int * asm["interview_score"]), 1)
    assert asm["final_score"] == expected_final

    # Transcript and competency table checks
    assert len(rep["transcript"]) >= 4
    assert any(c["interview_score"] is not None for c in asm["competency_table"])

    # 4. Record Recruiter Hiring Decision
    res_dec = client.post(f"/applications/{app_id}/decision", json={"decision": "HIRE", "notes": "Approved for offer."})
    assert res_dec.status_code == 200

    # 5. Verify decision recorded in report
    rep_decided = client.get(f"/applications/{app_id}/report").json()
    assert rep_decided["status"] == "DECIDED"
    assert rep_decided["recruiter_decision"]["decision"] == "HIRE"
    assert "Approved for offer" in rep_decided["recruiter_decision"]["notes"]


