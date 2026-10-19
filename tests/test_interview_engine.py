import pytest

from app.agents.interviewer import InterviewerAgent
from app.llm.client import DemoLLM
from app.schemas import InterviewAction as A, InterviewerDecision
from app.services import interview_engine as eng


def fresh(job_in, settings, scores=None):
    return eng.new_state(job_in, scores or {c.id: 5.0 for c in job_in.competencies}, settings)


def dec(action, trig="x y", q="What else can you tell me about it?", target=None):
    return InterviewerDecision(trigger_phrase=trig, reasoning="because reasons", decision=action, question=q if action != A.CONCLUDE else None, target_competency=target)


def run_interview(job_in, settings, answers):
    st, tr = fresh(job_in, settings)
    traces, agent, i = [tr], InterviewerAgent(DemoLLM(), settings), 0
    while st.status == "ACTIVE":
        eng.record_answer(st, answers[i % len(answers)]); i += 1
        reason = eng.force_conclude_reason(st, settings)
        if reason:
            traces.append(eng.force_conclude(st, reason)); break
        d = agent.decide(job_in, eng.decision_context(job_in, st, settings))
        traces.append(eng.apply_decision(st, job_in, d.output, d.source, settings))
        assert i < 50, "interview did not terminate"
    return st, traces


def test_plan_prioritises_weight_times_gap(job_in, settings):
    scores = {c.id: 9.0 for c in job_in.competencies}
    scores["security"] = 0.0                    # big gap, low weight (0.8*2=1.6) vs python (1.5*1.1=1.65)
    plan = eng.plan_competencies(job_in, scores, 4)
    assert "security" in plan and len(plan) == 4 and plan[0] == "python"


def test_opening_question_is_traced_with_plan_trigger(job_in, settings):
    st, tr = fresh(job_in, settings)
    assert tr.trigger_source == "plan" and tr.question_asked == st.pending_question and tr.competency == st.current


def test_followup_cap_is_enforced(job_in, settings):
    st, _ = fresh(job_in, settings)
    for _ in range(5):
        if st.status != "ACTIVE":
            break
        eng.record_answer(st, "short")
        eng.apply_decision(st, job_in, dec(A.NARROW_FOLLOW_UP, "short", f"Tell me more number {_} about it please?"), "llm", settings)
    assert max(st.followups_used.values()) <= settings.max_followups_per_competency
    assert st.guard_overrides >= 1


def test_repeated_question_is_replaced(job_in, settings):
    st, _ = fresh(job_in, settings)
    eng.record_answer(st, "some answer here")
    first_q = st.pending_question
    tr = eng.apply_decision(st, job_in, dec(A.NARROW_FOLLOW_UP, "some answer", first_q), "llm", settings)
    assert "repeated question rejected" in tr.guard_note
    assert st.asked_questions.count(first_q) == 1 and len(set(st.asked_questions)) == len(st.asked_questions)


def test_early_conclude_is_blocked(job_in, settings):
    st, _ = fresh(job_in, settings)
    eng.record_answer(st, "some answer here")
    tr = eng.apply_decision(st, job_in, dec(A.CONCLUDE, "some answer"), "llm", settings)
    assert st.status == "ACTIVE" and tr.decision == A.NEXT_COMPETENCY and tr.agent_decision == "CONCLUDE"


def test_pivot_to_unplanned_competency_is_recorded(job_in, settings):
    scores = {c.id: 5.0 for c in job_in.competencies}
    scores["leadership"] = 9.0                    # strong evidence -> not planned
    st, _ = eng.new_state(job_in, scores, settings)
    assert "leadership" not in st.planned
    eng.record_answer(st, "I also mentored two juniors")
    tr = eng.apply_decision(st, job_in, dec(A.BROAD_PIVOT, "mentored two juniors", "How did you help them grow?", "leadership"), "llm", settings)
    assert tr.decision == A.BROAD_PIVOT and st.current == "leadership" and "leadership" in st.extra
    assert st.pivots_used == 1 and tr.guard_note == ""


def test_pivot_to_already_explored_competency_is_downgraded(job_in, settings):
    st, _ = fresh(job_in, settings)
    eng.record_answer(st, "some answer here")
    tr = eng.apply_decision(st, job_in, dec(A.BROAD_PIVOT, "some answer", "A fresh and different question about this?", st.current), "llm", settings)
    assert tr.decision == A.NEXT_COMPETENCY and "already explored" in tr.guard_note


def test_budget_guard_protects_every_planned_competency(job_in, settings):
    settings.max_questions = 5
    st, _ = fresh(job_in, settings)               # 4 planned, 5 questions: only 1 spare
    eng.record_answer(st, "short")
    eng.apply_decision(st, job_in, dec(A.NARROW_FOLLOW_UP, "short", "Could you expand on that point please?"), "llm", settings)
    assert st.questions_asked == 2
    eng.record_answer(st, "short")
    tr = eng.apply_decision(st, job_in, dec(A.NARROW_FOLLOW_UP, "short", "Another clarifying question here please?"), "llm", settings)
    assert tr.decision == A.NEXT_COMPETENCY and "budget" in tr.guard_note


def test_interview_always_terminates_with_vague_answers(job_in, settings):
    st, traces = run_interview(job_in, settings, ["ok", "yes", "not sure"])
    assert st.status == "CONCLUDED" and st.questions_asked <= settings.max_questions
    assert len(set(st.asked_questions)) == len(st.asked_questions)             # no repeats
    assert len([c for c in st.planned if c in st.covered]) == len(st.planned)  # every planned competency asked


def test_interview_terminates_with_rich_answers_and_traces_are_complete(job_in, settings):
    from tests.helpers import ANSWERS
    st, traces = run_interview(job_in, settings, ANSWERS)
    assert st.status == "CONCLUDED" and st.questions_asked <= settings.max_questions
    for t in traces:
        assert t.trigger_phrase and t.reasoning and t.decision and t.competency
        if t.decision != A.CONCLUDE:
            assert t.question_asked
    asked = [t.question_asked for t in traces if t.question_asked]
    assert asked == st.asked_questions                                             # every question is traced


def test_question_cap_forces_conclusion(job_in, settings):
    settings.max_questions = 4
    st, traces = run_interview(job_in, settings, ["a very short reply"])
    assert st.questions_asked <= 4 and st.status == "CONCLUDED"


def test_fallback_decision_is_safe(job_in, settings):
    st, _ = fresh(job_in, settings)
    eng.record_answer(st, "anything at all here")
    d = eng.fallback_decision(st, job_in)
    tr = eng.apply_decision(st, job_in, d, "fallback", settings)
    assert tr.source == "fallback" and st.fallback_used == 1 and tr.decision == A.NEXT_COMPETENCY
