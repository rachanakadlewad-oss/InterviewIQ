"""Deterministic interview-flow rules (NO LLM here).

The Interviewer Agent *proposes* a decision; this module *disposes*: it enforces completion conditions,
follow-up/pivot caps, question-budget fairness and no-repeat rules, and records the auditable trace.
All functions are pure with respect to the database (they mutate SessionState only)."""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.schemas import (InterviewAction as A, InterviewerDecision, JobIn, SessionState, TraceEntry, Turn)
from app.textutil import jaccard, norm, slug, truncate_words

REPEAT_THRESHOLD = 0.75
SEED_TEMPLATES = [
    "Tell me about a project where you used {n}. What was your role, and what was the outcome?",
    "Can you walk me through a hard decision you made involving {n}, and how it turned out?",
    "What is something you got wrong with {n}, and what did you change afterwards?",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def comp_map(job: JobIn) -> Dict[str, object]:
    return {c.id: c for c in job.competencies}


def plan_competencies(job: JobIn, resume_scores: Dict[str, float], k: int) -> List[str]:
    """Priority = weight x (1 + resume gap/10). High-weight competencies with weak/unverified resume evidence
    are probed first. Ties broken by JD order (stable sort). Documented in ARCHITECTURE.md."""
    ranked = sorted(job.competencies,
                    key=lambda c: -(c.weight * (1 + (10 - resume_scores.get(c.id, 0.0)) / 10)))
    return [c.id for c in ranked[:max(1, k)]]


def is_repeat(question: str, asked: List[str]) -> bool:
    q = norm(question)
    return any(norm(a) == q or jaccard(a, question) > REPEAT_THRESHOLD for a in asked)


def seed_question(job: JobIn, comp_id: str, asked: List[str]) -> str:
    c = comp_map(job).get(comp_id)
    name = c.name if c else comp_id
    candidates = list(c.questions) if c else []
    candidates += [t.format(n=name) for t in SEED_TEMPLATES]
    for q in candidates:
        if not is_repeat(q, asked):
            return q
    return f"Is there anything else about {name} you would like to add?"


def name_of(state: SessionState, job: JobIn, cid: str) -> str:
    c = comp_map(job).get(cid)
    return c.name if c else state.extra.get(cid, cid)


def resolve_target(job: JobIn, state: SessionState, label: Optional[str]) -> Tuple[str, str]:
    """Map an agent-supplied label to (competency_id, display name)."""
    label = (label or "").strip()
    for c in job.competencies:
        if norm(label) in (norm(c.id), norm(c.name)):
            return c.id, c.name
    for cid, nm in state.extra.items():
        if norm(label) in (norm(cid), norm(nm)):
            return cid, nm
    return f"extra_{slug(label)}", label


def uncovered(state: SessionState) -> List[str]:
    return [c for c in state.planned if c not in state.covered]


def may_conclude(state: SessionState, settings) -> bool:
    if not uncovered(state):
        return True
    covered_planned = len([c for c in state.planned if c in state.covered])
    return (covered_planned >= min(settings.min_competencies_covered, len(state.planned))
            and state.questions_asked >= min(settings.min_questions_before_conclude, settings.max_questions))


def extras_allowed(state: SessionState, settings) -> bool:
    """Spare budget exists only if every uncovered planned competency can still get a question."""
    return (settings.max_questions - state.questions_asked - len(uncovered(state))) >= 1


def allowed_decisions(state: SessionState, settings) -> List[str]:
    out = []
    if extras_allowed(state, settings) and state.followups_used.get(state.current, 0) < settings.max_followups_per_competency:
        out.append(A.NARROW_FOLLOW_UP.value)
    if extras_allowed(state, settings) and state.pivots_used < settings.max_broad_pivots:
        out.append(A.BROAD_PIVOT.value)
    if uncovered(state):
        out.append(A.NEXT_COMPETENCY.value)
    if may_conclude(state, settings):
        out.append(A.CONCLUDE.value)
    return out


# ------------------------------------------------------------------ session lifecycle
def new_state(job: JobIn, resume_scores: Dict[str, float], settings) -> Tuple[SessionState, TraceEntry]:
    planned = plan_competencies(job, resume_scores, settings.planned_competencies)
    first = planned[0]
    q = seed_question(job, first, [])
    st = SessionState(planned=planned, current=first, covered=[first], questions_asked=1,
                      asked_questions=[q], pending_question=q)
    st.transcript.append(Turn(turn=0, role="interviewer", text=q, competency=first))
    sc = resume_scores.get(first, 0.0)
    tr = TraceEntry(
        turn=0, timestamp=now_iso(), trigger_source="plan",
        trigger_phrase=f"PLAN: '{name_of(st, job, first)}' selected (JD weight x resume gap; resume score {sc:.1f}/10)",
        reasoning="Opening question for the highest-priority planned competency (no candidate answer exists yet).",
        decision=A.NEXT_COMPETENCY, competency=first, question_asked=q, source="plan")
    return st, tr


def record_answer(state: SessionState, text: str):
    state.answers_received += 1
    state.transcript.append(Turn(turn=state.answers_received, role="candidate", text=text, competency=state.current))


def decision_context(job: JobIn, state: SessionState, settings) -> dict:
    cm = comp_map(job)
    cur = cm.get(state.current)
    last_answer = next((t.text for t in reversed(state.transcript) if t.role == "candidate"), "")
    explored = [name_of(state, job, c) for c in state.covered]
    unexplored_jd = [{"id": c.id, "name": c.name} for c in job.competencies if c.id not in state.covered]
    return {
        "job_title": job.title,
        "current_competency": {"id": state.current, "name": name_of(state, job, state.current),
                               "rubric": cur.rubric if cur else {}},
        "last_question": state.pending_question,
        "last_answer": last_answer,
        "recent_transcript": [t.model_dump() for t in state.transcript[-6:]],
        "remaining_planned": [{"id": c, "name": name_of(state, job, c), "seed_question": seed_question(job, c, state.asked_questions)}
                              for c in uncovered(state)],
        "already_explored": explored,
        "unexplored_job_competencies": unexplored_jd,
        "asked_questions": state.asked_questions,
        "followups_left_for_current": max(0, settings.max_followups_per_competency - state.followups_used.get(state.current, 0)),
        "pivots_left": max(0, settings.max_broad_pivots - state.pivots_used),
        "questions_left": settings.max_questions - state.questions_asked,
        "allowed_decisions": allowed_decisions(state, settings),
    }


def force_conclude_reason(state: SessionState, settings) -> Optional[str]:
    """Hard completion condition checked BEFORE calling the agent (after a candidate answer is recorded)."""
    if state.questions_asked >= settings.max_questions:
        return "question_cap"
    return None


def _last_answer(state: SessionState) -> str:
    return next((t.text for t in reversed(state.transcript) if t.role == "candidate"), "")


def conclude(state: SessionState, reason: str, trigger: str, reasoning: str, source: str, note: str = "",
             agent_decision: Optional[str] = None, trigger_source: str = "candidate") -> TraceEntry:
    state.status = "CONCLUDED"
    state.conclusion_reason = reason
    state.pending_question = ""
    state.transcript.append(Turn(turn=state.answers_received, role="interviewer",
                                 text="Thank you, that covers everything I wanted to ask. That concludes the interview.",
                                 competency=state.current))
    return TraceEntry(turn=state.answers_received, timestamp=now_iso(), trigger_phrase=trigger or "(none)",
                      trigger_source=trigger_source, reasoning=reasoning, decision=A.CONCLUDE,
                      competency=state.current, question_asked="", source=source, guard_note=note,
                      agent_decision=agent_decision)


def force_conclude(state: SessionState, reason: str) -> TraceEntry:
    trig = truncate_words(_last_answer(state), 12) or "(no answer)"
    return conclude(state, reason, trig, f"Completion condition reached: {reason}. Interview ended by supervisor guard.",
                    "guard", note=reason, trigger_source="limit")


def fallback_decision(state: SessionState, job: JobIn) -> InterviewerDecision:
    """Used only when the Interviewer Agent fails validation/service retries. Clearly labelled 'fallback'."""
    rest = uncovered(state)
    trig = truncate_words(_last_answer(state), 12) or "(no answer)"
    if rest:
        return InterviewerDecision(
            trigger_phrase=trig, decision=A.NEXT_COMPETENCY, target_competency=rest[0],
            reasoning="Interviewer agent unavailable or invalid; safe fallback moves to the next planned competency.",
            question=seed_question(job, rest[0], state.asked_questions))
    return InterviewerDecision(trigger_phrase=trig, decision=A.CONCLUDE,
                               reasoning="Interviewer agent unavailable; all planned competencies already covered.")


def apply_decision(state: SessionState, job: JobIn, d: InterviewerDecision, source: str, settings) -> TraceEntry:
    notes: List[str] = []
    action = d.decision
    answered = state.current
    question = (d.question or "").strip()
    target, target_name = None, ""
    rest = uncovered(state)

    def to_next(why):
        nonlocal action, question
        notes.append(why)
        action, question = A.NEXT_COMPETENCY, ""

    if action == A.CONCLUDE and not may_conclude(state, settings):
        to_next("conclude blocked: minimum coverage not met")
    if action in (A.NARROW_FOLLOW_UP, A.BROAD_PIVOT) and not extras_allowed(state, settings):
        to_next("no spare question budget: each planned competency still needs a question")
    if action == A.NARROW_FOLLOW_UP and state.followups_used.get(answered, 0) >= settings.max_followups_per_competency:
        to_next("follow-up limit reached for this competency")
    if action == A.BROAD_PIVOT and state.pivots_used >= settings.max_broad_pivots:
        to_next("broad-pivot limit reached")
    if action == A.BROAD_PIVOT:
        cid, cname = resolve_target(job, state, d.target_competency)
        if cid in state.covered:
            to_next("pivot target already explored")
        else:
            target, target_name = cid, cname
    if action == A.NARROW_FOLLOW_UP:
        target = answered
    if action == A.NEXT_COMPETENCY:
        keep = bool(question) and d.target_competency in rest and d.decision == A.NEXT_COMPETENCY
        t = d.target_competency if keep else (rest[0] if rest else None)
        if t is None:
            action = A.CONCLUDE
            notes.append("no planned competencies remain")
        else:
            target = t
            if not keep:
                question = seed_question(job, t, state.asked_questions)
    # repeated-question guard
    if action != A.CONCLUDE and is_repeat(question, state.asked_questions):
        notes.append("repeated question rejected")
        if rest:
            action, target = A.NEXT_COMPETENCY, rest[0]
            question = seed_question(job, rest[0], state.asked_questions)
        else:
            action = A.CONCLUDE

    agent_decision = d.decision.value if (action != d.decision or notes) else None
    if notes:
        state.guard_overrides += 1
    final_source = "guard" if (notes and source in ("llm", "demo_rules")) else source
    note = "; ".join(notes)

    if action == A.CONCLUDE:
        reason = "agent_concluded" if not notes else ("all_planned_covered" if not rest else "guard_concluded")
        return conclude(state, reason, d.trigger_phrase, d.reasoning, final_source, note, agent_decision)

    if action == A.NARROW_FOLLOW_UP:
        state.followups_used[answered] = state.followups_used.get(answered, 0) + 1
    elif action == A.BROAD_PIVOT:
        state.pivots_used += 1
        if target not in state.planned:
            state.extra[target] = target_name or name_of(state, job, target)
        state.covered.append(target)
        state.current = target
    else:
        state.covered.append(target)
        state.current = target
    if source == "fallback":
        state.fallback_used += 1
    state.questions_asked += 1
    state.asked_questions.append(question)
    state.pending_question = question
    state.transcript.append(Turn(turn=state.answers_received, role="interviewer", text=question, competency=state.current))
    return TraceEntry(turn=state.answers_received, timestamp=now_iso(), trigger_phrase=d.trigger_phrase,
                      reasoning=d.reasoning, decision=action, competency=state.current,
                      question_asked=question, source=final_source, guard_note=note, agent_decision=agent_decision)


def answers_by_competency(state: SessionState) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for t in state.transcript:
        if t.role == "candidate":
            out.setdefault(t.competency, []).append(t.text)
    return out
