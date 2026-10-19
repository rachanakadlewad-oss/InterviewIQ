"""Recruiter dashboard metrics, computed from real rows (nothing is fabricated).

Definitions (shown to the user in the UI):
  total_applicants       every parsed resume
  awaiting_screening     parsed but not yet scored (incl. scoring failures)
  awaiting_review        scored, recruiter has not shortlisted them yet
  shortlisted            recruiter-confirmed shortlist (flag)
  scheduled              interview slots currently booked (free_slots = unbooked slots that have not started yet)
  pending_identity       OPEN identity-review items
  completed_interviews   interview finished (assessed, awaiting decision, or decided)
  awaiting_decision      assessed, recruiter decision not yet recorded
Funnel counts are cumulative ('reached at least this stage')."""
from sqlalchemy import select

from app.db import Application, Job, ReviewItem, Slot

RANK = {"PARSED": 0, "SCORING_FAILED": 0, "SCORED": 1, "SHORTLISTED": 2, "SCHEDULED": 3, "HUMAN_REVIEW": 3,
        "REJECTED_AT_REVIEW": 3, "IDENTITY_PASSED": 4, "INTERVIEW_IN_PROGRESS": 5, "INTERVIEW_COMPLETE": 6,
        "ASSESSMENT_FAILED": 6, "ASSESSED": 7, "DECIDED": 8}
COMPLETED = ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED", "ASSESSED", "DECIDED")


def build_overview(jobs: list, apps: list, booked_slots: int, free_slots: int, open_reviews: int) -> dict:
    """apps: dicts with keys id, job_id, status, shortlisted."""
    st = lambda *names: sum(1 for a in apps if a["status"] in names)
    m = {
        "active_jobs": len(jobs),
        "total_applicants": len(apps),
        "awaiting_screening": st("PARSED", "SCORING_FAILED"),
        "scoring_failed": st("SCORING_FAILED"),
        "awaiting_review": sum(1 for a in apps if a["status"] == "SCORED" and not a["shortlisted"]),
        "shortlisted": sum(1 for a in apps if a["shortlisted"]),
        "awaiting_scheduling": st("SHORTLISTED"),
        "scheduled": booked_slots,
        "free_slots": free_slots,
        "pending_identity": open_reviews,
        "interviews_in_progress": st("INTERVIEW_IN_PROGRESS"),
        "completed_interviews": st(*COMPLETED),
        "awaiting_decision": st("ASSESSED"),
        "assessment_failed": st("ASSESSMENT_FAILED"),
        "decided": st("DECIDED"),
    }
    funnel = [
        {"stage": "Uploaded", "count": len(apps)},
        {"stage": "Scored", "count": sum(1 for a in apps if RANK.get(a["status"], 0) >= 1)},
        {"stage": "Shortlisted", "count": sum(1 for a in apps if RANK.get(a["status"], 0) >= 2)},
        {"stage": "Scheduled", "count": sum(1 for a in apps if RANK.get(a["status"], 0) >= 3)},
        {"stage": "Interviewed", "count": sum(1 for a in apps if RANK.get(a["status"], 0) >= 6)},
        {"stage": "Decided", "count": m["decided"]},
    ]
    actions = []

    def add(key, count, label, page, tone):
        if count:
            actions.append({"key": key, "count": count, "label": label, "page": page, "tone": tone})

    if not jobs:
        actions.append({"key": "create_job", "count": 0, "label": "Create your first job to get started", "page": "Jobs", "tone": "info"})
    if jobs and not apps:
        actions.append({"key": "upload", "count": 0, "label": "No resumes uploaded yet - add candidates to start screening", "page": "Candidates", "tone": "info"})
    add("identity", m["pending_identity"], f"{m['pending_identity']} identity review(s) are blocking interviews", "Identity Review", "error")
    add("failed_assessment", m["assessment_failed"], f"{m['assessment_failed']} assessment(s) failed and can be retried", "Reports & Decisions", "error")
    add("screen", m["awaiting_screening"], f"{m['awaiting_screening']} resume(s) are waiting to be scored", "Candidates", "warning")
    add("shortlist", m["awaiting_review"], f"{m['awaiting_review']} scored candidate(s) are waiting for a shortlist decision", "Shortlist & Scheduling", "warning")
    add("schedule", m["awaiting_scheduling"], f"{m['awaiting_scheduling']} shortlisted candidate(s) still need an interview slot", "Shortlist & Scheduling", "warning")
    add("decide", m["awaiting_decision"], f"{m['awaiting_decision']} report(s) are waiting for your hiring decision", "Reports & Decisions", "info")
    if m["interviews_in_progress"]:
        add("live", m["interviews_in_progress"], f"{m['interviews_in_progress']} interview(s) are in progress right now", "Reports & Decisions", "info")
    return {"metrics": m, "funnel": funnel, "pending_actions": actions, "next_action": actions[0] if actions else None}


def compute_overview(db, now=None) -> dict:
    from datetime import datetime
    now = now or datetime.now()
    jobs = db.execute(select(Job)).scalars().all()
    apps = [{"id": a.id, "job_id": a.job_id, "status": a.status, "shortlisted": a.shortlisted}
            for a in db.execute(select(Application)).scalars()]
    slots = db.execute(select(Slot)).scalars().all()
    booked = sum(1 for s in slots if s.application_id is not None)
    free_future = sum(1 for s in slots if s.application_id is None and s.start >= now)
    open_reviews = len(db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all())
    out = build_overview(jobs, apps, booked, free_future, open_reviews)
    per_job = []
    for j in jobs:
        ja = [a for a in apps if a["job_id"] == j.id]
        per_job.append({"job_id": j.id, "title": j.title, "applicants": len(ja),
                        "scored": sum(1 for a in ja if RANK.get(a["status"], 0) >= 1),
                        "shortlisted": sum(1 for a in ja if a["shortlisted"]),
                        "completed": sum(1 for a in ja if a["status"] in COMPLETED)})
    out["per_job"] = per_job
    return out
