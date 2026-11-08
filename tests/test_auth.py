"""Tests for InterviewIQ Authentication and Role-Based Authorization.
Covers:
- Password hashing (bcrypt) and validation
- JWT creation, decoding, expiration, and session revocation
- Recruiter signup, login, authorized access, candidate endpoint rejection (403)
- Candidate signup, login, authorized access, recruiter endpoint rejection (403)
- Security checks: duplicate emails, wrong role login, password mismatch, invalid emails
- Preserving candidate access-token links and preventing cross-candidate access
"""
import pytest
from fastapi.testclient import TestClient

from app import db as dbm
from app.api.main import create_app
from app.config import Settings
from app.db import Application, Job, User, UserSession
from app.services import auth as auth_svc


@pytest.fixture
def auth_settings(tmp_path):
    s = Settings(
        data_dir=str(tmp_path / "rt"),
        database_url=f"sqlite:///{tmp_path / 'auth_test.db'}",
        jwt_secret_key="test-super-secret-key-at-least-32-chars-long!",
        jwt_algorithm="HS256",
        jwt_expiration_hours=1,
        require_auth=True,
        llm_provider="demo"
    )
    return s


@pytest.fixture
def app_and_client(auth_settings):
    dbm.init_db(auth_settings.database_url)
    app = create_app(auth_settings)
    client = TestClient(app)
    return app, client, auth_settings


# ==============================================================================
# 1. Password Hashing and Token Unit Tests
# ==============================================================================
def test_password_hashing():
    pw = "SuperSecure123!"
    h1 = auth_svc.hash_password(pw)
    assert h1 != pw
    assert h1.startswith("$2b$") or h1.startswith("$2a$")
    assert auth_svc.verify_password(pw, h1) is True
    assert auth_svc.verify_password("WrongPassword", h1) is False


def test_email_and_password_validation():
    assert auth_svc.is_valid_email("recruiter@interviewiq.com") is True
    assert auth_svc.is_valid_email("candidate.test+tag@sub.domain.co") is True
    assert auth_svc.is_valid_email("invalid-email") is False
    assert auth_svc.is_valid_email("@no-user.com") is False

    assert auth_svc.validate_password_strength("short") is not None
    assert auth_svc.validate_password_strength("validpassword8") is None


def test_jwt_token_lifecycle(auth_settings):
    token, jti, exp = auth_svc.create_access_token(
        user_id=42,
        email="test@example.com",
        role="recruiter",
        name="Alex Recruiter",
        secret_key=auth_settings.jwt_secret_key,
        expires_hours=1,
        algorithm=auth_settings.jwt_algorithm
    )
    assert token and isinstance(token, str)
    assert jti and len(jti) in (32, 36)

    payload = auth_svc.decode_access_token(
        token,
        secret_key=auth_settings.jwt_secret_key,
        algorithm=auth_settings.jwt_algorithm
    )
    assert payload["sub"] == "42"
    assert payload["email"] == "test@example.com"
    assert payload["role"] == "recruiter"
    assert payload["name"] == "Alex Recruiter"
    assert payload["jti"] == jti


# ==============================================================================
# 2. Recruiter Signup and Login Flow Tests
# ==============================================================================
def test_recruiter_signup_and_login(app_and_client):
    _, client, _ = app_and_client

    # 1. Signup recruiter
    signup_res = client.post("/auth/signup", json={
        "name": "Sarah Connor",
        "email": "sarah.connor@cyberdyne.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "recruiter"
    })
    assert signup_res.status_code == 200, signup_res.text
    signup_data = signup_res.json()
    assert "token" in signup_data
    assert signup_data["user"]["role"] == "recruiter"
    assert signup_data["user"]["email"] == "sarah.connor@cyberdyne.com"

    # Verify password is not in plaintext in DB
    session = dbm.new_session()
    user = session.get(User, signup_data["user"]["id"])
    assert user is not None
    assert user.password_hash != "Password123!"
    assert auth_svc.verify_password("Password123!", user.password_hash)
    session.close()

    # 2. Login recruiter
    login_res = client.post("/auth/login", json={
        "email": "sarah.connor@cyberdyne.com",
        "password": "Password123!",
        "role": "recruiter"
    })
    assert login_res.status_code == 200, login_res.text
    login_data = login_res.json()
    assert "token" in login_data
    assert login_data["user"]["name"] == "Sarah Connor"


# ==============================================================================
# 3. Candidate Signup and Login Flow Tests
# ==============================================================================
def test_candidate_signup_and_login(app_and_client):
    _, client, _ = app_and_client

    # 1. Signup candidate
    signup_res = client.post("/auth/signup", json={
        "name": "John Connor",
        "email": "john.connor@resistance.net",
        "password": "ResistancePass123",
        "confirm_password": "ResistancePass123",
        "role": "candidate"
    })
    assert signup_res.status_code == 200, signup_res.text
    signup_data = signup_res.json()
    assert "token" in signup_data
    assert signup_data["user"]["role"] == "candidate"

    # 2. Login candidate
    login_res = client.post("/auth/login", json={
        "email": "john.connor@resistance.net",
        "password": "ResistancePass123",
        "role": "candidate"
    })
    assert login_res.status_code == 200, login_res.text
    assert "token" in login_res.json()


# ==============================================================================
# 4. Role-Based Authorization and Cross-Role Rejection Tests
# ==============================================================================
def test_role_based_access_control(app_and_client):
    _, client, _ = app_and_client

    # Register recruiter
    r_tok = client.post("/auth/signup", json={
        "name": "Recruiter One",
        "email": "recruiter1@hiring.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "recruiter"
    }).json()["token"]

    # Register candidate
    c_tok = client.post("/auth/signup", json={
        "name": "Candidate One",
        "email": "candidate1@jobseeker.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "candidate"
    }).json()["token"]

    recruiter_headers = {"Authorization": f"Bearer {r_tok}"}
    candidate_headers = {"Authorization": f"Bearer {c_tok}"}

    # Recruiter can access recruiter endpoints
    res_jobs = client.get("/jobs", headers=recruiter_headers)
    assert res_jobs.status_code == 200

    # Candidate is strictly REJECTED from recruiter endpoints with 403 Forbidden
    res_cand_on_jobs = client.get("/jobs", headers=candidate_headers)
    assert res_cand_on_jobs.status_code == 403
    assert "recruiter access required" in res_cand_on_jobs.json()["detail"].lower()

    # Recruiter is strictly REJECTED from candidate portal endpoints with 403 Forbidden
    res_rec_on_portal = client.get("/portal/me", headers=recruiter_headers)
    assert res_rec_on_portal.status_code == 403
    assert "candidate access required" in res_rec_on_portal.json()["detail"].lower()

    # Unauthenticated request to recruiter endpoint rejected with 401
    assert client.get("/jobs").status_code == 401

    # Unauthenticated request to portal/me without token rejected with 401
    assert client.get("/portal/me").status_code == 401


# ==============================================================================
# 5. Security Validation Tests: Errors, Wrong Roles, Duplicate Registration
# ==============================================================================
def test_security_validations(app_and_client):
    _, client, _ = app_and_client

    # 1. Weak password rejected
    r = client.post("/auth/signup", json={
        "name": "Short Pass",
        "email": "short@test.com",
        "password": "123",
        "confirm_password": "123",
        "role": "recruiter"
    })
    assert r.status_code == 422
    assert "at least 8" in r.text

    # 2. Password mismatch rejected
    r = client.post("/auth/signup", json={
        "name": "Mismatch Pass",
        "email": "mismatch@test.com",
        "password": "ValidPassword123!",
        "confirm_password": "DifferentPassword123!",
        "role": "recruiter"
    })
    assert r.status_code == 422
    assert "match" in r.text

    # 3. Invalid email rejected
    r = client.post("/auth/signup", json={
        "name": "Bad Email",
        "email": "not-an-email",
        "password": "ValidPassword123!",
        "confirm_password": "ValidPassword123!",
        "role": "recruiter"
    })
    assert r.status_code == 422
    assert "Invalid email" in r.text

    # 4. Duplicate email rejected with 409
    r1 = client.post("/auth/signup", json={
        "name": "Original User",
        "email": "unique@company.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "recruiter"
    })
    assert r1.status_code == 200

    r2 = client.post("/auth/signup", json={
        "name": "Impostor User",
        "email": "unique@company.com",
        "password": "OtherPassword123!",
        "confirm_password": "OtherPassword123!",
        "role": "recruiter"
    })
    assert r2.status_code == 409
    assert "already exists" in r2.text

    # 5. Incorrect password on login rejected with 401
    r_bad_pw = client.post("/auth/login", json={
        "email": "unique@company.com",
        "password": "WrongPassword999",
        "role": "recruiter"
    })
    assert r_bad_pw.status_code == 401
    assert "Invalid email or password" in r_bad_pw.text

    # 6. Wrong role login rejected with 403
    r_wrong_role = client.post("/auth/login", json={
        "email": "unique@company.com",
        "password": "Password123!",
        "role": "candidate"  # User registered as recruiter
    })
    assert r_wrong_role.status_code == 403
    assert "registered as a recruiter" in r_wrong_role.text


# ==============================================================================
# 6. Logout and Session Invalidation Tests
# ==============================================================================
def test_logout_session_invalidation(app_and_client):
    _, client, _ = app_and_client

    # Signup and get session
    r = client.post("/auth/signup", json={
        "name": "Logout Tester",
        "email": "logout@test.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "recruiter"
    })
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Verify access is authorized
    assert client.get("/auth/me", headers=headers).status_code == 200

    # Logout
    logout_res = client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == 200
    assert logout_res.json()["status"] == "ok"

    # Subsequent access with same token is rejected (401 revoked)
    check_again = client.get("/auth/me", headers=headers)
    assert check_again.status_code == 401
    assert "revoked" in check_again.text.lower() or "expired" in check_again.text.lower()


# ==============================================================================
# 7. Candidate Application Token Preservation & Auto-Linking Tests
# ==============================================================================
def test_candidate_application_linking_and_token_compatibility(app_and_client):
    _, client, _ = app_and_client

    session = dbm.new_session()
    # Create sample job
    job = Job(title="Security Engineer", description="SecOps", competencies_json="[]")
    session.add(job)
    session.flush()

    # Pre-existing application with an access token (before user created an account)
    app_record = Application(
        job_id=job.id,
        candidate_name="Devon Hunter",
        email="devon.hunter@example.com",
        access_token="devon-token-uuid-12345",
        status="APPLIED"
    )
    session.add(app_record)
    session.commit()
    app_id = app_record.id
    raw_access_token = app_record.access_token
    session.close()

    # 1. Verify candidate direct access token works WITHOUT account (backward compatibility)
    res_direct = client.get("/portal/me", headers={"X-Access-Token": raw_access_token})
    assert res_direct.status_code == 200
    assert res_direct.json()["name"] == "Devon Hunter"
    assert res_direct.json()["application_id"] == app_id

    # 2. Candidate registers with matching email
    cand_signup = client.post("/auth/signup", json={
        "name": "Devon Hunter",
        "email": "devon.hunter@example.com",
        "password": "HunterPassword123!",
        "confirm_password": "HunterPassword123!",
        "role": "candidate"
    })
    assert cand_signup.status_code == 200
    cand_token = cand_signup.json()["token"]
    cand_headers = {"Authorization": f"Bearer {cand_token}"}

    # 3. Application should now be auto-linked to this candidate
    apps_res = client.get("/portal/applications", headers=cand_headers)
    assert apps_res.status_code == 200
    my_apps = apps_res.json()
    assert len(my_apps) == 1
    assert my_apps[0]["application_id"] == app_id
    assert my_apps[0]["access_token"] == raw_access_token

    # 4. Access portal/me directly with candidate JWT (auto-resolves linked application)
    portal_me_res = client.get("/portal/me", headers=cand_headers)
    assert portal_me_res.status_code == 200
    assert portal_me_res.json()["name"] == "Devon Hunter"

    # 5. Security: Cross-candidate token hijacking is prevented
    # Another candidate cannot use Devon's token
    other_cand_tok = client.post("/auth/signup", json={
        "name": "Attacker Bob",
        "email": "bob@attacker.com",
        "password": "Password123!",
        "confirm_password": "Password123!",
        "role": "candidate"
    }).json()["token"]

    hijack_res = client.get(
        "/portal/me",
        headers={"Authorization": f"Bearer {other_cand_tok}", "X-Access-Token": raw_access_token}
    )
    assert hijack_res.status_code == 403
    assert "does not belong" in hijack_res.text


# ==============================================================================
# 5. Password Security, Change Password, and Reset Password Tests
# ==============================================================================
def test_breached_and_weak_passwords_rejected():
    # Common breached passwords rejected
    assert auth_svc.validate_password_strength("12345678") is not None
    assert auth_svc.validate_password_strength("password") is not None
    assert auth_svc.validate_password_strength("admin123") is not None
    assert auth_svc.validate_password_strength("admin1234") is not None

    # Missing digits or letters rejected
    assert auth_svc.validate_password_strength("alllettersonly") is not None
    assert auth_svc.validate_password_strength("1234567890") is not None

    # Short password rejected
    assert auth_svc.validate_password_strength("short1") is not None

    # Strong passwords accepted
    assert auth_svc.validate_password_strength("StrongPass99!") is None
    assert auth_svc.validate_password_strength("ValidPassw0rd") is None


def test_password_change_flow(app_and_client):
    _, client, _ = app_and_client

    # 1. Register recruiter
    res = client.post("/auth/signup", json={
        "name": "Grace Hopper",
        "email": "grace@navy.mil",
        "password": "InitialPass123!",
        "confirm_password": "InitialPass123!",
        "role": "recruiter"
    })
    assert res.status_code == 200
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Change password: wrong old password -> 401
    bad_old = client.post("/auth/change-password", headers=headers, json={
        "current_password": "WrongPassword123!",
        "new_password": "NewSecurePass123!",
        "confirm_new_password": "NewSecurePass123!"
    })
    assert bad_old.status_code == 401

    # 3. Change password: same as old password -> 422
    same_pw = client.post("/auth/change-password", headers=headers, json={
        "current_password": "InitialPass123!",
        "new_password": "InitialPass123!",
        "confirm_new_password": "InitialPass123!"
    })
    assert same_pw.status_code == 422

    # 4. Change password: weak/breached new password -> 422
    weak_pw = client.post("/auth/change-password", headers=headers, json={
        "current_password": "InitialPass123!",
        "new_password": "admin123",
        "confirm_new_password": "admin123"
    })
    assert weak_pw.status_code == 422

    # 5. Change password: successful update -> 200
    change_ok = client.post("/auth/change-password", headers=headers, json={
        "current_password": "InitialPass123!",
        "new_password": "NewStrongPass456!",
        "confirm_new_password": "NewStrongPass456!"
    })
    assert change_ok.status_code == 200
    assert "token" in change_ok.json()

    # 6. Old password must no longer work for login
    old_login = client.post("/auth/login", json={
        "email": "grace@navy.mil",
        "password": "InitialPass123!",
        "role": "recruiter"
    })
    assert old_login.status_code == 401

    # 7. New password logs in successfully
    new_login = client.post("/auth/login", json={
        "email": "grace@navy.mil",
        "password": "NewStrongPass456!",
        "role": "recruiter"
    })
    assert new_login.status_code == 200
    assert new_login.json()["user"]["email"] == "grace@navy.mil"


def test_password_reset_flow(app_and_client):
    _, client, _ = app_and_client

    # 1. Register candidate
    client.post("/auth/signup", json={
        "name": "Alan Turing",
        "email": "alan@enigma.org",
        "password": "OriginalPass123!",
        "confirm_password": "OriginalPass123!",
        "role": "candidate"
    })

    # 2. Reset password
    reset_res = client.post("/auth/reset-password", json={
        "email": "alan@enigma.org",
        "new_password": "ResetStrongPass789!",
        "confirm_new_password": "ResetStrongPass789!"
    })
    assert reset_res.status_code == 200

    # 3. Old password fails
    fail_login = client.post("/auth/login", json={
        "email": "alan@enigma.org",
        "password": "OriginalPass123!",
        "role": "candidate"
    })
    assert fail_login.status_code == 401

    # 4. Newly reset password succeeds
    ok_login = client.post("/auth/login", json={
        "email": "alan@enigma.org",
        "password": "ResetStrongPass789!",
        "role": "candidate"
    })
    assert ok_login.status_code == 200
