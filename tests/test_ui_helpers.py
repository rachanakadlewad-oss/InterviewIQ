from frontend.iqui import helpers as h


def test_every_backend_status_has_a_label():
    from app.services.state_machine import TRANSITIONS
    for s in TRANSITIONS:
        label, tone = h.status_label(s)
        assert label and tone in ("neutral", "info", "success", "warning", "error"), s


def test_unknown_status_falls_back_gracefully():
    assert h.status_label("SOMETHING_NEW")[0] == "Something New"


def test_score_tone_thresholds():
    assert h.score_tone(None) == "neutral"
    assert h.score_tone(75) == "success" and h.score_tone(55) == "warning" and h.score_tone(20) == "error"
    assert h.score_tone(8, out_of=10) == "success"


def test_source_label_distinguishes_demo_from_llm():
    assert h.source_label("demo_rules")[0] == "Demo rules" and h.source_label("llm")[0] == "LLM"
    assert h.source_label("")[0] == "Not scored"


def test_formatting():
    assert h.fmt_dt(None) == "-" and h.fmt_dt("garbage") == "garbage"
    assert h.fmt_dt("2026-10-12T10:00:00") == "Mon 12 Oct, 10:00"
    assert h.fmt_score(None) == "-" and h.fmt_score(7.25) == "7.2" or h.fmt_score(7.25) == "7.3"


def test_candidate_steps_progress_and_hide_internal_stages():
    labels = [l for l, _ in h.candidate_steps("SCORED")]
    assert labels == h.CAND_STEPS and "Scored" not in labels
    assert [s for _, s in h.candidate_steps("SCHEDULED")] == ["done", "done", "current", "todo", "todo"]
    assert [s for _, s in h.candidate_steps("INTERVIEW_IN_PROGRESS")] == ["done", "done", "done", "current", "todo"]
    assert all(s == "done" for _, s in h.candidate_steps("ASSESSED"))


def test_candidate_messages_never_leak_scores_or_decision():
    from app.services.state_machine import TRANSITIONS
    for s in TRANSITIONS:
        head, body, tone = h.candidate_message(s)
        text = (head + body).lower()
        assert head and body and not any(w in text for w in ("score", "rank", "advance", "rejected "))


def test_competency_form_validation_collects_all_problems():
    rows = [{"name": "Python", "weight": 1.5, "keywords": "python, fastapi", "question": "Tell me?", "rubric_strong": "Great"},
            {"name": "python", "weight": 1}, {"name": "", "description": "orphan"}, {"name": "SQL", "weight": 0},
            {"name": "Go", "weight": "abc"}, {}]
    clean, errors = h.competency_rows_valid(rows)
    assert [c["id"] for c in clean] == ["python"] and clean[0]["rubric"] == {"5": "Great"} and clean[0]["keywords"] == ["python", "fastapi"]
    assert len(errors) == 4 and any("twice" in e for e in errors) and any("name is required" in e for e in errors)


def test_competency_form_requires_one_and_builds_valid_unique_ids():
    assert h.competency_rows_valid([{}, {"name": ""}])[1] == ["Add at least one competency."]
    clean, errors = h.competency_rows_valid([{"name": "Data Modeling!"}, {"name": "Data modeling?"}, {"name": "A b"}, {"name": "A-b"}])
    ids = [c["id"] for c in clean]
    assert not errors and len(ids) == len(set(ids)) == 4          # distinct names always get distinct ids
    assert ids[:2] == ["data_modeling", "data_modeling_2"]


def test_form_output_passes_backend_schema():
    from app.schemas import JobIn
    clean, errors = h.competency_rows_valid([{"name": "Testing", "weight": 2}, {"name": "APIs"}])
    assert not errors
    JobIn.model_validate({"title": "Engineer", "description": "d", "competencies": clean})


def test_analyze_competency_details_strong_evidence():
    comp = {
        "id": "system_design",
        "name": "System Design",
        "weight": 2.0,
        "description": "Architecting resilient distributed systems",
        "keywords": ["distributed systems", "microservices", "kubernetes", "kafka"],
        "rubric": {"1": "No experience", "3": "Builds basic APIs", "5": "Designs multi-region systems"},
        "questions": ["How do you ensure high availability in distributed architectures?"]
    }
    score_data = {
        "competency_id": "system_design",
        "score": 8.0,
        "evidence_level": "DIRECT",
        "justification": "Direct Evidence: Designed distributed systems handling 50k requests per second using microservices and kafka.",
        "evidence": ["Architected distributed systems handling 50k requests per second across 12 microservices."]
    }
    info = h.analyze_competency_details(comp, score_data)
    assert info["name"] == "System Design"
    assert info["score"] == 8.0
    assert info["weight"] == 2.0
    assert info["level_label"] == "Strong evidence"
    assert info["level_tone"] == "success"
    assert len(info["evidence"]) == 1
    assert "Architected distributed systems" in info["evidence"][0]
    assert any("microservices" in p or "distributed systems" in p for p in info["demonstrated_points"])
    assert any("50k requests" in p for p in info["demonstrated_points"])
    assert any("Designs multi-region systems" in p for p in info["missing_points"])
    assert len(info["suggested_questions"]) == 2
    assert "high availability" in info["suggested_questions"][0]["question"]


def test_analyze_competency_details_partial_evidence():
    comp = {
        "id": "system_design",
        "name": "System Design",
        "weight": 1.5,
        "description": "Architecting resilient distributed systems",
        "keywords": ["kubernetes", "kafka", "redis", "load balancer"],
        "rubric": {"3": "Working standard", "5": "Advanced architecture"},
        "questions": []
    }
    score_data = {
        "competency_id": "system_design",
        "score": 5.2,
        "evidence_level": "PARTIAL",
        "justification": "Partial Evidence: Candidate mentioned kubernetes in coursework but lacked production scale.",
        "evidence": ["Completed academic project deploying containers with Kubernetes."]
    }
    info = h.analyze_competency_details(comp, score_data)
    assert info["level_label"] == "Partial evidence"
    assert info["level_tone"] == "warning"
    assert info["score"] == 5.2
    assert any("kubernetes" in p for p in info["demonstrated_points"])
    assert any("Unrepresented production tools" in p for p in info["missing_points"])
    assert any("No quantified scale" in p for p in info["missing_points"])
    assert any("Production Depth Probe" in q["tag"] for q in info["suggested_questions"])


def test_analyze_competency_details_missing_evidence():
    comp = {
        "id": "cloud_infra",
        "name": "Cloud Infrastructure",
        "weight": 1.0,
        "description": "Managing AWS and Terraform infrastructure",
        "keywords": ["aws", "terraform", "ci/cd"],
        "rubric": {"3": "Provisions cloud resources", "5": "Zero-downtime infrastructure"},
        "questions": ["Describe your cloud architecture workflow."]
    }
    info = h.analyze_competency_details(comp, None)
    assert info["score"] == 0.0
    assert info["level_label"] == "Missing evidence"
    assert info["level_tone"] == "neutral"
    assert info["evidence"] == []
    assert "No relevant evidence was identified" in info["relevance_explanation"]
    assert "aws" in info["relevance_explanation"]
    assert any("Missing core domain technologies" in p for p in info["missing_points"])
    assert any("Gap Exploration Probe" in q["tag"] for q in info["suggested_questions"])
