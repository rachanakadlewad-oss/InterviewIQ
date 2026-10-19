"""Assessment Agent: scores interview competencies from transcript evidence and writes the narratives.
(Combining resume + interview scores is deterministic and lives in app/services/scoring.py.)"""
import re

from app.agents.base import AgentResult, run_agent
from app.agents.demo_logic import demo_assessment
from app.schemas import AssessmentOutput
from app.textutil import contains_quote

SYSTEM = """You are the Assessment Agent. For EACH competency in the input, score the candidate's INTERVIEW answers
from 0 to 10 against the rubric (1 minimal, 3 working, 5 strong; interpolate). Every score above 2 MUST cite 1-3
evidence excerpts copied VERBATIM from that competency's candidate answers. Judge only job-related content, not
accent, fluency, personality or any protected attribute; short or nervous answers are scored on substance only.
Also produce: recruiter_summary (3-5 sentences, factual), recommendation_rationale (why the evidence supports or
does not support advancing; the human recruiter decides), strengths, weaknesses, and candidate_feedback
(summary, strengths, weaknesses, improvement_areas - constructive, specific, written TO the candidate).
candidate_feedback must NOT contain numeric scores, rankings, comparisons with other candidates, or the hiring
decision. Output one assessment entry per competency id supplied."""

SCORE_PATTERN = re.compile(r"\b\d+(\.\d+)?\s*(/\s*(10|100)|%)")


class AssessmentAgent:
    def __init__(self, llm, settings):
        self.llm, self.settings = llm, settings

    def assess(self, ctx: dict) -> AgentResult:
        """ctx = {job_title, competencies:[{id,name,weight,rubric,keywords,answers:[...]}], resume_summary, trace_summary}"""
        ids = {c["id"] for c in ctx["competencies"]}
        answers = {c["id"]: c["answers"] for c in ctx["competencies"]}
        all_text = " ".join(a for v in answers.values() for a in v)

        def check(out: AssessmentOutput):
            got = {c.competency_id for c in out.competencies}
            if got != ids:
                raise ValueError(f"must assess exactly {sorted(ids)}; got {sorted(got)}")
            for c in out.competencies:
                if c.score > 2 and not c.evidence:
                    raise ValueError(f"score>2 without evidence for {c.competency_id}")
                for q in c.evidence:
                    if not contains_quote(all_text, q):
                        raise ValueError(f"evidence for {c.competency_id} not verbatim from candidate answers: {q[:80]!r}")
            fb = out.candidate_feedback
            blob = " ".join([fb.summary] + fb.strengths + fb.weaknesses + fb.improvement_areas)
            if SCORE_PATTERN.search(blob):
                raise ValueError("candidate_feedback must not contain numeric scores")

        # keywords are used by demo mode only; do not send them to a real LLM
        payload = {**ctx, "competencies": [{k: v for k, v in c.items() if k != "keywords"} for c in ctx["competencies"]]}
        return run_agent(name="AssessmentAgent", llm=self.llm, system=SYSTEM, payload=payload,
                         out_model=AssessmentOutput, demo_fn=lambda: demo_assessment(ctx), semantic_check=check,
                         max_retries=self.settings.agent_max_retries, backoff=self.settings.agent_retry_backoff)
