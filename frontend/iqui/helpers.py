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
