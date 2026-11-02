from datetime import datetime, timedelta

from sqlalchemy import delete, select

from app.db import Slot
from app.services import scheduler
from app.services.slotlogic import overlaps, select_slot
from tests.helpers import FUTURE, add_resume, make_job


class S:
    def __init__(self, id, resource, start, mins=45):
        self.id, self.resource, self.start, self.end = id, resource, start, start + timedelta(minutes=mins)


T = datetime(2030, 1, 1, 10, 0)


def test_overlap_rules():
    assert overlaps(T, T + timedelta(minutes=45), T + timedelta(minutes=30), T + timedelta(minutes=75))
    assert not overlaps(T, T + timedelta(minutes=45), T + timedelta(minutes=45), T + timedelta(minutes=90))


def test_select_slot_skips_overlap_same_resource_only():
    booked = [S("b", "R1", T)]
    free = [S("x", "R1", T + timedelta(minutes=15)), S("y", "R2", T + timedelta(minutes=15))]
    assert select_slot(free, booked).id == "y"


def test_select_slot_skips_past():
    free = [S("old", "R1", T - timedelta(days=1)), S("new", "R1", T + timedelta(days=1))]
    assert select_slot(free, [], now=T).id == "new"
    assert select_slot([S("old", "R1", T - timedelta(days=1))], [], now=T) is None


def test_double_booking_is_prevented(db):
    job = make_job(db)
    a, b = add_resume(db, job, "Aarav_Mehta.docx"), add_resume(db, job, "Priya_Nair.pdf")
    slot_id = db.get(Slot, "S001").id
    assert scheduler.book_slot(db, slot_id, a.id) is True
    assert scheduler.book_slot(db, slot_id, b.id) is False          # slot already taken
    assert scheduler.slot_of(db, b.id) is None


def test_application_cannot_hold_two_slots(db):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    assert scheduler.book_slot(db, "S001", a.id) is True
    assert scheduler.book_slot(db, "S002", a.id) is False           # UNIQUE(application_id)


def test_assign_slot_gives_distinct_non_overlapping_slots(db):
    job = make_job(db)
    apps = [add_resume(db, job, f) for f in ("Aarav_Mehta.docx", "Priya_Nair.pdf", "Rohan_Gupta.docx")]
    got = [scheduler.assign_slot(db, a.id, now=FUTURE) for a in apps]
    assert len({s.id for s in got}) == 3
    assert scheduler.assign_slot(db, apps[0].id, now=FUTURE).id == got[0].id   # idempotent


def test_no_slot_available_returns_none(db):
    job = make_job(db)
    from sqlalchemy import update
    a = add_resume(db, job, "Aarav_Mehta.docx")
    assert scheduler.assign_slot(db, a.id, now=datetime(2100, 1, 1)) is None   # all slots in the past


def test_release_frees_slot(db):
    job = make_job(db)
    a, b = add_resume(db, job, "Aarav_Mehta.docx"), add_resume(db, job, "Priya_Nair.pdf")
    scheduler.book_slot(db, "S001", a.id)
    assert scheduler.release_booking(db, a.id) is True
    assert scheduler.book_slot(db, "S001", b.id) is True


def test_confirmation_artifacts_written(db, settings):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    s = scheduler.assign_slot(db, a.id, now=FUTURE)
    conf = scheduler.write_confirmation(settings, a, job, s)
    d = settings.subdir("confirmations")
    assert (d / f"confirmation_{a.id}.json").exists() and (d / f"email_{a.id}.txt").exists()
    assert conf["access_token"] == a.access_token and "no e-mail was sent" in conf["notification"]


def test_generate_slots_is_weekday_only_idempotent_and_non_overlapping(db):
    now = datetime(2026, 10, 15, 9, 0)                          # a Thursday
    n = scheduler.generate_slots(db, now)
    assert n == 5 * 2 * 4                                       # 5 working days x 2 resources x 4 times
    assert scheduler.generate_slots(db, now) == 0               # idempotent
    from sqlalchemy import select
    slots = db.execute(select(Slot)).scalars().all()
    assert all(s.start.weekday() < 5 and s.start > now for s in slots)
    by_res = {}
    for s in slots:
        by_res.setdefault(s.resource, []).append(s)
    for lst in by_res.values():
        lst.sort(key=lambda s: s.start)
        assert all(a.end <= b.start for a, b in zip(lst, lst[1:]))     # no overlaps on a resource


def test_generated_slots_never_disturb_bookings(db):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")
    s = scheduler.assign_slot(db, a.id, now=FUTURE)
    scheduler.generate_slots(db, datetime(2026, 10, 15, 9, 0))
    assert scheduler.slot_of(db, a.id).id == s.id


def test_load_calendar_skips_slots_that_already_ended(db):
    from tests.helpers import SAMPLE
    assert scheduler.load_calendar(db, SAMPLE / "mock_calendar.json", now=datetime(2100, 1, 1)) == 0
    assert scheduler.load_calendar(db, SAMPLE / "mock_calendar.json") > 0


def test_multiple_candidates_competing_for_limited_slots(db, settings):
    job = make_job(db)
    a1 = add_resume(db, job, "Aarav_Mehta.docx")
    a2 = add_resume(db, job, "Priya_Nair.pdf")
    a3 = add_resume(db, job, "Rohan_Gupta.docx")

    # Clear mock slots and add exactly 2 slots
    db.execute(delete(Slot))
    db.commit()
    db.add(Slot(id="TEST-S1", resource="AI-Room-1", start=FUTURE, end=FUTURE + timedelta(minutes=45)))
    db.add(Slot(id="TEST-S2", resource="AI-Room-2", start=FUTURE, end=FUTURE + timedelta(minutes=45)))
    db.commit()

    # Shortlist all three
    for app in (a1, a2, a3):
        app.shortlisted = True
        app.status = "SHORTLISTED"
    db.commit()

    res = scheduler.schedule_shortlisted(db, settings, job, now=FUTURE)
    assert len(res) == 3
    # First two succeed
    assert res[0]["scheduled"] is True and res[0]["application_id"] == a1.id
    assert res[1]["scheduled"] is True and res[1]["application_id"] == a2.id
    # Third fails gracefully due to insufficient availability and remains in SHORTLISTED status
    assert res[2]["scheduled"] is False and "no free slot available" in res[2]["reason"]
    assert a3.status == "SHORTLISTED"

    # Now add another slot and schedule remaining
    db.add(Slot(id="TEST-S3", resource="AI-Room-1", start=FUTURE + timedelta(hours=1), end=FUTURE + timedelta(hours=1, minutes=45)))
    db.commit()
    res2 = scheduler.schedule_shortlisted(db, settings, job, now=FUTURE)
    # a1 and a2 were already scheduled; a3 gets the new slot
    a3_res = next(r for r in res2 if r["application_id"] == a3.id)
    assert a3_res["scheduled"] is True
    assert a3.status == "SCHEDULED"


def test_cannot_book_overlapping_slots_on_same_room(db):
    job = make_job(db)
    a1 = add_resume(db, job, "Aarav_Mehta.docx")
    a2 = add_resume(db, job, "Priya_Nair.pdf")

    # Two overlapping slots on the same room
    s1 = Slot(id="OV-1", resource="AI-Room-1", start=FUTURE, end=FUTURE + timedelta(minutes=60))
    s2 = Slot(id="OV-2", resource="AI-Room-1", start=FUTURE + timedelta(minutes=30), end=FUTURE + timedelta(minutes=90))
    db.add_all([s1, s2])
    db.commit()

    # Book s1 for a1
    assert scheduler.book_slot(db, "OV-1", a1.id) is True
    # Attempt to book overlapping s2 on the same room for a2 must be rejected
    assert scheduler.book_slot(db, "OV-2", a2.id) is False
    assert scheduler.slot_of(db, a2.id) is None


def test_multiple_rooms_at_same_time_can_be_booked_concurrently(db):
    job = make_job(db)
    a1 = add_resume(db, job, "Aarav_Mehta.docx")
    a2 = add_resume(db, job, "Priya_Nair.pdf")

    # Same start time, different rooms
    s1 = Slot(id="MR-1", resource="AI-Room-1", start=FUTURE, end=FUTURE + timedelta(minutes=45))
    s2 = Slot(id="MR-2", resource="AI-Room-2", start=FUTURE, end=FUTURE + timedelta(minutes=45))
    db.add_all([s1, s2])
    db.commit()

    assert scheduler.book_slot(db, "MR-1", a1.id) is True
    assert scheduler.book_slot(db, "MR-2", a2.id) is True
    assert scheduler.slot_of(db, a1.id).resource == "AI-Room-1"
    assert scheduler.slot_of(db, a2.id).resource == "AI-Room-2"


def test_deduplicate_slots_cleans_ghost_duplicates_preserving_booked(db):
    job = make_job(db)
    a = add_resume(db, job, "Aarav_Mehta.docx")

    # Clear mock slots and add duplicate slots for AI-Room-1 at the same time: one booked, one unbooked
    db.execute(delete(Slot))
    db.commit()
    s_booked = Slot(id="DUP-BOOKED", resource="AI-Room-1", start=FUTURE, end=FUTURE + timedelta(minutes=45), application_id=a.id)
    s_ghost = Slot(id="DUP-GHOST", resource="AI-Room-1", start=FUTURE, end=FUTURE + timedelta(minutes=45), application_id=None)
    db.add_all([s_booked, s_ghost])
    db.commit()

    removed = scheduler.deduplicate_slots(db)
    assert removed == 1
    remaining = db.execute(select(Slot).where(Slot.resource == "AI-Room-1")).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].id == "DUP-BOOKED" and remaining[0].application_id == a.id
