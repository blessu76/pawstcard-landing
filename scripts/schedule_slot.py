#!/usr/bin/env python3
"""Print the next valid random publish_at for a NEW manuscript (America/New_York offset string, DST-correct).

Rules (see slot_rules.py): KST 12:00-17:59, the day after the last scheduled post, KST hour different from that post's hour.
"Last scheduled" = the latest of every published post and every queued manuscript (publish_at floors), --after, and today.

    python3 scripts/schedule_slot.py                      # after everything already published/queued
    python3 scripts/schedule_slot.py --after 2026-11-20   # not before the day after this KST date
    python3 scripts/schedule_slot.py --count 3 --seed 7   # three consecutive slots (reproducible)
"""
import argparse
import datetime as dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import slot_rules as sr  # noqa: E402


def last_scheduled(posts):
    """latest KST instant already taken: published_at of published posts, publish_at floor of queued ones (None when nothing)"""
    taken = [p["_pub"] or p["_at"] for p in posts if not p["draft"]]
    return max(taken) if taken else None


def pick_slot(last, now, rng, after=None):
    """-> UTC datetime: random minute in a KST 12-17 hour, on the day after `last`, hour != last's hour."""
    day = bj.kst(now).date()  # never schedule into the past: earliest is today if its window can still be met, else tomorrow
    first = day + dt.timedelta(days=1)
    if last is not None:
        first = max(first, bj.kst(last).date() + dt.timedelta(days=1))
    if after is not None:
        first = max(first, after + dt.timedelta(days=1))
    hours = [h for h in sr.SLOT_HOURS if last is None or h != bj.kst(last).hour]
    h, m = rng.choice(hours), rng.randrange(60)
    return dt.datetime(first.year, first.month, first.day, h, m, tzinfo=bj.OUT_TZ).astimezone(dt.timezone.utc)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--queue", default=str(bj.default_queue_dir()))
    ap.add_argument("--after", help="KST date YYYY-MM-DD: schedule on a later day than this")
    ap.add_argument("--now", help="ISO 8601 with offset (default: real clock)")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--seed", type=int)
    a = ap.parse_args(argv)
    try:
        now = bj.parse_now(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
        after = dt.date.fromisoformat(a.after) if a.after else None
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1
    posts, errors = bj.load_posts(Path(a.root).resolve(), a.queue)
    if errors:
        print("journal: errors\n  " + "\n  ".join(errors), file=sys.stderr)
        return 1
    rng = random.Random(a.seed)
    last = last_scheduled(posts)
    for _ in range(max(1, a.count)):
        slot = pick_slot(last, now, rng, after)
        print("publish_at: %s   # KST %s" % (bj.et_stamp_str(slot), bj.stamp_str(slot)))
        last = slot
    return 0


if __name__ == "__main__":
    sys.exit(main())
