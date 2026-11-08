import json

import pytest

from app.agents.assessment import AssessmentAgent
from app.agents.base import AgentError
from app.agents.interviewer import InterviewerAgent
from app.agents.recruitment import RecruitmentAgent
from app.llm.client import DemoLLM, LLMError
from app.services import interview_engine as eng
from app.textutil import contains_quote
from tests.helpers import SAMPLE, FakeLLM


def resume_text(name):
    from app.services.resume_parser import parse_resume
    return parse_resume(name, (SAMPLE / "resumes" / name).read_bytes())[0]


def good_scores(job, text, evidence):
    return json.dumps({"scores": [{"competency_id": c.id, "score": 5 if evidence else 0,
                                   "evidence": [evidence] if evidence else [], "justification": "ok fine"}
                                  for c in job.competencies], "summary": "s"})


# ---------------- recruitment agent
def test_demo_resume_scoring_has_verbatim_evidence_and_all_competencies(settings, job_in):
    text = resume_text("Aarav_Mehta.docx")
    res = RecruitmentAgent(DemoLLM(), settings).score_resume(job_in, text)
    assert res.source == "demo_rules"
    assert {s.competency_id for s in res.output.scores} == {c.id for c in job_in.competencies}
    for s in res.output.scores:
        assert all(contains_quote(text, e) for e in s.evidence)
        if s.score > 0:
            assert s.evidence


def test_strong_resume_outscores_weak_resume(settings, job_in):
    from app.services.scoring import resume_total
    ag = RecruitmentAgent(DemoLLM(), settings)
    def total(name):
        r = ag.score_resume(job_in, resume_text(name)).output
        return resume_total(job_in, {s.competency_id: s.score for s in r.scores})
    assert total("Aarav_Mehta.docx") > total("Rohan_Gupta.docx") > total("Karan_Shah.docx")


def test_scoring_distinguishes_direct_partial_missing_evidence(settings, job_in):
    ag = RecruitmentAgent(DemoLLM(), settings)
    # Aarav: strong direct technical evidence
    aarav_scores = {s.competency_id: s for s in ag.score_resume(job_in, resume_text("Aarav_Mehta.docx")).output.scores}
    assert aarav_scores["python"].evidence_level == "DIRECT"
    assert aarav_scores["databases"].evidence_level == "DIRECT"
    assert aarav_scores["leadership"].evidence_level == "MISSING"
    assert aarav_scores["leadership"].score == 0.0
    assert aarav_scores["leadership"].evidence == []

    # Karan: junior/intern with partial evidence
    karan_scores = {s.competency_id: s for s in ag.score_resume(job_in, resume_text("Karan_Shah.docx")).output.scores}
    assert karan_scores["python"].evidence_level == "PARTIAL"
    assert karan_scores["testing"].evidence_level == "PARTIAL"
    assert karan_scores["cloud_devops"].evidence_level == "MISSING"
    assert karan_scores["cloud_devops"].score == 0.0


def test_scores_are_realistic_and_no_casual_ten_out_of_ten(settings, job_in):
    ag = RecruitmentAgent(DemoLLM(), settings)
    r = ag.score_resume(job_in, resume_text("Aarav_Mehta.docx")).output
    # No competency should be awarded 10.0 simply for matching keywords
    for s in r.scores:
        assert s.score < 10.0, f"Score for {s.competency_id} should not be 10.0"
        assert s.justification != "", "Justification must not be empty"
        # Justification must mention evidence level
        assert any(lvl in s.justification for lvl in ["Direct Evidence", "Partial Evidence", "Missing Evidence"])

    # Weak resume (Karan) must have low realistic scores for partial competencies
    karan_out = ag.score_resume(job_in, resume_text("Karan_Shah.docx")).output
    for s in karan_out.scores:
        if s.evidence_level == "PARTIAL":
            assert s.score <= 4.5, f"Partial competency {s.competency_id} scored too high: {s.score}"


def test_llm_mode_retries_invalid_json_then_succeeds(settings, job_in):
    text = resume_text("Aarav_Mehta.docx")
    ev = "Wrote pytest unit tests and integration tests reaching 92% coverage; enforced in CI with GitHub Actions."
    llm = FakeLLM(["this is not json at all", good_scores(job_in, text, ev)])
    res = RecruitmentAgent(llm, settings).score_resume(job_in, text)
    assert res.source == "llm" and res.attempts == 2 and llm.calls == 2


def test_llm_mode_rejects_fabricated_evidence(settings, job_in):
    text = resume_text("Karan_Shah.docx")
    llm = FakeLLM([good_scores(job_in, text, "Led a 50 person team at Google")])
    with pytest.raises(AgentError):
        RecruitmentAgent(llm, settings).score_resume(job_in, text)
    assert llm.calls == settings.agent_max_retries + 1          # bounded retries


def test_llm_mode_rejects_missing_competency(settings, job_in):
    text = resume_text("Aarav_Mehta.docx")
    bad = json.dumps({"scores": [{"competency_id": "python", "score": 0, "evidence": [], "justification": "none"}]})
    with pytest.raises(AgentError):
        RecruitmentAgent(FakeLLM([bad]), settings).score_resume(job_in, text)


def test_service_failure_is_bounded_and_reported(settings, job_in):
    llm = FakeLLM([LLMError("timeout")])
    with pytest.raises(AgentError) as e:
        RecruitmentAgent(llm, settings).score_resume(job_in, resume_text("Aarav_Mehta.docx"))
    assert "service error" in str(e.value) and llm.calls == settings.agent_max_retries + 1


def test_json_inside_markdown_fence_is_accepted(settings, job_in):
    text = resume_text("Karan_Shah.docx")
    fenced = "```json\n" + good_scores(job_in, text, "") + "\n```"
    assert RecruitmentAgent(FakeLLM([fenced]), settings).score_resume(job_in, text).source == "llm"


# ---------------- interviewer agent
def make_state(job_in, settings):
    scores = {c.id: 5.0 for c in job_in.competencies}
    st, _ = eng.new_state(job_in, scores, settings)
    return st


def decision_json(trigger, decision="NARROW_FOLLOW_UP", question="Could you say more about that part?", target=None):
    d = {"trigger_phrase": trigger, "reasoning": "The answer was vague so clarify.", "decision": decision, "question": question}
    if target:
        d["target_competency"] = target
    return json.dumps(d)


def test_interviewer_demo_pivots_on_mentoring(settings, job_in):
    st = make_state(job_in, settings)
    eng.record_answer(st, "I optimised the schema and I also mentored two juniors while doing it, cutting latency by 60 percent.")
    ctx = eng.decision_context(job_in, st, settings)
    d = InterviewerAgent(DemoLLM(), settings).decide(job_in, ctx).output
    assert d.decision.value == "BROAD_PIVOT"
    assert "mentored" in d.trigger_phrase and d.question


def test_interviewer_llm_trigger_must_be_quoted_from_answer(settings, job_in):
    st = make_state(job_in, settings)
    eng.record_answer(st, "I built a cache layer for our API.")
    ctx = eng.decision_context(job_in, st, settings)
    llm = FakeLLM([decision_json("something the candidate never said")])
    with pytest.raises(AgentError):
        InterviewerAgent(llm, settings).decide(job_in, ctx)
    ok = FakeLLM([decision_json("built a cache layer")])
    assert InterviewerAgent(ok, settings).decide(job_in, ctx).source == "llm"


def test_interviewer_llm_cannot_repeat_question(settings, job_in):
    st = make_state(job_in, settings)
    eng.record_answer(st, "I built a cache layer for our API.")
    ctx = eng.decision_context(job_in, st, settings)
    llm = FakeLLM([decision_json("built a cache layer", question=st.pending_question)])
    with pytest.raises(AgentError):
        InterviewerAgent(llm, settings).decide(job_in, ctx)


def test_interviewer_llm_disallowed_decision_rejected(settings, job_in):
    st = make_state(job_in, settings)
    eng.record_answer(st, "I built a cache layer for our API.")
    ctx = eng.decision_context(job_in, st, settings)
    assert "CONCLUDE" not in ctx["allowed_decisions"]
    llm = FakeLLM([json.dumps({"trigger_phrase": "built a cache layer", "reasoning": "enough", "decision": "CONCLUDE"})])
    with pytest.raises(AgentError):
        InterviewerAgent(llm, settings).decide(job_in, ctx)


# ---------------- assessment agent
def assess_ctx():
    return {"job_title": "J", "resume_summary": {}, "trace_summary": {},
            "competencies": [{"id": "python", "name": "Python", "weight": 1.5, "rubric": {"5": "great"}, "keywords": ["python"],
                              "answers": ["I built a FastAPI service with pytest tests and 90 percent coverage."]}]}


def assess_json(evidence, summary="You gave a strong, concrete example."):
    return json.dumps({"competencies": [{"competency_id": "python", "score": 7, "evidence": [evidence], "rationale": "solid example"}],
                       "recruiter_summary": "Good python.", "recommendation_rationale": "Evidence supports advancing.",
                       "strengths": ["python"], "weaknesses": [],
                       "candidate_feedback": {"summary": summary, "strengths": ["clear examples"], "weaknesses": [], "improvement_areas": ["more metrics"]}})


def test_assessment_demo_mode_valid(settings):
    r = AssessmentAgent(DemoLLM(), settings).assess(assess_ctx())
    assert r.source == "demo_rules" and r.output.competencies[0].competency_id == "python"


def test_assessment_rejects_fabricated_evidence(settings):
    with pytest.raises(AgentError):
        AssessmentAgent(FakeLLM([assess_json("I rewrote the Linux kernel")]), settings).assess(assess_ctx())


def test_assessment_candidate_feedback_cannot_leak_scores(settings):
    ev = "I built a FastAPI service with pytest tests"
    with pytest.raises(AgentError):
        AssessmentAgent(FakeLLM([assess_json(ev, summary="You scored 7/10 overall.")]), settings).assess(assess_ctx())
    ok = AssessmentAgent(FakeLLM([assess_json(ev)]), settings).assess(assess_ctx())
    assert ok.source == "llm"


def test_demo_scoring_empty_and_dismissive_answers_score_zero():
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services"}
    }
    # Empty answers
    score_empty, wc_empty, hits_empty, _, _ = _score_answers([], comp)
    assert score_empty == 0.0
    assert hits_empty == []

    score_spaces, _, _, _, _ = _score_answers(["   ", ""], comp)
    assert score_spaces == 0.0

    # Dismissive answers
    score_dismissive, _, _, _, _ = _score_answers(["No, I don't know."], comp)
    assert score_dismissive == 0.0


def test_demo_scoring_irrelevant_answer_scores_zero():
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services"}
    }
    ans = ["I enjoy baking sourdough bread and running half marathons outdoors on weekends."]
    score, wc, hits, digits, verbs = _score_answers(ans, comp)
    assert score == 0.0
    assert hits == []


def test_demo_scoring_vague_introductory_answer_scores_partial():
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services"}
    }
    ans = ["I learned Python in a college project and wrote simple basic scripts for coursework."]
    score, wc, hits, digits, verbs = _score_answers(ans, comp)
    assert 2.5 <= score <= 4.5
    assert "python" in hits


def test_demo_scoring_relevant_without_metrics_scores_strong():
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services with clean architecture"}
    }
    # Notice: exactly zero numbers/digits in this answer
    ans = [
        "I designed and implemented our REST backend service in FastAPI, "
        "writing pytest tests and structuring the codebase into distinct service layers "
        "to ensure clean separation of concerns."
    ]
    assert not any(ch.isdigit() for ch in ans[0])
    score, wc, hits, digits, verbs = _score_answers(ans, comp)
    assert score >= 7.0
    assert digits == 0
    assert verbs >= 2


def test_demo_scoring_detailed_with_reasoning_and_metrics_scores_excellent():
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services with high throughput"}
    }
    ans = [
        "I re-architected our data pipeline in Python using asyncio because synchronous I/O "
        "was blocking request threads under peak load. I profiled the system, migrated the queries, "
        "and reduced latency by 45% across 10 microservices."
    ]
    score, wc, hits, digits, verbs = _score_answers(ans, comp)
    assert score >= 8.5
    assert digits >= 1
    assert verbs >= 2


def test_demo_assessment_end_to_end_agent_evidence_tiers(settings):
    comp_py = {
        "id": "python",
        "name": "Python",
        "weight": 1.0,
        "keywords": ["python", "fastapi", "pytest"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Advanced architecture"},
        "answers": ["I designed and built our FastAPI service, writing pytest tests to ensure reliability."]
    }
    comp_db = {
        "id": "databases",
        "name": "Databases",
        "weight": 1.0,
        "keywords": ["postgresql", "sql", "redis"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Optimized queries"},
        "answers": ["I haven't used PostgreSQL or databases much; I only read about them briefly."]
    }
    ctx = {
        "job_title": "Backend Engineer",
        "resume_summary": {},
        "trace_summary": {},
        "competencies": [comp_py, comp_db]
    }
    res = AssessmentAgent(DemoLLM(), settings).assess(ctx)
    assert res.source == "demo_rules"
    scores = {c.competency_id: c.score for c in res.output.competencies}
    # Python should be strong (>= 7.0)
    assert scores["python"] >= 7.0
    # Databases should be partial (<= 4.5)
    assert scores["databases"] <= 4.5
    # Python in strengths, Databases in weaknesses
    assert any("Python" in s for s in res.output.strengths)
    assert any("Databases" in w for w in res.output.weaknesses)
    # Verbatim evidence check
    for c in res.output.competencies:
        if c.score > 2.0:
            assert len(c.evidence) > 0
def test_regression_vulnerability_1_generic_words_do_not_establish_relevance():
    """Regression Test 1: Generic English words from descriptions/rubrics must not establish competency relevance."""
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services with maintainable structure",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {
            "1": "No experience with basic scripts",
            "3": "Builds working services and modules with some structure and standard practices",
            "5": "Production services with clean architecture and maintainable code"
        }
    }
    # Answers contain generic words from description and rubric: clean, write, notes, team, habits, workflow
    ans_1 = ["I keep a clean desk, write daily notes, and work with our team on various tasks."]
    score_1, wc_1, hits_1, digits_1, verbs_1 = _score_answers(ans_1, comp)
    assert score_1 == 0.0, f"Expected 0.0 but got {score_1}"
    assert hits_1 == [], f"Expected empty hits but got {hits_1}"

    ans_2 = ["I maintain clean habits and write daily reflections to improve my personal workflow."]
    score_2, wc_2, hits_2, _, _ = _score_answers(ans_2, comp)
    assert score_2 == 0.0, f"Expected 0.0 but got {score_2}"
    assert hits_2 == []


def test_regression_vulnerability_2_irrelevant_answers_with_action_verbs_do_not_score_strong():
    """Regression Test 2: Irrelevant answers with action verbs must not receive strong scores."""
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services"}
    }
    # Irrelevant carpentry answer with multiple action verbs: designed, built, implemented, improved, fixed
    ans_carpentry = [
        "I designed, built, and implemented a wooden dining table in my garage. "
        "I improved the varnish, cut the lumber, and fixed the wobbly legs."
    ]
    score_c, wc_c, hits_c, digits_c, verbs_c = _score_answers(ans_carpentry, comp)
    assert verbs_c >= 3, f"Expected action verbs to be extracted, got {verbs_c}"
    assert score_c == 0.0, f"Irrelevant answer with action verbs must score 0.0, got {score_c}"
    assert hits_c == []

    # Irrelevant answer with action verbs AND metrics (kitchen pantry: built, reduced, 30%)
    ans_metrics = ["I organized our kitchen pantry, built three spice racks, and reduced cooking prep time by 30%."]
    score_m, _, hits_m, digits_m, verbs_m = _score_answers(ans_metrics, comp)
    assert score_m == 0.0, f"Irrelevant answer with metrics must score 0.0, got {score_m}"
    assert hits_m == []


def test_regression_vulnerability_3_buzzwords_and_metrics_without_explanation_do_not_score_excellent():
    """Regression Test 3: Buzzwords and metrics without meaningful explanation must not receive excellent scores."""
    from app.agents.demo_logic import _score_answers
    comp = {
        "id": "python",
        "name": "Python Programming",
        "description": "Writing idiomatic, clean Python backend services",
        "keywords": ["python", "fastapi", "pytest", "asyncio"],
        "rubric": {"1": "No experience", "3": "Basic scripts", "5": "Production services with high throughput"}
    }
    # Comma-separated buzzword list + isolated metrics claims without explanation of problem or mechanism
    ans_buzzwords = [
        "Python, FastAPI, Redis, Docker, microservices. "
        "Built and deployed 10 microservices, 99.9% uptime, 100k rps, reduced latency by 45%."
    ]
    score, wc, hits, digits, verbs = _score_answers(ans_buzzwords, comp)
    assert digits >= 2, "Expected multiple metrics"
    assert verbs >= 2, "Expected action verbs"
    assert len(hits) >= 2, "Expected keywords matched"
    # MUST NOT receive an excellent score (>= 8.5)
    assert score < 8.5, f"Buzzwords and metrics without meaningful explanation scored {score}, expected < 8.5"
    assert score <= 4.5, f"Should be in Partial tier (<= 4.5), got {score}"


def test_regression_vulnerability_4_relevant_technical_explanations_score_well_without_keywords_numbers_first_person():
    """Regression Test 4: Relevant technical explanations should still score well without predefined keywords, numbers or first-person phrasing where their meaning is recognizable."""
    import re
    from app.agents.demo_logic import _score_answers

    # Scenario A: Database competency
    comp_db = {
        "id": "databases",
        "name": "Databases and SQL",
        "description": "Models data, writes efficient queries, understands indexing and transactions.",
        "keywords": ["postgresql", "sql", "redis"],
        "rubric": {"1": "Basic queries", "3": "Indexes and schemas", "5": "Optimizes execution plans"}
    }
    ans_db = [
        "Query execution plans revealed table scans due to missing composite indexes on tenant and created_at timestamps. "
        "Adding the composite index and rewriting subqueries into inner joins eliminated nested loop bottlenecks, "
        "ensuring write lock contention and deadlocks were avoided during concurrent updates."
    ]
    # Verify strict constraints on the test input:
    # 1. Zero predefined keywords
    for kw in comp_db["keywords"]:
        assert not re.search(r"\b" + re.escape(kw) + r"\b", ans_db[0], re.I), f"Keyword '{kw}' must not be in answer"
    # 2. Zero numbers/digits
    assert not any(ch.isdigit() for ch in ans_db[0]), "Answer must contain zero numbers"
    # 3. Zero first-person phrasing
    for pron in ["i", "we", "my", "our", "me", "us"]:
        assert not re.search(r"\b" + pron + r"\b", ans_db[0], re.I), f"Pronoun '{pron}' must not be in answer"

    score_db, wc_db, hits_db, digits_db, verbs_db = _score_answers(ans_db, comp_db)
    assert digits_db == 0
    assert len(hits_db) >= 3, f"Expected domain concept hits, got {hits_db}"
    # Must score well (Strong tier >= 6.5, specifically >= 7.0)
    assert score_db >= 7.0, f"Relevant technical explanation should score well (>= 7.0), got {score_db}"

    # Scenario B: REST API Design competency
    comp_api = {
        "id": "api_design",
        "name": "REST API Design",
        "description": "Designs consistent, versioned, well-documented APIs.",
        "keywords": ["rest", "api", "endpoint", "openapi", "swagger"],
        "rubric": {"1": "Consumes APIs", "3": "CRUD endpoints", "5": "Versioned contracts and error handling"}
    }
    ans_api = [
        "The service separates domain entities from HTTP transport representations using data transfer objects. "
        "Incoming request payloads undergo strict schema validation before dispatching to service handlers, "
        "and exceptions are mapped to standardized error response envelopes with machine-readable codes and idempotency keys to safely permit client retries."
    ]
    for kw in comp_api["keywords"]:
        assert not re.search(r"\b" + re.escape(kw) + r"\b", ans_api[0], re.I), f"Keyword '{kw}' must not be in answer"
    assert not any(ch.isdigit() for ch in ans_api[0]), "Answer must contain zero numbers"
    for pron in ["i", "we", "my", "our", "me", "us"]:
        assert not re.search(r"\b" + pron + r"\b", ans_api[0], re.I), f"Pronoun '{pron}' must not be in answer"

    score_api, wc_api, hits_api, digits_api, verbs_api = _score_answers(ans_api, comp_api)
    assert digits_api == 0
    assert len(hits_api) >= 3, f"Expected domain concept hits, got {hits_api}"
    assert score_api >= 7.0, f"Relevant technical explanation should score well (>= 7.0), got {score_api}"
def test_candidate_feedback_is_evidence_based_actionable_and_has_no_numeric_scores(settings):
    """Candidate feedback must be specific, evidence-based, contain actionable practice suggestions,
    and must never expose numeric scores or generic boilerplate."""
    import json
    import re
    from app.agents.assessment import SCORE_PATTERN

    comp_py = {
        "id": "python",
        "name": "Python Programming",
        "weight": 1.5,
        "keywords": ["python", "fastapi", "pytest"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Production services"},
        "answers": [
            "I designed and implemented our FastAPI backend service, writing pytest unit tests "
            "and structuring distinct service layers to ensure clean separation of concerns."
        ]
    }
    comp_db = {
        "id": "databases",
        "name": "Databases and SQL",
        "weight": 1.2,
        "keywords": ["postgresql", "sql", "redis"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Optimized queries"},
        "answers": ["I haven't used PostgreSQL or databases much; I only read about them briefly."]
    }
    ctx = {
        "job_title": "Backend Python Engineer",
        "competencies": [comp_py, comp_db],
        "planned_competencies": ["python", "databases"],
        "resume_summary": {"resume_score_0_100": 75.0},
        "trace_summary": {"decisions": ["NEXT_COMPETENCY"], "conclusion": "plan_completed"}
    }
    res = AssessmentAgent(DemoLLM(), settings).assess(ctx)
    fb = res.output.candidate_feedback

    # 1. No generic boilerplate
    assert "Thank you for interviewing" not in fb.summary
    assert "You engaged with every question asked" not in fb.strengths
    assert "Keep adding measurable results" not in fb.improvement_areas

    # 2. No numeric assessment scores in candidate-facing narrative fields
    narrative_blob = " ".join([fb.summary] + fb.strengths + fb.weaknesses + fb.improvement_areas)
    assert not SCORE_PATTERN.search(narrative_blob), f"Found numeric score pattern in candidate feedback: {narrative_blob}"
    # Verify no raw numbers/percentages leaked in candidate feedback
    assert not any(ch.isdigit() for ch in json.dumps(fb.model_dump()))

    # 3. Grounded in actual candidate answers and consistent with competency scores
    # Python (strong): mentioned in strengths with actual tools/techniques
    assert any("Python" in s for s in fb.strengths)
    assert any("fastapi" in s.lower() or "pytest" in s.lower() for s in fb.strengths)

    # Databases (weak): mentioned in weaknesses with explanation of what was missing
    assert any("Databases" in w for w in fb.weaknesses)
    # Improvement areas include actionable practice suggestion
    assert any("Databases" in imp for imp in fb.improvement_areas)
    assert any("query execution plans" in imp.lower() or "indexing" in imp.lower() for imp in fb.improvement_areas)


def test_recruiter_report_distinguishes_incomplete_provisional_from_complete(settings):
    """Recruiter summaries and recommendation rationales must be evidence-based and clearly distinguish
    incomplete provisional assessments from completed ones without treating unassessed competencies as poor ability."""
    comp_py = {
        "id": "python",
        "name": "Python Programming",
        "weight": 1.5,
        "keywords": ["python", "fastapi", "pytest"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Production services"},
        "answers": [
            "I designed and implemented our FastAPI backend service, writing pytest unit tests "
            "and structuring distinct service layers to ensure clean separation of concerns."
        ]
    }
    # Interview was interrupted/incomplete: only 1 of 3 planned competencies was assessed
    ctx_incomplete = {
        "job_title": "Backend Python Engineer",
        "competencies": [comp_py],
        "planned_competencies": ["python", "databases", "system_design"],
        "min_coverage": 0.75,
        "weights": {"resume": 0.4, "interview": 0.6},
        "thresholds": {"advance_min": 70.0, "review_min": 50.0},
        "resume_summary": {"resume_score_0_100": 80.0},
        "trace_summary": {"decisions": ["CONCLUDE"], "conclusion": "interrupted"}
    }
    res_inc = AssessmentAgent(DemoLLM(), settings).assess(ctx_incomplete)
    out_inc = res_inc.output

    # 1. Recruiter summary explicitly labels PROVISIONAL and lists unassessed competencies
    assert "PROVISIONAL ASSESSMENT" in out_inc.recruiter_summary
    assert "coverage" in out_inc.recruiter_summary.lower()
    # Explicitly states unassessed areas must not be treated as poor candidate ability
    assert "poor candidate ability" in out_inc.recruiter_summary or "session constraints" in out_inc.recruiter_summary

    # 2. Recommendation rationale explains why advance is withheld and requires recruiter review
    assert "PROVISIONAL" in out_inc.recommendation_rationale
    assert "BORDERLINE RECRUITER REVIEW" in out_inc.recommendation_rationale

    # 3. Complete interview scenario: all 2 planned competencies assessed
    comp_db = {
        "id": "databases",
        "name": "Databases and SQL",
        "weight": 1.2,
        "keywords": ["postgresql", "sql", "redis"],
        "rubric": {"1": "Vague", "3": "Working", "5": "Optimized queries"},
        "answers": [
            "I fixed a slow PostgreSQL query by reading the query plan, adding a composite index and rewriting a join, "
            "which cut latency by 60 percent."
        ]
    }
    ctx_complete = {
        "job_title": "Backend Python Engineer",
        "competencies": [comp_py, comp_db],
        "planned_competencies": ["python", "databases"],
        "min_coverage": 0.75,
        "weights": {"resume": 0.4, "interview": 0.6},
        "thresholds": {"advance_min": 70.0, "review_min": 50.0},
        "resume_summary": {"resume_score_0_100": 80.0},
        "trace_summary": {"decisions": ["NEXT_COMPETENCY", "CONCLUDE"], "conclusion": "plan_completed"}
    }
    res_comp = AssessmentAgent(DemoLLM(), settings).assess(ctx_complete)
    out_comp = res_comp.output
    assert "COMPLETE ASSESSMENT" in out_comp.recruiter_summary
    assert "RECOMMEND ADVANCE" in out_comp.recommendation_rationale


def test_misleading_answers_cannot_produce_high_scores():
    """Verify that reasoning phrases alone, action verbs alone, and buzzwords without meaningful explanation
    cannot produce high scores."""
    from app.agents.demo_logic import _score_answers

    comp = {
        "id": "databases",
        "name": "Databases and SQL",
        "description": "Models data, writes efficient queries, understands indexing and transactions.",
        "keywords": ["postgresql", "sql", "redis"],
        "rubric": {"1": "Basic queries", "3": "Indexes and schemas", "5": "Optimizes execution plans"}
    }

    # 1. Reasoning phrases alone without competency concepts
    ans_reasoning_only = [
        "Because of the trade-off and root cause investigation, we decided on a strategic architecture approach instead of alternatives."
    ]
    score_r, _, hits_r, _, _ = _score_answers(ans_reasoning_only, comp)
    assert score_r == 0.0
    assert hits_r == []

    # 2. Action verbs alone without competency concepts
    ans_actions_only = [
        "I designed, built, implemented, deployed, monitored, and automated the whole system."
    ]
    score_a, _, hits_a, _, _ = _score_answers(ans_actions_only, comp)
    assert score_a == 0.0
    assert hits_a == []

    # 3. Buzzwords + reasoning phrases without concrete actions
    ans_buzz_no_actions = [
        "PostgreSQL, Redis, indexing, transactions. Because of eventual consistency trade-offs."
    ]
    score_b, _, hits_b, _, verbs_b = _score_answers(ans_buzz_no_actions, comp)
    assert verbs_b == 0
    # Must be capped in Partial tier (<= 4.5), never Strong (>= 6.5)
    assert score_b <= 4.5

    # 4. Buzzwords + metrics without meaningful explanation
    ans_buzz_metrics = [
        "PostgreSQL, Redis. Managed 10 database clusters, 50k QPS, 99.99% uptime, reduced latency by 50%."
    ]
    score_bm, _, hits_bm, digits_bm, _ = _score_answers(ans_buzz_metrics, comp)
    assert digits_bm >= 2
    assert score_bm <= 4.5
