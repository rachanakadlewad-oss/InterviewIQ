"""Recruitment Agent: resume parsing support, competency matching, evidence-based scoring."""
import json
import logging

from app.agents.base import AgentError, AgentResult, run_agent
from app.agents.demo_logic import demo_resume_scores
from app.schemas import JobIn, ParsedProfile, ResumeScoringOutput
from app.textutil import contains_quote

log = logging.getLogger(__name__)

SCORE_SYSTEM = """You are the Recruitment Agent in a hiring pipeline. Score a candidate's resume against EACH job
competency from 0 to 10 using the supplied rubric (1 = minimal, 3 = working, 5 = strong; interpolate to 10).
Rules: (1) every score above 0 MUST cite 1-3 evidence excerpts copied VERBATIM from the resume text;
(2) if the resume has no evidence for a competency score it 0 with empty evidence; (3) never invent experience;
(4) return one entry for every competency id given; (5) keep justification to one or two sentences."""

PROFILE_SYSTEM = """You are the Recruitment Agent. Extract a structured profile from the resume text: name, email,
phone, skills (list), education (list), experience_years (number, total professional years, 0 if unknown), and a
one-sentence summary. Copy values from the text; use empty values when absent. Do not guess."""


class RecruitmentAgent:
    def __init__(self, llm, settings):
        self.llm, self.settings = llm, settings

    # -------- resume scoring --------
    def score_resume(self, job: JobIn, resume_text: str) -> AgentResult:
        ids = {c.id for c in job.competencies}

        def check(out: ResumeScoringOutput):
            got = {s.competency_id for s in out.scores}
            if got != ids:
                raise ValueError(f"scores must cover exactly competency ids {sorted(ids)}; got {sorted(got)}")
            for s in out.scores:
                if s.score > 0 and not s.evidence:
                    raise ValueError(f"score>0 without evidence for {s.competency_id}")
                for q in s.evidence:
                    if not contains_quote(resume_text, q):
                        raise ValueError(f"evidence for {s.competency_id} is not a verbatim resume excerpt: {q[:80]!r}")

        job_dict = job.model_dump()
        payload = {"job_title": job.title,
                   "competencies": [{"id": c.id, "name": c.name, "description": c.description, "rubric": c.rubric}
                                    for c in job.competencies],
                   "resume_text": resume_text[:12000]}
        return run_agent(name="RecruitmentAgent.score", llm=self.llm, system=SCORE_SYSTEM, payload=payload,
                         out_model=ResumeScoringOutput, demo_fn=lambda: demo_resume_scores(job_dict, resume_text),
                         semantic_check=check, max_retries=self.settings.agent_max_retries,
                         backoff=self.settings.agent_retry_backoff)

    # -------- profile enhancement (parsing support) --------
    def enhance_profile(self, base: ParsedProfile, resume_text: str) -> ParsedProfile:
        """Demo mode: keep the regex-parsed profile (no LLM). LLM mode: let the model refine it; on any failure
        fall back to the regex profile (parsing support must never block the pipeline)."""
        if self.llm.is_demo:
            return base
        try:
            res = run_agent(name="RecruitmentAgent.profile", llm=self.llm, system=PROFILE_SYSTEM,
                            payload={"resume_text": resume_text[:12000], "regex_profile": base.model_dump()},
                            out_model=ParsedProfile, demo_fn=lambda: base.model_dump(),
                            max_retries=1, backoff=self.settings.agent_retry_backoff)
            out = res.output
            return ParsedProfile(**{**base.model_dump(), **{k: v for k, v in out.model_dump().items() if v}})
        except AgentError as e:
            log.warning("profile enhancement skipped: %s", e)
            return base
