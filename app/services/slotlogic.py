"""Pure (dependency-free) slot-selection rules used by the scheduler."""
from datetime import datetime
from typing import Iterable, Optional


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start < b_end and b_start < a_end


def select_slot(free: Iterable, booked: Iterable, now: Optional[datetime] = None):
    """Earliest free slot that is not in the past and does not overlap a booked slot on the same resource."""
    booked = list(booked)
    for s in sorted(free, key=lambda s: (s.start, s.id)):
        if now and s.start < now:
            continue
        if any(b.resource == s.resource and overlaps(s.start, s.end, b.start, b.end) for b in booked):
            continue
        return s
    return None
