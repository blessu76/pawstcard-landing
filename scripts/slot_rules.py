#!/usr/bin/env python3
"""Publish-slot rules for the Pawstcard journal (shared by publish_journal.py, build_journal.py --check and schedule_slot.py).

A post may go live only when ALL hold (publish_at stays a floor; these are additional gates, evaluated in KST):
  1. the real KST clock is inside the window 12:00-17:59            (SLOT_HOURS)
  2. no post has been published yet on that KST calendar day       (max 1 per day, by published_at date)
  3. that KST hour differs from the hour of the previous (latest) published post
"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402

SLOT_HOURS = tuple(range(12, 18))  # KST 12:00-17:59
MIN_DEPTH = 3


def kst_day(d):
    return bj.kst(d).date()


def published_instants(posts):
    return sorted(p["_pub"] for p in posts if p["_pub"] is not None and not p["draft"])


def check(now, published):
    """-> None when `now` may publish, else the reason (a short English sentence). published = sorted instants."""
    k = bj.kst(now)
    if k.hour not in SLOT_HOURS:
        return "not in window (KST %s, window is %02d:00-%02d:59)" % (k.strftime("%H:%M"), SLOT_HOURS[0], SLOT_HOURS[-1])
    if any(kst_day(t) == k.date() for t in published):
        return "already published today (KST %s)" % k.date()
    if published and bj.kst(published[-1]).hour == k.hour:
        return "same hour slot as the previous post (KST hour %02d, published %s)" % (k.hour, bj.stamp_str(published[-1]))
    return None


def next_eligible(floor, published):
    """Earliest instant >= floor (UTC datetime) that passes check(). floor = max(now, publish_at of the next manuscript)."""
    if floor.second or floor.microsecond:  # whole minutes only
        floor = floor.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    last_hour = bj.kst(published[-1]).hour if published else None
    day = bj.kst(floor).date()
    for _ in range(400):
        if not any(kst_day(t) == day for t in published):
            for h in SLOT_HOURS:
                if h == last_hour:
                    continue
                start = dt.datetime(day.year, day.month, day.day, h, 0, tzinfo=bj.OUT_TZ).astimezone(dt.timezone.utc)
                end = start + dt.timedelta(hours=1)
                if end > floor:
                    return max(start, floor)
        day += dt.timedelta(days=1)
    raise RuntimeError("no eligible slot found")


def queue(posts):
    """unpublished, non-draft manuscripts, oldest publish_at first"""
    return sorted((p for p in posts if p["_pub"] is None and not p["draft"]), key=lambda p: (p["_at"], p["slug"]))


def report(posts, now):
    """-> list of report lines: queue depth (+ warning) and the next eligible publish time."""
    q, pub = queue(posts), published_instants(posts)
    lines = ["queue depth: %d (min %d)" % (len(q), MIN_DEPTH)]
    if len(q) < MIN_DEPTH:
        lines.append("WARN: queue depth %d is below %d — refill the queue (python3 scripts/schedule_slot.py)" % (len(q), MIN_DEPTH))
    floor = max(now, q[0]["_at"]) if q else now
    nxt = next_eligible(floor, pub)
    lines.append("next eligible publish: %s%s" % (bj.stamp_str(nxt), " (%s)" % q[0]["slug"] if q else " (queue empty: the earliest slot a new manuscript could take)"))
    return lines


def pick(posts, now, published=None):
    """-> (post to publish now or None, held list of (slug, reason)). At most one: the oldest due manuscript."""
    pub = published_instants(posts) if published is None else published
    due = [p for p in queue(posts) if p["_at"] <= now]
    if not due:
        return None, []
    why = check(now, pub)
    if why:
        return None, [(p["slug"], why) for p in due]
    return due[0], [(p["slug"], "waits for a later day (max 1 post per day)") for p in due[1:]]


def warn_manuscripts(posts):
    """lint warnings for queued manuscripts whose publish_at is likely to be gated (publish_at is only a floor, never an error)"""
    out, days = [], {}
    for p in queue(posts):
        k = bj.kst(p["_at"])
        if k.hour not in SLOT_HOURS:
            out.append("%s: publish_at %s = KST %s is outside the %02d:00-%02d:59 slot (it will wait for the next window; use scripts/schedule_slot.py)" % (p["_src"], p["publish_at"], k.strftime("%H:%M"), SLOT_HOURS[0], SLOT_HOURS[-1]))
        days.setdefault(k.date(), []).append(p["_src"])
    out += ["%s share the KST day %s (max 1 post per day)" % (", ".join(n), d) for d, n in sorted(days.items()) if len(n) > 1]
    return out
