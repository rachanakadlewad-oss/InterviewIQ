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
