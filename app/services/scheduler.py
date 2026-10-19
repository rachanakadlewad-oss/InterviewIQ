"""Interview slot allocation with double-booking prevention.

Guarantees (see tests/test_scheduler.py):
  * a slot can be taken by only one application - the UPDATE is an atomic compare-and-set
    (`WHERE application_id IS NULL`), so two concurrent requests cannot both win;
  * an application holds at most one slot - UNIQUE(slots.application_id);
  * no two bookings on the same resource overlap in time (checked before booking);
  * past slots are never offered (unless `now` is injected, for tests)."""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import Application, Job, Slot
from app.services.slotlogic import overlaps, select_slot  # noqa: F401  (re-exported)
from app.services.state_machine import transition

log = logging.getLogger(__name__)


def load_calendar(db, path, now: Optional[datetime] = None) -> int:
    """Load mock calendar JSON {"slots":[{slot_id,resource,start,end}]}. Existing slots (and bookings) are kept.
    If `now` is given, slots that already ended are skipped (a stale calendar file must not look like free capacity)."""
    data = json.loads(Path(path).read_text())
    added = 0
    for s in data["slots"]:
        if now and datetime.fromisoformat(s["end"]) < now:
            continue
        if db.get(Slot, s["slot_id"]) is None:
            db.add(Slot(id=s["slot_id"], resource=s.get("resource", "AI-Room-1"),
                        start=datetime.fromisoformat(s["start"]), end=datetime.fromisoformat(s["end"])))
            added += 1
    db.commit()
    return added


def generate_slots(db, now: Optional[datetime] = None, working_days: int = 5, resources=("AI-Room-1", "AI-Room-2"),
                   hours=(10, 11, 14, 15), minutes: int = 45) -> int:
    """Ensure interview slots exist for the next `working_days` weekdays (starting tomorrow). Idempotent: slot ids are
    deterministic, so calling it twice never duplicates slots or touches existing bookings."""
    from datetime import timedelta
    day = ((now or datetime.now()) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    produced = added = 0
    while produced < working_days:
        if day.weekday() < 5:
            for res in resources:
                for h in hours:
                    sid = f"G{day:%Y%m%d}-{res.rsplit('-', 1)[-1]}-{h:02d}"
                    if db.get(Slot, sid) is None:
                        start = day.replace(hour=h)
                        db.add(Slot(id=sid, resource=res, start=start, end=start + timedelta(minutes=minutes)))
                        added += 1
            produced += 1
        day += timedelta(days=1)
    db.commit()
    return added


def book_slot(db, slot_id: str, application_id: int) -> bool:
    """Atomic compare-and-set. Returns False if the slot is gone or the application already holds a slot."""
    try:
        res = db.execute(update(Slot).where(Slot.id == slot_id, Slot.application_id.is_(None))
                         .values(application_id=application_id))
        if res.rowcount != 1:
            db.rollback()
            return False
        db.commit()
        return True
    except IntegrityError:          # UNIQUE(application_id): application already has a slot
        db.rollback()
        return False


def slot_of(db, application_id: int) -> Optional[Slot]:
    return db.execute(select(Slot).where(Slot.application_id == application_id)).scalar_one_or_none()


def release_booking(db, application_id: int) -> bool:
    res = db.execute(update(Slot).where(Slot.application_id == application_id).values(application_id=None))
    db.commit()
    return res.rowcount > 0


def assign_slot(db, application_id: int, now: Optional[datetime] = None, max_tries: int = 5) -> Optional[Slot]:
    if slot_of(db, application_id):
        return slot_of(db, application_id)
    for _ in range(max_tries):
        free = db.execute(select(Slot).where(Slot.application_id.is_(None))).scalars().all()
        booked = db.execute(select(Slot).where(Slot.application_id.is_not(None))).scalars().all()
        s = select_slot(free, booked, now)
        if s is None:
            return None
        if book_slot(db, s.id, application_id):
            return s
        log.info("slot %s was taken concurrently; retrying", s.id)
    return None


def write_confirmation(settings, app: Application, job: Job, slot: Slot) -> dict:
    """Confirmation + notification artifacts (JSON + plain-text e-mail). Nothing is actually e-mailed."""
    d = settings.subdir("confirmations")
    conf = {"application_id": app.id, "candidate": app.candidate_name, "email": app.email, "job": job.title,
            "slot_id": slot.id, "resource": slot.resource, "start": slot.start.isoformat(), "end": slot.end.isoformat(),
            "access_token": app.access_token,
            "instructions": "Open the Candidate Portal, enter your access token, complete the identity check, then start the interview.",
            "notification": "ARTIFACT ONLY - no e-mail was sent (no SMTP configured)."}
    (d / f"confirmation_{app.id}.json").write_text(json.dumps(conf, indent=2))
    (d / f"email_{app.id}.txt").write_text(
        f"To: {app.email}\nSubject: Interview confirmation - {job.title}\n\nHello {app.candidate_name},\n\n"
        f"Your AI interview is scheduled for {slot.start:%A %d %B %Y, %H:%M} - {slot.end:%H:%M} ({slot.resource}).\n"
        f"Your access token: {app.access_token}\nYou must pass an identity check (webcam) before the interview starts.\n")
    return conf


def schedule_shortlisted(db, settings, job: Job, now: Optional[datetime] = None) -> List[dict]:
    apps = db.execute(select(Application).where(Application.job_id == job.id, Application.shortlisted.is_(True))
                      .order_by(Application.rank, Application.id)).scalars().all()
    out = []
    for a in apps:
        if a.status not in ("SHORTLISTED", "SCHEDULED"):
            continue
        s = assign_slot(db, a.id, now)
        if s is None:
            out.append({"application_id": a.id, "scheduled": False, "reason": "no free slot available"})
            continue
        if a.status == "SHORTLISTED":
            transition(a, "SCHEDULED")
            db.commit()
        out.append({"application_id": a.id, "scheduled": True, **write_confirmation(settings, a, job, s)})
    return out
