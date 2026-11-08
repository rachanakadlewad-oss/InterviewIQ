"""Comprehensive end-to-end verification of Candidate Dashboard & Portal workflow:
1. Candidate account signup & authentication
2. Browse active open positions (/portal/jobs)
3. Submit application with resume upload & AI scoring (/portal/jobs/{id}/apply)
4. View application details, AI match score, and stepper (/portal/me)
5. Recruiter shortlists and schedules interview
6. Identity verification (/portal/identity-check)
7. Autonomous AI interview (/portal/interview/start & answer)
8. Candidate feedback retrieval (/portal/feedback)
9. Candidate password change & security validation
"""
import pytest
from fastapi.testclient import TestClient

from app.api.main import create_app
from tests.helpers import ANSWER_BANK, SAMPLE


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def test_candidate_complete_dashboard_workflow(client):
    # -------------------------------------------------------------------------
    # 1. Setup: Recruiter creates a job
    # -------------------------------------------------------------------------
    job_res = client.post("/jobs/load-sample")
    assert job_res.status_code == 200
    job_id = job_res.json()["id"]

    # -------------------------------------------------------------------------
    # 2. Candidate Registration & Login
    # -------------------------------------------------------------------------
    signup_res = client.post("/auth/signup", json={
        "name": "Maya Lin",
        "email": "maya.lin@example.com",
        "password": "MayaStrongPass123!",
        "confirm_password": "MayaStrongPass123!",
        "role": "candidate"
    })
    assert signup_res.status_code == 200
    auth_data = signup_res.json()
    token = auth_data["token"]
    auth_headers = {"Authorization": f"Bearer {token}"}
    assert auth_data["user"]["email"] == "maya.lin@example.com"
    assert auth_data["user"]["role"] == "candidate"

    # Verify no plaintext password or hash in response
    assert "password" not in auth_data["user"]
    assert "password_hash" not in auth_data["user"]

    # -------------------------------------------------------------------------
    # 3. Candidate Explores Open Jobs
    # -------------------------------------------------------------------------
    jobs_res = client.get("/portal/jobs")
    assert jobs_res.status_code == 200
    jobs_list = jobs_res.json()
    assert len(jobs_list) >= 1
    target_job = next(j for j in jobs_list if j["id"] == job_id)
    assert target_job["title"]

    # -------------------------------------------------------------------------
    # 4. Candidate Applies for Job (Submits Resume)
    # -------------------------------------------------------------------------
    pdf_bytes = (SAMPLE / "resumes" / "Meera_Iyer.pdf").read_bytes()
    apply_res = client.post(
        f"/portal/jobs/{job_id}/apply",
        headers=auth_headers,
        files={"file": ("Maya_Lin_Resume.pdf", pdf_bytes, "application/pdf")}
    )
    assert apply_res.status_code == 200
    apply_data = apply_res.json()
    app_id = apply_data["application_id"]
    access_token = apply_data["access_token"]
    assert app_id is not None
    assert access_token is not None
    assert 0.0 <= apply_data["ai_score"] <= 100.0

    # -------------------------------------------------------------------------
    # 5. Candidate Views "My Application" (/portal/me & /portal/applications)
    # -------------------------------------------------------------------------
    apps_res = client.get("/portal/applications", headers=auth_headers)
    assert apps_res.status_code == 200
    my_apps = apps_res.json()
    assert len(my_apps) == 1
    assert my_apps[0]["application_id"] == app_id

    me_res = client.get("/portal/me", headers=auth_headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["application_id"] == app_id
    assert me_data["access_token"] == access_token
    assert me_data["ai_score"] is not None

    cand_headers = {"X-Access-Token": access_token}

    # -------------------------------------------------------------------------
    # 6. Candidate cannot start interview before shortlisting & scheduling
    # -------------------------------------------------------------------------
    assert client.post("/portal/interview/start", headers=cand_headers).status_code == 409

    # Recruiter shortlists and schedules candidate
    client.patch(f"/applications/{app_id}/status", json={"action": "SHORTLIST"})
    client.post(f"/jobs/{job_id}/schedule")

    # -------------------------------------------------------------------------
    # 7. Candidate Identity Verification
    # -------------------------------------------------------------------------
    id_res = client.post(
        "/portal/identity-check",
        headers=cand_headers,
        data={"scenario": "match", "check_type": "pre_interview"}
    )
    assert id_res.status_code == 200
    assert id_res.json()["passed"] is True

    # -------------------------------------------------------------------------
    # 8. Candidate Attends Multi-turn AI Interview
    # -------------------------------------------------------------------------
    start_res = client.post("/portal/interview/start", headers=cand_headers)
    assert start_res.status_code == 200
    q_data = start_res.json()
    assert "question" in q_data

    # Multi-turn answering until conclusion
    concluded = False
    turns = 0
    cid = q_data.get("competency_id", "c1")
    while not concluded and turns < 10:
        ans_text = ANSWER_BANK.get(cid, ANSWER_BANK["_generic"])
        ans_res = client.post("/portal/interview/answer", headers=cand_headers, json={"answer": ans_text})
        assert ans_res.status_code == 200
        turn_data = ans_res.json()
        turns += 1
        if turn_data.get("concluded"):
            concluded = True
            break
        cid = turn_data.get("competency_id", cid)

    # -------------------------------------------------------------------------
    # 9. Candidate Views My Feedback
    # -------------------------------------------------------------------------
    fb_res = client.get("/portal/feedback", headers=cand_headers)
    assert fb_res.status_code == 200
    fb_data = fb_res.json()
    assert fb_data["available"] is True
    assert "strengths" in fb_data
    assert "weaknesses" in fb_data
    assert "competencies" in fb_data

    # Verify score, rank, and internal hiring decisions are NOT leaked to candidate
    assert "ai_score" not in fb_data
    assert "rank" not in fb_data
    assert "decision" not in fb_data

    # -------------------------------------------------------------------------
    # 10. Candidate Changes Password Securely
    # -------------------------------------------------------------------------
    change_res = client.post("/auth/change-password", headers=auth_headers, json={
        "current_password": "MayaStrongPass123!",
        "new_password": "MayaUpdatedPass456!",
        "confirm_new_password": "MayaUpdatedPass456!"
    })
    assert change_res.status_code == 200
    assert "token" in change_res.json()

    # Old password fails
    assert client.post("/auth/login", json={
        "email": "maya.lin@example.com",
        "password": "MayaStrongPass123!",
        "role": "candidate"
    }).status_code == 401

    # New password succeeds
    login_new = client.post("/auth/login", json={
        "email": "maya.lin@example.com",
        "password": "MayaUpdatedPass456!",
        "role": "candidate"
    })
    assert login_new.status_code == 200
    assert login_new.json()["user"]["email"] == "maya.lin@example.com"
