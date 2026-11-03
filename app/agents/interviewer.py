"""Interviewer Agent: reads the candidate's last answer and chooses the next action."""
from app.agents.base import AgentResult, run_agent
from app.agents.demo_logic import demo_interviewer
from app.schemas import InterviewerDecision
from app.services import interview_engine as eng
from app.textutil import contains_quote

SYSTEM = """You are the Interviewer Agent conducting a SPOKEN job interview. After each candidate answer, reason about
the MEANING of what they said and choose exactly one decision:
- NARROW_FOLLOW_UP: clarify or deepen what was just said (vague, unsupported claim, interesting detail).
- BROAD_PIVOT: the answer opened a NEW but relevant competency (e.g. the candidate mentions mentoring juniors while
  answering a technical question). Set target_competency to that competency's id (if it is in
  unexplored_job_competencies) or a short new competency name. Do not pivot to something already explored.
- NEXT_COMPETENCY: the current competency has enough evidence; set target_competency to one id from
  remaining_planned and write a natural question for it (you may adapt its seed_question).
- CONCLUDE: only if allowed.
Rules: trigger_phrase MUST be copied verbatim from the candidate's last answer (the words that drove your
decision). reasoning: 1-2 sentences on the meaning of the answer. Choose ONLY from allowed_decisions.
The 'question' field is strictly REQUIRED whenever decision is NARROW_FOLLOW_UP, BROAD_PIVOT, or NEXT_COMPETENCY (set question to empty or null only if CONCLUDE).
The question is read aloud: ONE short, natural, conversational question under 35 words, no lists, no preamble, never repeating a
question in asked_questions. Do not reveal scores or the rubric."""


class InterviewerAgent:
    def __init__(self, llm, settings):
        self.llm, self.settings = llm, settings

    def decide(self, job, ctx: dict) -> AgentResult:
        last_answer, allowed, asked = ctx["last_answer"], ctx["allowed_decisions"], ctx["asked_questions"]
        remaining_ids = {r["id"] for r in ctx["remaining_planned"]}

        def check(d: InterviewerDecision):
            if last_answer.strip() and not contains_quote(last_answer, d.trigger_phrase):
                raise ValueError("trigger_phrase must be quoted verbatim from the candidate's last answer")
            if d.decision.value not in allowed:
                raise ValueError(f"decision {d.decision.value} not allowed now; allowed: {allowed}")
            if d.decision.value == "NEXT_COMPETENCY" and d.target_competency not in remaining_ids:
                raise ValueError(f"NEXT_COMPETENCY target must be one of {sorted(remaining_ids)}")
            if d.question and eng.is_repeat(d.question, asked):
                raise ValueError("question repeats an earlier question")

        cm = eng.comp_map(job)
        dctx = dict(ctx)
        dctx["current_keywords"] = cm[ctx["current_competency"]["id"]].keywords if ctx["current_competency"]["id"] in cm else []
        return run_agent(name="InterviewerAgent", llm=self.llm, system=SYSTEM, payload=ctx,
                         out_model=InterviewerDecision, demo_fn=lambda: demo_interviewer(dctx),
                         semantic_check=check, max_retries=self.settings.agent_max_retries,
                         backoff=self.settings.agent_retry_backoff)
