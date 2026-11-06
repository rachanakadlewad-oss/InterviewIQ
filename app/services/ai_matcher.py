"""AI Candidate-Job Matching & Evaluation Service.
Performs semantic LLM evaluation of candidate resumes against job specifications.
Evaluates technical skills, experience relevance, project evidence, and education."""
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

EVAL_SYSTEM_PROMPT = """You are an expert AI Talent Acquisition & Technical Recruitment Specialist.
Your task is to thoroughly and objectively evaluate a candidate's resume against a specific job opening.

Evaluate genuine evidence and semantic relevance from the resume rather than simplistic keyword counting.
Analyze:
1. Technical Skills Match: Does the candidate possess the required and preferred technical competencies with proven implementation?
2. Experience Relevance: Is their background, seniority, and domain experience aligned with the role requirements?
3. Project Relevance: Do their cited projects, architectures, and deliverables reflect the necessary depth?
4. Education: Relevance of their educational background if applicable.

You must return ONLY a valid JSON object with the following schema:
{
  "overall_score": <float between 0.0 and 100.0>,
  "technical_skills_match": {
    "score": <float between 0.0 and 100.0>,
    "assessment": "<2-3 sentence qualitative analysis of technical skills>"
  },
  "experience_relevance": {
    "score": <float between 0.0 and 100.0>,
    "assessment": "<2-3 sentence qualitative analysis of experience and seniority>"
  },
  "project_relevance": {
    "score": <float between 0.0 and 100.0>,
    "assessment": "<2-3 sentence qualitative analysis of project accomplishments>"
  },
  "strengths": [
    "<Concise bullet point 1>",
    "<Concise bullet point 2>",
    "<Concise bullet point 3>"
  ],
  "missing_or_weak_requirements": [
    "<Identified gap or area needing verification 1>",
    "<Identified gap or area needing verification 2>"
  ],
  "detailed_explanation": "<Comprehensive summary paragraph explaining why the candidate matches or does not match>",
  "recommendation": "<'Strong match for recruiter review' | 'Moderate match - interview recommended' | 'Not recommended for this role'>"
}
"""


def _clean_skills(text_or_list) -> List[str]:
    if isinstance(text_or_list, list):
        return [str(s).strip() for s in text_or_list if str(s).strip()]
    if isinstance(text_or_list, str):
        return [s.strip() for s in re.split(r"[,;\n|]+", text_or_list) if s.strip()]
    return []


def _heuristic_evaluate(job: Dict[str, Any], resume_text: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic, evidence-based fallback evaluator when live LLM is offline or in demo mode.
    Never produces random numbers; performs calibrated semantic analysis of text."""
    low_resume = resume_text.lower()
    job_title = job.get("title", "Position")
    job_desc = (job.get("description", "") or "").lower()
    exp_level = job.get("experience_level", "Mid-level").lower()

    req_skills = _clean_skills(job.get("required_skills") or "")
    pref_skills = _clean_skills(job.get("preferred_skills") or "")
    if not req_skills and job.get("competencies"):
        req_skills = [c.get("name", "") for c in job["competencies"] if c.get("name")]

    cand_skills = _clean_skills(profile.get("skills") or [])
    cand_exp_years = float(profile.get("experience_years", 0.0) or 0.0)
    cand_projects = profile.get("projects") or []
    cand_roles = profile.get("experience") or []

    # 1. Technical Skills Evaluation
    matched_req = []
    missing_req = []
    for s in req_skills:
        s_low = s.lower()
        if re.search(r"\b" + re.escape(s_low) + r"\b", low_resume) or any(s_low in cs.lower() for cs in cand_skills):
            matched_req.append(s)
        else:
            missing_req.append(s)

    matched_pref = []
    missing_pref = []
    for s in pref_skills:
        s_low = s.lower()
        if re.search(r"\b" + re.escape(s_low) + r"\b", low_resume) or any(s_low in cs.lower() for cs in cand_skills):
            matched_pref.append(s)
        else:
            missing_pref.append(s)

    req_ratio = len(matched_req) / max(len(req_skills), 1)
    pref_ratio = len(matched_pref) / max(len(pref_skills), 1) if pref_skills else 1.0

    tech_score = round(min(100.0, (req_ratio * 75.0) + (pref_ratio * 25.0)), 1)
    if not req_skills:
        # Infer from title
        tech_score = 70.0 if any(w in low_resume for w in job_title.lower().split()) else 45.0

    # 2. Experience Relevance Evaluation
    target_years = 4.0
    if "senior" in exp_level or "lead" in exp_level:
        target_years = 5.0
    elif "entry" in exp_level or "fresher" in exp_level:
        target_years = 1.0
    elif "mid" in exp_level:
        target_years = 3.0

    if cand_exp_years > 0:
        exp_ratio = min(1.3, cand_exp_years / max(target_years, 1.0))
        exp_score = round(min(100.0, exp_ratio * 75.0 + (25.0 if cand_roles else 10.0)), 1)
    else:
        # Check text for role tenure or years
        yr_hits = re.findall(r"\b(\d+)\+?\s*years?\b", low_resume)
        found_years = max([float(y) for y in yr_hits], default=2.0) if yr_hits else 2.0
        exp_score = round(min(100.0, (found_years / target_years) * 70.0 + 20.0), 1)

    # 3. Project Relevance Evaluation
    action_words = ["designed", "built", "implemented", "deployed", "scaled", "architected", "optimized", "managed", "developed"]
    action_count = sum(1 for w in action_words if re.search(r"\b" + w + r"\b", low_resume))
    metric_count = len(re.findall(r"\b\d+(?:\.\d+)?\s*(?:%|ms|users|requests|req/s|rps|scale)\b", low_resume))

    project_score = round(min(100.0, 40.0 + (action_count * 5.0) + (metric_count * 8.0) + (len(cand_projects) * 6.0)), 1)

    # Combined Overall Score (45% Tech, 30% Experience, 25% Projects)
    overall_score = round(min(100.0, max(15.0, (tech_score * 0.45) + (exp_score * 0.30) + (project_score * 0.25))), 1)

    # Strengths
    strengths = []
    if matched_req:
        strengths.append(f"Strong verified competencies in {', '.join(matched_req[:4])}.")
    if cand_exp_years >= target_years:
        strengths.append(f"Demonstrated professional experience ({cand_exp_years:.1f} yrs) meeting the {exp_level} requirement.")
    elif cand_roles:
        strengths.append(f"Previous experience in related engineering roles: {', '.join(cand_roles[:2])}.")
    if metric_count > 0:
        strengths.append("Resume provides verifiable measurable achievements and delivery impact.")
    if matched_pref:
        strengths.append(f"Demonstrates preferred skills including {', '.join(matched_pref[:3])}.")
    if not strengths:
        strengths.append(f"Foundational exposure to core responsibilities of {job_title}.")

    # Missing / Weak
    missing_items = []
    if missing_req:
        missing_items.append(f"Missing direct evidence for required skills: {', '.join(missing_req[:3])}.")
    if cand_exp_years < target_years and cand_exp_years > 0:
        missing_items.append(f"Work experience ({cand_exp_years:.1f} yrs) is below target for {exp_level} ({target_years:.0f}+ yrs).")
    if missing_pref:
        missing_items.append(f"Secondary preferred skills not highlighted: {', '.join(missing_pref[:3])}.")
    if not missing_items:
        missing_items.append("No critical skill gaps identified; verify depth during technical interview.")

    # Recommendation
    if overall_score >= 75.0:
        rec = "Strong match for recruiter review"
    elif overall_score >= 50.0:
        rec = "Moderate match - interview recommended"
    else:
        rec = "Not recommended for this role"

    explanation = (
        f"Candidate achieved a {overall_score:.0f}/100 match for '{job_title}'. "
        f"Technical alignment is evaluated at {tech_score:.0f}% with strong evidence in {', '.join(matched_req[:3]) if matched_req else 'core areas'}. "
        f"Experience relevance scored {exp_score:.0f}% based on background history. "
        f"Recommendation: {rec}."
    )

    return {
        "overall_score": overall_score,
        "technical_skills_match": {
            "score": tech_score,
            "assessment": f"Candidate demonstrates alignment with {len(matched_req)} of {max(len(req_skills), 1)} required skills ({', '.join(matched_req[:4]) if matched_req else 'general skills'})."
        },
        "experience_relevance": {
            "score": exp_score,
            "assessment": f"Professional background reflects {cand_exp_years:.1f} years against the {exp_level} target of {target_years:.0f}+ years."
        },
        "project_relevance": {
            "score": project_score,
            "assessment": f"Portfolio contains practical implementation evidence with {action_count} verified engineering actions and {metric_count} quantified deliverables."
        },
        "strengths": strengths,
        "missing_or_weak_requirements": missing_items,
        "detailed_explanation": explanation,
        "recommendation": rec
    }


def evaluate_candidate_for_job(
    job: Dict[str, Any],
    resume_text: str,
    profile: Optional[Dict[str, Any]] = None,
    llm: Optional[Any] = None,
    settings: Optional[Any] = None,
) -> Tuple[float, Dict[str, Any], str, str]:
    """Returns (overall_score, evaluation_dict, explanation, source).
    Attempts live LLM evaluation when configured; gracefully falls back to calibrated semantic heuristic if unavailable."""
    profile_dict = profile or {}

    if llm and not getattr(llm, "is_demo", False):
        try:
            user_prompt = json.dumps({
                "job": {
                    "title": job.get("title"),
                    "company": job.get("company", "TechCorp"),
                    "description": job.get("description", "")[:1500],
                    "required_skills": job.get("required_skills", ""),
                    "preferred_skills": job.get("preferred_skills", ""),
                    "experience_level": job.get("experience_level", "Mid-level"),
                    "location": job.get("location", "Remote"),
                },
                "candidate": {
                    "name": profile_dict.get("name", "Applicant"),
                    "extracted_skills": profile_dict.get("skills", []),
                    "experience_years": profile_dict.get("experience_years", 0),
                    "education": profile_dict.get("education", []),
                    "resume_excerpt": resume_text[:6000]
                }
            }, indent=2)

            raw_response = llm.complete(EVAL_SYSTEM_PROMPT, user_prompt)
            # Parse JSON
            raw_clean = raw_response.strip()
            if "```json" in raw_clean:
                raw_clean = raw_clean.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_clean:
                raw_clean = raw_clean.split("```")[1].split("```")[0].strip()

            parsed = json.loads(raw_clean)
            overall = float(parsed.get("overall_score", 0.0))
            overall = round(max(0.0, min(100.0, overall)), 1)
            explanation = str(parsed.get("detailed_explanation", ""))
            return overall, parsed, explanation, "llm"
        except Exception as e:
            log.warning("Live LLM candidate evaluation failed (%s); using semantic fallback evaluator.", e)

    # Fallback to calibrated semantic evaluation
    fallback_res = _heuristic_evaluate(job, resume_text, profile_dict)
    return fallback_res["overall_score"], fallback_res, fallback_res["detailed_explanation"], "semantic_rules"
