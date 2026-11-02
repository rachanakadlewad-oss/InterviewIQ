"""Recruitment Agent: resume parsing support, competency matching, evidence-based scoring."""
import json
import logging

from app.agents.base import AgentError, AgentResult, run_agent
from app.agents.demo_logic import demo_resume_scores
from app.schemas import JobIn, ParsedProfile, ResumeScoringOutput
from app.textutil import contains_quote

log = logging.getLogger(__name__)

SCORE_SYSTEM = """You are the Recruitment Agent in a hiring pipeline. Semantically evaluate and score a candidate's resume
against EACH job competency from 0.0 to 10.0 using the supplied rubric (1 = minimal/basic, 3 = working/proficient, 5 = strong/expert; interpolate to a 0-10 scale).

Evaluation Standards:
1. Distinguish evidence level for each competency:
   - DIRECT EVIDENCE: The candidate demonstrates active responsibility, architectural contribution, or technical implementation in professional roles or substantial projects.
   - PARTIAL EVIDENCE: The technology is merely listed in a skills list, mentioned in an introductory/coursework/tutorial context, or used passively without demonstrated depth or ownership.
   - MISSING EVIDENCE: No relevant background, skills, or projects found in the resume.
2. Realistic Scoring Calibration:
   - Score 0.0: Missing evidence (evidence list MUST be empty).
   - Score 1.0 - 4.5: Partial evidence. Never award a score above 4.5 for simply listing a skill or mentioning a keyword without active responsibilities.
   - Score 5.0 - 7.0: Direct evidence of working competency (rubric level 3-4), meeting job requirements with clear responsibilities.
   - Score 7.5 - 9.0: Direct evidence with advanced responsibilities, architectural depth, or verified measurable achievements.
   - Reserve 9.5 - 10.0 strictly for exceptional, outstanding evidence demonstrating high-scale production leadership.
3. Measurable Achievements:
   - Consider genuine measurable results (e.g., latency reduction %, test coverage %, throughput req/s, users served, team size led).
   - Do NOT treat dates/years (e.g. 2021-2026), phone numbers, or tool version numbers (e.g. OAuth2, Python 3) as quantified impact.
4. Verbatim Excerpts:
   - For every score > 0, cite 1-3 evidence excerpts copied VERBATIM from the resume text.
   - Never invent, extrapolate, or assume experience not present in the resume text.
5. Justification:
   - In 1-2 sentences, state the evidence level ([Direct Evidence], [Partial Evidence], or [Missing Evidence]), summarize the candidate's responsibilities or project context, and state the reason for the score.
   - Return evidence_level field as "DIRECT", "PARTIAL", or "MISSING"."""

PROFILE_SYSTEM = """You are the Recruitment Agent. Extract a structured profile from the resume text:
- name: Candidate's full name (or empty string if not found)
- email: Email address (or empty string if not found)
- phone: Phone number (or empty string if not found)
- skills: List of detected technical skills and tools
- education: List of educational qualifications (degree, major, institution, dates if present)
- experience_years: Total professional work experience in years as a float (0.0 if unknown or student)
- summary: A one-sentence professional summary from the resume
- experience: List of professional roles held (job title, company, dates, and key responsibilities)
- projects: List of specific projects mentioned in the resume

Copy values directly from the text; use empty values when absent. NEVER invent or assume missing candidate information."""


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
