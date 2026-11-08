"""Recruiter dashboard metrics, computed from real rows (nothing is fabricated).

Definitions:
  total_jobs             all jobs owned by recruiter
  active_jobs            active job openings
  total_applicants       every application submitted
  shortlisted            recruiter-confirmed shortlist (flag or SHORTLISTED status)
  rejected               rejected applications
  pending                applications waiting for recruiter review or screening
  scheduled              interview slots booked
  completed_interviews   interview finished (assessed, awaiting decision, or decided)
  decided                recruiter hiring decision recorded
"""
from datetime import datetime
from sqlalchemy import select

from app.db import Application, Job, ReviewItem, Slot

RANK = {
    "APPLIED": 0, "PARSED": 0, "SCORING_FAILED": 0, "SCORED": 1, "UNDER_REVIEW": 1,
    "SHORTLISTED": 2, "SCHEDULED": 3, "HUMAN_REVIEW": 3, "REJECTED_AT_REVIEW": 3,
    "REJECTED": 3, "IDENTITY_PASSED": 4, "INTERVIEW_IN_PROGRESS": 5, "INTERVIEW_COMPLETE": 6,
    "ASSESSMENT_FAILED": 6, "ASSESSED": 7, "DECIDED": 8
}
COMPLETED = ("INTERVIEW_COMPLETE", "ASSESSMENT_FAILED", "ASSESSED", "DECIDED")


def build_overview(jobs: list, apps: list, booked_slots: int, free_slots: int, open_reviews: int) -> dict:
    """apps: dicts with keys id, job_id, status, shortlisted, ai_score, candidate_name, etc."""
    st = lambda *names: sum(1 for a in apps if a["status"] in names)
    
    active_jobs_count = sum(1 for j in jobs if getattr(j, "status", "ACTIVE") == "ACTIVE")
    total_shortlisted = sum(1 for a in apps if (a.get("shortlisted") or a.get("status") == "SHORTLISTED") and a.get("status") != "REJECTED")
    total_rejected = sum(1 for a in apps if a.get("status") == "REJECTED")
    total_pending = sum(1 for a in apps if a.get("status") in ("APPLIED", "PARSED", "PENDING_REVIEW", "SCORED", "UNDER_REVIEW", "PENDING") and not a.get("shortlisted") and a.get("status") != "REJECTED")

    m = {
        "total_jobs": len(jobs),
        "active_jobs": active_jobs_count,
        "total_applicants": len(apps),
        "shortlisted": total_shortlisted,
        "rejected": total_rejected,
        "pending": total_pending,
        "awaiting_screening": st("PARSED", "SCORING_FAILED", "APPLIED", "PENDING_REVIEW"),
        "scoring_failed": st("SCORING_FAILED"),
        "awaiting_review": sum(1 for a in apps if a.get("status") in ("SCORED", "UNDER_REVIEW") and not a.get("shortlisted")),
        "awaiting_scheduling": sum(1 for a in apps if a.get("status") == "SHORTLISTED"),
        "scheduled": booked_slots,
        "free_slots": free_slots,
        "pending_identity": open_reviews,
        "interviews_in_progress": st("INTERVIEW_IN_PROGRESS"),
        "completed_interviews": st(*COMPLETED),
        "awaiting_decision": st("ASSESSED"),
        "assessment_failed": st("ASSESSMENT_FAILED"),
        "decided": st("DECIDED"),
    }

    status_distribution = {
        "Shortlisted": total_shortlisted,
        "Pending Review": total_pending,
        "Scheduled": booked_slots,
        "Decided": m["decided"],
        "Rejected": total_rejected,
    }

    funnel = [
        {"stage": "Uploaded", "count": len(apps)},
        {"stage": "Scored", "count": sum(1 for a in apps if RANK.get(a.get("status"), 0) >= 1)},
        {"stage": "Shortlisted", "count": sum(1 for a in apps if RANK.get(a.get("status"), 0) >= 2 and a.get("status") != "REJECTED")},
        {"stage": "Scheduled", "count": sum(1 for a in apps if RANK.get(a.get("status"), 0) >= 3 and a.get("status") != "REJECTED")},
        {"stage": "Interviewed", "count": sum(1 for a in apps if RANK.get(a.get("status"), 0) >= 6 and a.get("status") != "REJECTED")},
        {"stage": "Decided", "count": m["decided"]},
    ]

    actions = []
    def add(key, count, label, page, tone):
        if count:
            actions.append({"key": key, "count": count, "label": label, "page": page, "tone": tone})

    if not jobs:
        actions.append({"key": "create_job", "count": 0, "label": "Create your first job opening to begin", "page": "Jobs", "tone": "info"})
    if jobs and not apps:
        actions.append({"key": "upload", "count": 0, "label": "Add or invite candidates to start screening", "page": "Candidates", "tone": "info"})
    add("identity", m["pending_identity"], f"{m['pending_identity']} identity review(s) are blocking interviews", "Identity Review", "error")
    add("failed_assessment", m["assessment_failed"], f"{m['assessment_failed']} assessment(s) failed and can be retried", "Reports", "error")
    add("screen", m["awaiting_screening"], f"{m['awaiting_screening']} resume(s) are waiting for AI screening", "Candidates", "warning")
    add("shortlist", m["awaiting_review"], f"{m['awaiting_review']} candidate(s) are pending review", "Candidates", "warning")
    add("schedule", m["awaiting_scheduling"], f"{m['awaiting_scheduling']} shortlisted candidate(s) need an interview slot", "Interviews", "warning")
    add("decide", m["awaiting_decision"], f"{m['awaiting_decision']} report(s) are waiting for your hiring decision", "Reports", "info")
    if m["interviews_in_progress"]:
        add("live", m["interviews_in_progress"], f"{m['interviews_in_progress']} interview(s) are in progress right now", "Interviews", "info")

    return {
        "metrics": m,
        "funnel": funnel,
        "status_distribution": status_distribution,
        "actions": actions,
        "pending_actions": actions,
        "next_action": actions[0] if actions else None
    }


def compute_overview(db, user_id=None, now=None) -> dict:
    now = now or datetime.now()
    if user_id:
        jobs = db.execute(select(Job).where((Job.recruiter_id == user_id) | (Job.recruiter_id.is_(None)))).scalars().all()
    else:
        jobs = db.execute(select(Job)).scalars().all()

    job_ids = [j.id for j in jobs]
    job_map = {j.id: j.title for j in jobs}
    company_map = {j.id: getattr(j, "company", "TechCorp") or "TechCorp" for j in jobs}

    q_app = select(Application)
    if job_ids:
        q_app = q_app.where(Application.job_id.in_(job_ids))
    app_rows = db.execute(q_app.order_by(Application.id.desc())).scalars().all()

    apps = [{
        "id": a.id,
        "job_id": a.job_id,
        "candidate_name": a.candidate_name,
        "email": a.email,
        "status": a.status,
        "shortlisted": bool(a.shortlisted),
        "ai_score": a.ai_score if a.ai_score is not None else a.resume_score,
        "resume_score": a.resume_score,
        "created_at": a.created_at
    } for a in app_rows]

    slots = db.execute(select(Slot)).scalars().all()
    booked = sum(1 for s in slots if s.application_id is not None)
    free_future = sum(1 for s in slots if s.application_id is None and s.start >= now)
    open_reviews = len(db.execute(select(ReviewItem).where(ReviewItem.status == "OPEN")).scalars().all())

    out = build_overview(jobs, apps, booked, free_future, open_reviews)

    # Per job summary
    per_job = []
    for j in jobs:
        ja = [a for a in apps if a["job_id"] == j.id]
        per_job.append({
            "job_id": j.id,
            "title": j.title,
            "company": company_map.get(j.id, "TechCorp"),
            "status": getattr(j, "status", "ACTIVE") or "ACTIVE",
            "location": getattr(j, "location", "Remote") or "Remote",
            "experience_level": getattr(j, "experience_level", "Mid-level") or "Mid-level",
            "employment_type": getattr(j, "employment_type", "Full-time") or "Full-time",
            "applicants": len(ja),
            "scored": sum(1 for a in ja if RANK.get(a["status"], 0) >= 1),
            "shortlisted": sum(1 for a in ja if a["shortlisted"] or a["status"] == "SHORTLISTED"),
            "rejected": sum(1 for a in ja if a["status"] == "REJECTED"),
            "completed": sum(1 for a in ja if a["status"] in COMPLETED),
            "created_date": j.created_at.strftime("%b %d, %Y") if getattr(j, "created_at", None) else "-"
        })
    out["per_job"] = per_job

    # Recent applications (latest 8)
    out["recent_applications"] = [{
        "application_id": a["id"],
        "name": a["candidate_name"] or f"Applicant #{a['id']}",
        "email": a["email"] or "-",
        "job_title": job_map.get(a["job_id"], f"Job #{a['job_id']}"),
        "ai_score": a["ai_score"],
        "status": a["status"],
        "shortlisted": a["shortlisted"],
        "applied_date": a["created_at"].strftime("%b %d, %Y %H:%M") if a.get("created_at") else "-"
    } for a in apps[:8]]

    return out
