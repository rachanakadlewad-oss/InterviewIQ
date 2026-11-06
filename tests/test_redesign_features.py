"""Comprehensive tests for recruitment platform redesign, database models,
authentication session persistence, recruiter dashboard, candidate tracking,
and AI-powered candidate-job matching."""
import json
import pytest
from app import db as dbm
from app.config import Settings, set_settings
from app.db import Application, Job, User, CandidateProfile, new_session
from app.services.ai_matcher import evaluate_candidate_for_job
from app.services import auth as auth_svc


@pytest.fixture
def clean_db(tmp_path):
    s = Settings(
        data_dir=str(tmp_path / "rt"),
        database_url=f"sqlite:///{tmp_path / 'test_app.db'}",
        agent_retry_backoff=0.0,
        llm_provider="demo"
    )
    set_settings(s)
    dbm.init_db(s.database_url)
    session = new_session()
    yield session, s
    session.close()


def test_database_schema_and_models(clean_db):
    """Verify that all required models and fields exist with proper relationships."""
    db, s = clean_db

    # 1. Create Recruiter User
    rec = User(
        name="Rachana Kadlewad",
        email="rachana@example.com",
        password_hash=auth_svc.hash_password("Password123"),
        role="recruiter",
        status="active",
        profile_info=json.dumps({"department": "Engineering"})
    )
    db.add(rec)
    db.commit()
    assert rec.id is not None
    assert rec.role == "recruiter"

    # 2. Create Candidate User
    cand = User(
        name="Alex Smith",
        email="alex@example.com",
        password_hash=auth_svc.hash_password("Password123"),
        role="candidate",
        status="active"
    )
    db.add(cand)
    db.commit()
    assert cand.id is not None
    assert cand.role == "candidate"

    # 3. Create Candidate Profile
    prof = CandidateProfile(
        user_id=cand.id,
        skills=json.dumps(["Python", "FastAPI", "SQL"]),
        experience=json.dumps(["Software Engineer at Acme (3 yrs)"]),
        education=json.dumps(["B.S. in Computer Science"])
    )
    db.add(prof)
    db.commit()
    assert prof.id is not None

    # 4. Create Job Opening with meaningful recruiter fields
    job = Job(
        recruiter_id=rec.id,
        title="Senior Python Backend Developer",
        company="TechCorp Solutions",
        description="Build scalable microservices with Python and FastAPI.",
        required_skills="Python, FastAPI, SQL, Docker",
        preferred_skills="AWS, Kubernetes",
        experience_level="Senior",
        location="Remote",
        employment_type="Full-time",
        status="ACTIVE",
        competencies_json="[]"
    )
    db.add(job)
    db.commit()
    assert job.id is not None
    assert job.recruiter_id == rec.id
    assert job.status == "ACTIVE"

    # 5. Create Application linked to Job and Candidate
    app = Application(
        job_id=job.id,
        user_id=cand.id,
        candidate_name="Alex Smith",
        email="alex@example.com",
        status="PENDING",
        resume_filename="alex_resume.pdf",
        resume_text="Experienced Python Developer with 5 years building REST APIs with FastAPI.",
        profile_json=json.dumps({"skills": ["Python", "FastAPI"], "experience_years": 5.0}),
        ai_score=85.0,
        ai_reasoning=json.dumps({"recommendation": "Strong match for recruiter review"}),
        access_token="tok_test_123"
    )
    db.add(app)
    db.commit()
    assert app.id is not None
    assert app.job_id == job.id
    assert app.user_id == cand.id


def test_ai_candidate_matching_engine():
    """Verify semantic LLM evaluation structure: score 0-100, technical match, experience, strengths, gaps, recommendation."""
    job = {
        "title": "Backend Python Engineer",
        "company": "TechCorp",
        "description": "Develop and maintain high performance backend APIs.",
        "required_skills": "Python, FastAPI, PostgreSQL, REST APIs",
        "preferred_skills": "Docker, Kubernetes, Redis",
        "experience_level": "Mid-level"
    }

    resume_text = """
    Jane Doe - Senior Software Engineer
    5 years of experience building production web applications and REST APIs in Python and FastAPI.
    Redesigned PostgreSQL relational database schemas, reducing query latency by 35%.
    Deployed containerized services with Docker to cloud environments.
    """

    profile = {
        "name": "Jane Doe",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Docker", "REST APIs"],
        "experience_years": 5.0,
        "experience": ["Senior Software Engineer at SaaS Corp (3 years)"],
        "projects": ["High throughput payment processing API"]
    }

    score, eval_dict, explanation, source = evaluate_candidate_for_job(job, resume_text, profile)

    assert 0.0 <= score <= 100.0
    assert "technical_skills_match" in eval_dict
    assert "score" in eval_dict["technical_skills_match"]
    assert "assessment" in eval_dict["technical_skills_match"]

    assert "experience_relevance" in eval_dict
    assert "score" in eval_dict["experience_relevance"]
    assert "assessment" in eval_dict["experience_relevance"]

    assert "project_relevance" in eval_dict
    assert "score" in eval_dict["project_relevance"]

    assert isinstance(eval_dict["strengths"], list)
    assert len(eval_dict["strengths"]) > 0

    assert isinstance(eval_dict["missing_or_weak_requirements"], list)
    assert "detailed_explanation" in eval_dict
    assert "recommendation" in eval_dict
    assert "Strong match" in eval_dict["recommendation"] or "interview" in eval_dict["recommendation"].lower()


def test_recruiter_shortlist_and_status_actions(clean_db):
    """Verify that recruiter shortlisting, rejection, and pending status persist and sync accurately."""
    db, s = clean_db

    rec = User(name="Recruiter One", email="rec@test.com", password_hash="hash", role="recruiter")
    db.add(rec); db.flush()

    job = Job(recruiter_id=rec.id, title="QA Lead", status="ACTIVE", competencies_json="[]")
    db.add(job); db.flush()

    app1 = Application(job_id=job.id, candidate_name="Candidate A", email="a@test.com", status="PENDING", access_token="tok_a")
    app2 = Application(job_id=job.id, candidate_name="Candidate B", email="b@test.com", status="PENDING", access_token="tok_b")
    db.add_all([app1, app2])
    db.commit()

    # Shortlist Candidate A
    app1.status = "SHORTLISTED"
    app1.shortlisted = True
    db.commit()

    # Verify Candidate A is shortlisted
    reloaded_a = db.get(Application, app1.id)
    assert reloaded_a.status == "SHORTLISTED"
    assert reloaded_a.shortlisted is True

    # Reject Candidate B
    app2.status = "REJECTED"
    app2.shortlisted = False
    db.commit()

    reloaded_b = db.get(Application, app2.id)
    assert reloaded_b.status == "REJECTED"
    assert reloaded_b.shortlisted is False

    # Move Candidate B back to pending
    app2.status = "PENDING"
    db.commit()
    reloaded_b2 = db.get(Application, app2.id)
    assert reloaded_b2.status == "PENDING"


def test_job_activation_and_deactivation(clean_db):
    """Verify job activation, deactivation, and persistence."""
    db, s = clean_db

    job = Job(title="DevOps Specialist", status="ACTIVE", competencies_json="[]")
    db.add(job); db.commit()
    assert job.status == "ACTIVE"

    # Deactivate job
    job.status = "INACTIVE"
    db.commit()
    reloaded = db.get(Job, job.id)
    assert reloaded.status == "INACTIVE"

    # Reactivate job
    job.status = "ACTIVE"
    db.commit()
    reloaded2 = db.get(Job, job.id)
    assert reloaded2.status == "ACTIVE"
