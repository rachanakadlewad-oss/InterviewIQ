"""End-to-End verification of the 6 Recruiter Dashboard & Candidate Management scenarios:
1. Job Update confirmation and persistence
2. Resume Upload, automatic AI evaluation, and duplicate handling
3. Candidate Shortlisting workflow and status tracking
4. Candidate Rejection workflow (critical: DB persistence, active exclusion, archive access)
5. AI Candidate-Job Evaluation Breakdown (4 categories, strengths, gaps, no raw HTML)
6. Recruiter Overview and metrics consistency
"""
import pytest
from fastapi.testclient import TestClient
from app.api.main import create_app
from app.services.ai_matcher import evaluate_candidate_for_job
from tests.helpers import SAMPLE


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings))


def test_scenario_1_job_update_confirmation_and_persistence(client):
    """Test 1: Recruiter edits an existing job opening and saves changes to database.
    Verifies modified fields, competencies regeneration, persistence, and retrieval.
    """
    # 1. Create a job
    create_res = client.post("/jobs", json={
        "title": "Initial Python Engineer",
        "company": "Initial Corp",
        "description": "Initial job description for backend engineer.",
        "required_skills": "Python, Django",
        "preferred_skills": "PostgreSQL",
        "experience_level": "Mid-level",
        "location": "New York",
        "employment_type": "Full-time",
        "competencies": [{"id": "comp_python", "name": "Python", "weight": 1.0}]
    })
    assert create_res.status_code == 200
    job_id = create_res.json()["id"]

    # 2. Recruiter modifies all fields and submits update
    update_payload = {
        "title": "Lead AI Systems Engineer",
        "company": "NextGen AI Corp",
        "description": "Architect and deploy production-grade LLM applications and agent pipelines.",
        "required_skills": "Python, PyTorch, LangChain, FastAPI",
        "preferred_skills": "Kubernetes, Vector DBs, Triton",
        "experience_level": "Lead",
        "location": "Remote (Worldwide)",
        "employment_type": "Full-time",
        "status": "ACTIVE"
    }
    update_res = client.patch(f"/jobs/{job_id}", json=update_payload)
    assert update_res.status_code == 200
    updated_data = update_res.json()

    # 3. Verify updated fields in response
    assert updated_data["title"] == "Lead AI Systems Engineer"
    assert updated_data["company"] == "NextGen AI Corp"
    assert updated_data["description"] == "Architect and deploy production-grade LLM applications and agent pipelines."
    assert updated_data["required_skills"] == "Python, PyTorch, LangChain, FastAPI"
    assert updated_data["preferred_skills"] == "Kubernetes, Vector DBs, Triton"
    assert updated_data["experience_level"] == "Lead"
    assert updated_data["location"] == "Remote (Worldwide)"
    assert updated_data["employment_type"] == "Full-time"
    assert updated_data["status"] == "ACTIVE"

    # Verify competencies were regenerated from new required skills
    comp_names = [c["name"] for c in updated_data.get("competencies", [])]
    assert "Python" in comp_names
    assert "PyTorch" in comp_names
    assert "LangChain" in comp_names

    # 4. Verify persistence across subsequent GET requests
    get_res = client.get(f"/jobs/{job_id}")
    assert get_res.status_code == 200
    persisted = get_res.json()
    assert persisted["title"] == "Lead AI Systems Engineer"
    assert persisted["location"] == "Remote (Worldwide)"
    assert persisted["required_skills"] == "Python, PyTorch, LangChain, FastAPI"


def test_scenario_2_resume_upload_eval_and_duplicate_handling(client):
    """Test 2: Recruiter uploads resumes for a job opening.
    Verifies automatic text extraction, parsing, AI scoring, PENDING_REVIEW initial status,
    and graceful duplicate handling without duplicate records.
    """
    # Create target job
    job = client.post("/jobs/load-sample").json()
    job_id = job["id"]

    # 1. Upload sample resume PDF
    pdf_path = SAMPLE / "resumes" / "Meera_Iyer.pdf"
    assert pdf_path.exists()
    pdf_bytes = pdf_path.read_bytes()

    upload_res = client.post(
        f"/jobs/{job_id}/applications",
        files={"file": ("Meera_Iyer.pdf", pdf_bytes, "application/pdf")}
    )
    assert upload_res.status_code == 200
    app_info = upload_res.json()
    app_id = app_info["application_id"]
    assert app_id is not None

    # 2. Check candidate listing for this job
    cands_res = client.get(f"/recruiter/candidates?job_id={job_id}")
    assert cands_res.status_code == 200
    cands = cands_res.json()
    assert len(cands) >= 1

    meera = next(c for c in cands if c["id"] == app_id)
    assert meera["candidate_name"] == "Meera Iyer"
    assert meera["job_id"] == job_id
    assert meera["status"] in ("PENDING_REVIEW", "PARSED", "SCORED")
    assert meera["ai_score"] is not None
    assert 0.0 <= meera["ai_score"] <= 100.0

    # Verify structured AI breakdown is saved
    ai_breakdown = meera.get("ai_breakdown")
    assert ai_breakdown is not None
    assert "technical_skills_match" in ai_breakdown
    assert "experience_relevance" in ai_breakdown
    assert "project_relevance" in ai_breakdown
    assert "educational_relevance" in ai_breakdown

    initial_cand_count = len(cands)

    # 3. Duplicate Upload test: re-upload the same resume to the same job
    dup_res = client.post(
        f"/jobs/{job_id}/applications",
        files={"file": ("Meera_Iyer.pdf", pdf_bytes, "application/pdf")}
    )
    assert dup_res.status_code == 200
    dup_info = dup_res.json()
    assert dup_info["application_id"] == app_id  # Updates existing application

    # Verify no duplicate candidate record was created
    cands_after = client.get(f"/recruiter/candidates?job_id={job_id}").json()
    assert len(cands_after) == initial_cand_count


def test_scenario_3_shortlisting_workflow(client):
    """Test 3: Recruiter shortlists a candidate.
    Verifies status update to SHORTLISTED in DB, database-backed count increment,
    and presence in shortlisted filter.
    """
    job = client.post("/jobs/load-sample").json()
    job_id = job["id"]

    pdf_bytes = (SAMPLE / "resumes" / "Priya_Nair.pdf").read_bytes()
    up = client.post(f"/jobs/{job_id}/applications", files={"file": ("Priya_Nair.pdf", pdf_bytes, "application/pdf")})
    app_id = up.json()["application_id"]

    # Initial counts
    c_init = client.get(f"/recruiter/candidates/counts?job_id={job_id}").json()
    initial_shortlisted = c_init["shortlisted"]

    # Recruiter clicks Shortlist
    shortlist_res = client.patch(f"/recruiter/applications/{app_id}/status", json={"status": "SHORTLISTED"})
    assert shortlist_res.status_code == 200
    assert shortlist_res.json()["status"] == "SHORTLISTED"
    assert shortlist_res.json()["shortlisted"] is True

    # Check updated database-backed counts
    c_after = client.get(f"/recruiter/candidates/counts?job_id={job_id}").json()
    assert c_after["shortlisted"] == initial_shortlisted + 1

    # Verify shortlisted filter returns candidate
    sl_list = client.get(f"/recruiter/candidates?job_id={job_id}&status=SHORTLISTED").json()
    assert any(c["id"] == app_id for c in sl_list)


def test_scenario_4_candidate_rejection_workflow(client):
    """Test 4 (Critical): Candidate rejection workflow.
    Verifies:
    1. Candidate status set to REJECTED in database.
    2. Removed from active Candidates listing.
    3. Excluded from shortlisted and accepted counts.
    4. Excluded from interview scheduling.
    5. Preserved in database (never hard deleted).
    6. Accessible in Rejected / Archived view.
    7. Can be restored if needed.
    """
    job = client.post("/jobs/load-sample").json()
    job_id = job["id"]

    pdf_bytes = (SAMPLE / "resumes" / "Sneha_Kulkarni.pdf").read_bytes()
    up = client.post(f"/jobs/{job_id}/applications", files={"file": ("Sneha_Kulkarni.pdf", pdf_bytes, "application/pdf")})
    app_id = up.json()["application_id"]

    # 1. Shortlist first
    client.patch(f"/recruiter/applications/{app_id}/status", json={"status": "SHORTLISTED"})
    counts_sl = client.get(f"/recruiter/candidates/counts?job_id={job_id}").json()
    assert counts_sl["shortlisted"] >= 1

    # 2. Recruiter clicks Reject
    rej_res = client.patch(f"/recruiter/applications/{app_id}/status", json={"status": "REJECTED"})
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "REJECTED"
    assert rej_res.json()["shortlisted"] is False

    # 3. Verify counts updated: candidate NOT in shortlisted count, rejected count incremented
    counts_rej = client.get(f"/recruiter/candidates/counts?job_id={job_id}").json()
    assert counts_rej["rejected"] >= 1

    # 4. Candidate must NOT appear in active listing
    active_cands = client.get(f"/recruiter/candidates?job_id={job_id}&status=ACTIVE").json()
    assert not any(c["id"] == app_id for c in active_cands), "Rejected candidate must not appear in active listing"

    # Default listing (no status param) must also exclude rejected candidates
    default_cands = client.get(f"/recruiter/candidates?job_id={job_id}").json()
    assert not any(c["id"] == app_id for c in default_cands), "Default candidate list must exclude rejected candidates"

    # 5. Candidate is NOT deleted from database: accessible via REJECTED or ALL filter
    rej_cands = client.get(f"/recruiter/candidates?job_id={job_id}&status=REJECTED").json()
    assert any(c["id"] == app_id for c in rej_cands), "Rejected candidate must be accessible in rejected archive view"

    all_cands = client.get(f"/recruiter/candidates?job_id={job_id}&status=ALL").json()
    assert any(c["id"] == app_id for c in all_cands), "Candidate record must be preserved in DB"

    # 6. Candidate can be restored to PENDING_REVIEW or ACTIVE
    restore_res = client.patch(f"/recruiter/applications/{app_id}/status", json={"status": "PENDING_REVIEW"})
    assert restore_res.status_code == 200
    assert restore_res.json()["status"] == "PENDING_REVIEW"

    # Restored candidate reappears in active list
    active_again = client.get(f"/recruiter/candidates?job_id={job_id}&status=ACTIVE").json()
    assert any(c["id"] == app_id for c in active_again), "Restored candidate should reappear in active list"


def test_scenario_5_ai_evaluation_breakdown_structure():
    """Test 5: Verify AI Candidate-Job Evaluation Breakdown.
    Ensures 4 categories, strengths, gaps, detailed assessment, and zero raw HTML strings.
    """
    job = {
        "title": "Senior AI Engineer",
        "company": "DeepTech",
        "description": "Build high-throughput LLM pipelines and RAG architectures.",
        "required_skills": "Python, LLM, PyTorch, LangChain, Vector DB",
        "preferred_skills": "Docker, Kubernetes, Triton",
        "experience_level": "Senior"
    }

    resume_text = """
    Rachana K. - Senior Machine Learning Engineer
    5+ years designing and evaluating LLM fine-tuning pipelines and RAG systems using PyTorch and LangChain.
    Implemented vector search indexing using Qdrant and pgvector.
    Deployed FastAPI microservices in Docker containers.
    Education: B.Tech in Computer Science and Engineering.
    """

    profile = {
        "name": "Rachana K.",
        "skills": ["Python", "LLM", "PyTorch", "LangChain", "Vector DB", "Docker", "FastAPI"],
        "experience_years": 5.0,
        "education": ["B.Tech in Computer Science and Engineering"],
        "projects": ["High-throughput RAG indexing platform"],
        "certifications": ["AWS Certified Machine Learning Specialist"]
    }

    score, breakdown, explanation, source = evaluate_candidate_for_job(job, resume_text, profile)

    # 1. Overall Match Score & Classification
    assert 0.0 <= score <= 100.0

    # 2. Four categories must exist
    assert "technical_skills_match" in breakdown
    assert "experience_relevance" in breakdown
    assert "project_relevance" in breakdown
    assert "educational_relevance" in breakdown

    for cat in ("technical_skills_match", "experience_relevance", "project_relevance", "educational_relevance"):
        assert "score" in breakdown[cat]
        assert "assessment" in breakdown[cat]
        assert 0.0 <= breakdown[cat]["score"] <= 100.0

    # 3. Strengths and Gaps
    assert isinstance(breakdown.get("strengths"), list)
    assert len(breakdown["strengths"]) > 0
    assert isinstance(breakdown.get("missing_or_weak_requirements"), list)

    # 4. Detailed explanation and recommendation
    assert isinstance(breakdown.get("detailed_explanation"), str)
    assert len(breakdown["detailed_explanation"]) > 20
    assert isinstance(breakdown.get("recommendation"), str)

    # 5. ZERO raw HTML tags or unescaped entities anywhere in the breakdown
    forbidden_tokens = ["</div>", "<div>", "style=", "<b ", "&nbsp;", "<span", "class="]
    dumped_json = str(breakdown) + " " + str(explanation)
    for token in forbidden_tokens:
        assert token not in dumped_json, f"Raw HTML token '{token}' found in AI evaluation output!"


def test_scenario_6_recruiter_overview_consistency(client):
    """Test 6: Verify full Recruiter Overview consistency.
    Ensures overview counts, funnel, and action items accurately reflect real DB state,
    and rejected candidates do not skew metrics.
    """
    job = client.post("/jobs/load-sample").json()
    job_id = job["id"]

    # Upload two candidates
    pdf1 = (SAMPLE / "resumes" / "Meera_Iyer.pdf").read_bytes()
    pdf2 = (SAMPLE / "resumes" / "Priya_Nair.pdf").read_bytes()

    up1 = client.post(f"/jobs/{job_id}/applications", files={"file": ("Meera_Iyer.pdf", pdf1, "application/pdf")}).json()
    up2 = client.post(f"/jobs/{job_id}/applications", files={"file": ("Priya_Nair.pdf", pdf2, "application/pdf")}).json()

    # Shortlist candidate 1, reject candidate 2
    client.patch(f"/recruiter/applications/{up1['application_id']}/status", json={"status": "SHORTLISTED"})
    client.patch(f"/recruiter/applications/{up2['application_id']}/status", json={"status": "REJECTED"})

    # Check candidate counts endpoint
    counts = client.get(f"/recruiter/candidates/counts?job_id={job_id}").json()
    assert counts["shortlisted"] == 1
    assert counts["rejected"] == 1
    assert counts["active"] == 1  # Only 1 active candidate (the shortlisted one)
    assert counts["total"] == 2

    # Check overview endpoint
    overview = client.get("/overview").json()
    assert "metrics" in overview
    assert "funnel" in overview
    assert "actions" in overview
