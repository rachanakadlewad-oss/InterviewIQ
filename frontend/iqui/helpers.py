"""Pure UI helpers (no Streamlit import) so they can be unit-tested."""
from datetime import datetime
from typing import List, Optional, Tuple

# status -> (recruiter label, badge tone)
STATUS = {
    "PARSED": ("Parsed", "neutral"), "SCORING_FAILED": ("Scoring failed", "error"), "SCORED": ("Scored", "info"),
    "SHORTLISTED": ("Shortlisted", "info"), "SCHEDULED": ("Scheduled", "info"), "HUMAN_REVIEW": ("Identity review", "warning"),
    "IDENTITY_PASSED": ("Identity verified", "success"), "INTERVIEW_IN_PROGRESS": ("Interview in progress", "warning"),
    "INTERVIEW_COMPLETE": ("Assessing", "info"), "ASSESSED": ("Awaiting decision", "warning"),
    "ASSESSMENT_FAILED": ("Assessment failed", "error"), "DECIDED": ("Decided", "success"),
    "REJECTED_AT_REVIEW": ("Closed at review", "error"),
}
DECISION_TONE = {"NEXT_COMPETENCY": "info", "NARROW_FOLLOW_UP": "warning", "BROAD_PIVOT": "success", "CONCLUDE": "neutral"}
DECISION_LABEL = {"NEXT_COMPETENCY": "Next competency", "NARROW_FOLLOW_UP": "Narrow follow-up",
                  "BROAD_PIVOT": "Broad pivot", "CONCLUDE": "Conclude"}
RECOMMENDATION = {"RECOMMEND_ADVANCE": ("Recommend advancing", "success"),
                  "BORDERLINE_RECRUITER_REVIEW": ("Borderline - review closely", "warning"),
                  "NOT_RECOMMENDED": ("Not recommended", "error")}
SOURCE = {"demo_rules": ("Demo rules", "warning"), "llm": ("LLM", "info"), "plan": ("Plan", "neutral"),
          "guard": ("Supervisor guard", "neutral"), "fallback": ("Fallback", "warning")}


def status_label(status: str) -> Tuple[str, str]:
    return STATUS.get(status, (status.replace("_", " ").title(), "neutral"))


def source_label(src: Optional[str]) -> Tuple[str, str]:
    if not src:
        return ("Not scored", "neutral")
    return SOURCE.get(src, (src, "neutral"))


def score_tone(score: Optional[float], out_of: float = 100) -> str:
    if score is None:
        return "neutral"
    pct = score / out_of
    return "success" if pct >= 0.7 else "warning" if pct >= 0.5 else "error"


def fmt_dt(iso: Optional[str], with_date: bool = True) -> str:
    if not iso:
        return "-"
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    return d.strftime("%a %d %b, %H:%M") if with_date else d.strftime("%H:%M")


def fmt_score(v, digits: int = 1) -> str:
    return "-" if v is None else f"{v:.{digits}f}"


def slugify_id(name: str, taken: set) -> str:
    import re
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30] or "competency"
    cid, n = base, 2
    while cid in taken:
        cid, n = f"{base}_{n}", n + 1
    return cid


# ---- candidate-facing progress (hides recruiter-internal stages such as scoring) ----
CAND_STEPS = ["Application received", "Interview scheduled", "Identity verification", "Interview", "Feedback"]
_CAND_REACHED = {"PARSED": 0, "SCORING_FAILED": 0, "SCORED": 0, "SHORTLISTED": 0, "SCHEDULED": 1, "HUMAN_REVIEW": 2,
                 "REJECTED_AT_REVIEW": 2, "IDENTITY_PASSED": 3, "INTERVIEW_IN_PROGRESS": 3, "INTERVIEW_COMPLETE": 4,
                 "ASSESSMENT_FAILED": 4, "ASSESSED": 5, "DECIDED": 5}


def candidate_steps(status: str) -> List[Tuple[str, str]]:
    """-> [(label, state)] where state in done | current | todo"""
    cur = _CAND_REACHED.get(status, 0)
    if status in ("SCHEDULED",):
        cur = 2          # next thing the candidate must do: identity check
    out = []
    for i, label in enumerate(CAND_STEPS):
        out.append((label, "done" if i < cur else "current" if i == cur else "todo"))
    if status in ("ASSESSED", "DECIDED"):
        out = [(l, "done") for l in CAND_STEPS]
    return out


RECRUITER_STAGES = [
    "Scheduled",
    "Identity Verified",
    "Interview Conducted",
    "Assessment Generated",
    "Report Available",
    "Recruiter Decision"
]


def recruiter_workflow_steps(status: str) -> List[Tuple[str, str]]:
    """Return [(label, state)] for the recruiter assessment workflow pipeline."""
    curr_idx = {
        "PARSED": 0, "SCORING_FAILED": 0, "SCORED": 0, "SHORTLISTED": 0,
        "SCHEDULED": 1,
        "HUMAN_REVIEW": 1,
        "REJECTED_AT_REVIEW": 1,
        "IDENTITY_PASSED": 2,
        "INTERVIEW_IN_PROGRESS": 2,
        "INTERVIEW_COMPLETE": 3,
        "ASSESSMENT_FAILED": 3,
        "ASSESSED": 5,
        "DECIDED": 6
    }.get(status, 1)

    out = []
    for i, label in enumerate(RECRUITER_STAGES):
        if status == "DECIDED":
            out.append((label, "done"))
        elif i < curr_idx:
            out.append((label, "done"))
        elif i == curr_idx:
            out.append((label, "current"))
        else:
            out.append((label, "todo"))
    return out


def candidate_message(status: str) -> Tuple[str, str, str]:
    """-> (headline, explanation, tone)"""
    m = {
        "SCHEDULED": ("Verify your identity", "Your interview is booked. Complete the identity check, then you can start.", "info"),
        "HUMAN_REVIEW": ("Identity check is being reviewed", "A person will review your identity check. The interview cannot start until they respond - please contact the recruiter.", "warning"),
        "IDENTITY_PASSED": ("You are ready", "Identity confirmed. Start the interview when you are ready.", "success"),
        "INTERVIEW_IN_PROGRESS": ("Interview in progress", "Continue your interview in the Join Interview section.", "warning"),
        "INTERVIEW_COMPLETE": ("Interview complete", "Thank you. Your answers are being assessed - feedback will appear here.", "info"),
        "ASSESSMENT_FAILED": ("Interview complete", "Thank you. Your feedback is taking longer than expected; the recruiter has been notified in their console.", "info"),
        "ASSESSED": ("Feedback is ready", "Open My Feedback to see your strengths and areas to improve.", "success"),
        "DECIDED": ("Feedback is ready", "Open My Feedback to see your strengths and areas to improve. The recruiter will contact you about next steps.", "success"),
        "REJECTED_AT_REVIEW": ("Application closed", "Your identity could not be confirmed, so the application was closed. Contact the recruiter if you think this is a mistake.", "error"),
    }
    return m.get(status, ("Application received", "Your application is being processed.", "neutral"))


def competency_rows_valid(rows: list) -> Tuple[list, List[str]]:
    """Validate guided-form competency rows. Returns (clean competency dicts, error messages)."""
    errors, clean, names, taken = [], [], set(), set()
    for i, r in enumerate(rows, 1):
        name = (r.get("name") or "").strip()
        if not name and not any(str(v or "").strip() for k, v in r.items() if k != "weight"):
            continue                                   # fully blank row
        if not name:
            errors.append(f"Competency row {i}: name is required.")
            continue
        if name.lower() in names:
            errors.append(f"Competency '{name}' appears twice - names must be unique.")
            continue
        names.add(name.lower())
        try:
            w = float(r.get("weight") if r.get("weight") not in (None, "") else 1.0)
        except (TypeError, ValueError):
            errors.append(f"'{name}': weight must be a number.")
            continue
        if w <= 0:
            errors.append(f"'{name}': weight must be greater than 0.")
            continue
        cid = slugify_id(name, taken)
        taken.add(cid)
        rub = {k: (r.get(f).strip()) for k, f in (("1", "rubric_basic"), ("3", "rubric_working"), ("5", "rubric_strong")) if (r.get(f) or "").strip()}
        q = (r.get("question") or "").strip()
        clean.append({"id": cid, "name": name, "description": (r.get("description") or "").strip(), "weight": w, "rubric": rub,
                      "questions": [q] if q else [],
                      "keywords": [k.strip() for k in (r.get("keywords") or "").split(",") if k.strip()]})
    if not clean and not errors:
        errors.append("Add at least one competency.")
    return clean, errors


def analyze_competency_details(comp: dict, score_data: Optional[dict]) -> dict:
    import re
    cid = comp.get("id", "")
    name = comp.get("name", cid.replace("_", " ").title())
    description = comp.get("description", "")
    weight = float(comp.get("weight", 1.0))
    rubric = comp.get("rubric", {})
    keywords = comp.get("keywords", [])
    questions = comp.get("questions", [])

    score = float(score_data.get("score", 0.0)) if score_data else 0.0
    evidence = list(score_data.get("evidence", [])) if score_data else []
    justification = str(score_data.get("justification", "")) if score_data else ""
    evidence_level = (score_data.get("evidence_level") if score_data else None)

    # Infer evidence level if missing
    if not evidence_level:
        if "Direct Evidence" in justification or score >= 6.5:
            evidence_level = "DIRECT"
        elif "Partial Evidence" in justification or (0 < score < 6.5):
            evidence_level = "PARTIAL"
        else:
            evidence_level = "MISSING"

    # Status label & tone
    if evidence_level == "DIRECT" or score >= 6.5:
        level_label = "Strong evidence"
        level_tone = "success"
    elif evidence_level == "PARTIAL" or score > 0:
        level_label = "Partial evidence"
        level_tone = "warning"
    else:
        level_label = "Missing evidence"
        level_tone = "neutral"

    # Clean explanation
    clean_just = re.sub(r"^\[Demo Heuristic - [^\]]+\]\s*", "", justification).strip()
    if evidence_level == "MISSING" or score == 0.0:
        relevance_explanation = (
            f"No relevant evidence was identified in the resume text for {name}. "
            f"The candidate did not mention expected core concepts ({', '.join(keywords[:4]) if keywords else name}). "
            f"This represents an unverified area that should be explored directly during the interview."
        )
    else:
        if description and description.lower() not in clean_just.lower():
            relevance_explanation = f"{clean_just} (Evaluated against requirement: {description})"
        else:
            relevance_explanation = clean_just

    # Demonstrated items
    demonstrated_points = []
    if evidence_level == "MISSING" or score == 0.0:
        demonstrated_points.append("No relevant skills, projects, or responsibilities cited in resume.")
    else:
        evidence_text = (justification + " " + " ".join(evidence)).lower()
        hits = [k for k in keywords if re.search(r"\b" + re.escape(k.lower()), evidence_text)]
        if hits:
            demonstrated_points.append(f"Referenced technologies/concepts: {', '.join(hits[:5])}.")
        if evidence_level == "DIRECT":
            demonstrated_points.append("Demonstrated professional ownership and active implementation.")
            metrics = re.findall(
                r"\b(?:\d+(?:\.\d+)?\s*%|\d[\d,]*(?:[kKmMbB])?\+?\s*(?:requests|req|qps|rps|users|concurrent)|\d+\s*(?:ms|seconds)|team\s*of\s*\d+|\d+\s*endpoints)\b",
                justification + " " + " ".join(evidence),
                re.I
            )
            if metrics:
                demonstrated_points.append(f"Verified measurable achievements: {', '.join(metrics[:2])}.")
            if rubric.get("3"):
                demonstrated_points.append(f"Working proficiency: {rubric['3']}")
        else:
            demonstrated_points.append("Introductory, academic, or junior task exposure without production scale.")

    # Missing / gap items
    missing_points = []
    evidence_text = (justification + " " + " ".join(evidence)).lower()
    if evidence_level == "MISSING" or score == 0.0:
        if keywords:
            missing_points.append(f"Missing core domain technologies: {', '.join(keywords[:5])}.")
        if rubric.get("3"):
            missing_points.append(f"Working competency requirement: {rubric['3']}")
        if rubric.get("5"):
            missing_points.append(f"Advanced design expectation: {rubric['5']}")
        missing_points.append("No active or passive experience demonstrated on paper.")
    elif evidence_level == "PARTIAL":
        unhit = [k for k in keywords if not re.search(r"\b" + re.escape(k.lower()), evidence_text)]
        if unhit:
            missing_points.append(f"Unrepresented production tools: {', '.join(unhit[:4])}.")
        if rubric.get("3"):
            missing_points.append(f"Working standard: {rubric['3']}")
        if rubric.get("5"):
            missing_points.append(f"Advanced architecture: {rubric['5']}")
        missing_points.append("No quantified scale, latency, or throughput metrics reported.")
    else:
        if rubric.get("5"):
            missing_points.append(f"Advanced depth to verify: {rubric['5']}")
        missing_points.append("Failure modes & trade-offs: Resume verifies delivery; probe how edge cases and outages were handled.")

    # Suggested interview validation questions
    suggested_questions = []
    if questions:
        suggested_questions.append({
            "tag": "Primary Domain Question",
            "question": questions[0]
        })
    else:
        suggested_questions.append({
            "tag": "Primary Domain Question",
            "question": f"Can you walk me through your experience with {name} and describe a project where you applied it?"
        })

    if evidence_level == "MISSING":
        suggested_questions.append({
            "tag": "Gap Exploration Probe",
            "question": f"Your resume focuses on other areas and does not highlight {name}. Have you worked with {name} (or tools like {', '.join(keywords[:3]) if keywords else 'related technologies'}) in unlisted projects or prior roles?"
        })
    elif evidence_level == "PARTIAL":
        suggested_questions.append({
            "tag": "Production Depth Probe",
            "question": f"You mentioned {name} in a project context. What were the specific scale constraints, and what would you do differently to make it production-ready?"
        })
    else:
        suggested_questions.append({
            "tag": "Trade-offs & Resilience Probe",
            "question": f"In your implementation of {name}, what critical architectural trade-offs did you make, and how did you measure success?"
        })

    return {
        "cid": cid,
        "name": name,
        "description": description,
        "weight": weight,
        "score": score,
        "evidence": evidence,
        "evidence_level": evidence_level,
        "level_label": level_label,
        "level_tone": level_tone,
        "relevance_explanation": relevance_explanation,
        "demonstrated_points": demonstrated_points,
        "missing_points": missing_points,
        "suggested_questions": suggested_questions,
    }


# ---- shortlist management helpers -------------------------------------------
def sort_candidates_by_score(apps: List[dict]) -> List[dict]:
    """Sorts candidates strictly in descending order of resume score, secondary by rank."""
    return sorted(
        apps,
        key=lambda a: (
            -float(a.get("resume_score") if a.get("resume_score") is not None else -1.0),
            a.get("rank") if a.get("rank") is not None else 9999,
            a.get("application_id", 0)
        )
    )


def get_confirmed_shortlist_ids(apps: List[dict]) -> List[int]:
    """Returns application IDs confirmed as shortlisted in the database and still editable."""
    return [
        a["application_id"]
        for a in apps
        if a.get("shortlisted") and a.get("status") in ("SCORED", "SHORTLISTED")
    ]


def add_candidate_to_selection(selected_ids: List[int], app_id: int) -> List[int]:
    """Adds candidate ID ensuring no duplicates."""
    res = list(selected_ids)
    if app_id not in res:
        res.append(app_id)
    return res


def remove_candidate_from_selection(selected_ids: List[int], app_id: int) -> List[int]:
    """Removes candidate ID if present."""
    return [i for i in selected_ids if i != app_id]


def validate_shortlist_selection(selected_ids: List[int], apps: List[dict]) -> Tuple[bool, List[str]]:
    """Validates candidate selection before confirmation against pipeline rules."""
    errors = []
    if not selected_ids:
        errors.append("No candidates selected. Please select at least one candidate before confirming the shortlist.")
        return False, errors

    if len(selected_ids) != len(set(selected_ids)):
        errors.append("Duplicate candidate selections detected.")

    app_map = {a["application_id"]: a for a in apps}
    for aid in selected_ids:
        if aid not in app_map:
            errors.append(f"Application #{aid} does not belong to this job or is unscored.")
        else:
            cand = app_map[aid]
            if cand.get("status") not in ("SCORED", "SHORTLISTED"):
                errors.append(f"Candidate {cand.get('name') or f'#{aid}'} is already past the shortlisting stage ({cand.get('status')}).")

    return (len(errors) == 0), errors
