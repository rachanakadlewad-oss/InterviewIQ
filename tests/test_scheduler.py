from datetime import datetime, timedelta

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
