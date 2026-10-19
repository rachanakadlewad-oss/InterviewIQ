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
