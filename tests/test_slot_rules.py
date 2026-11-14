import datetime as dt
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import publish_journal as pj  # noqa: E402
import schedule_slot as ss  # noqa: E402
import slot_rules as sr  # noqa: E402
from test_build_journal import Site  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))


def k(y, mo, d, h, mi=0):
    return dt.datetime(y, mo, d, h, mi, tzinfo=KST).astimezone(dt.timezone.utc)


def pubs(*stamps):
    return sorted(stamps)


class Gates(unittest.TestCase):
    def test_window(self):
        self.assertIsNone(sr.check(k(2026, 11, 14, 12, 0), []))
        self.assertIsNone(sr.check(k(2026, 11, 14, 17, 59), []))
        self.assertIn("not in window", sr.check(k(2026, 11, 14, 11, 59), []))
        self.assertIn("not in window", sr.check(k(2026, 11, 14, 18, 0), []))
        self.assertIn("not in window", sr.check(k(2026, 11, 14, 4, 39), []))

    def test_one_per_kst_day(self):
        self.assertIn("already published today", sr.check(k(2026, 11, 14, 15), pubs(k(2026, 11, 14, 12, 30))))
        self.assertIsNone(sr.check(k(2026, 11, 15, 15), pubs(k(2026, 11, 14, 12, 30))))

    def test_hour_differs_from_previous(self):
        self.assertIn("same hour", sr.check(k(2026, 11, 15, 13, 5), pubs(k(2026, 11, 14, 13, 40))))
        self.assertIsNone(sr.check(k(2026, 11, 15, 14, 5), pubs(k(2026, 11, 14, 13, 40))))

    def test_previous_is_the_latest_not_an_older_one(self):
        self.assertIsNone(sr.check(k(2026, 11, 16, 13), pubs(k(2026, 11, 14, 13), k(2026, 11, 15, 16))))

    def test_next_eligible(self):
        # published today at 13:10 -> tomorrow 12:00 (hour 12 != 13)
        self.assertEqual(sr.next_eligible(k(2026, 11, 14, 14), pubs(k(2026, 11, 14, 13, 10))), k(2026, 11, 15, 12))
        # yesterday 12:xx, now today 11:00 -> 13:00 (hour 12 is the previous post's)
        self.assertEqual(sr.next_eligible(k(2026, 11, 15, 11), pubs(k(2026, 11, 14, 12, 5))), k(2026, 11, 15, 13))
        # inside the window and allowed: now
        self.assertEqual(sr.next_eligible(k(2026, 11, 15, 14, 22), pubs(k(2026, 11, 14, 12, 5))), k(2026, 11, 15, 14, 22))
        # after the window -> next day 12:00
        self.assertEqual(sr.next_eligible(k(2026, 11, 14, 18, 30), []), k(2026, 11, 15, 12))
        # floor in the future wins; last post hour 12 -> floor at 12:30 is blocked until 13:00
        self.assertEqual(sr.next_eligible(k(2026, 11, 20, 12, 30), pubs(k(2026, 11, 14, 12))), k(2026, 11, 20, 13))


class PublishRun(unittest.TestCase):
    def run_pub(self, s, now, **kw):
        lines = []
        rc = pj.run(s.root, now, out=lines.append, slot_gates=True, **kw)
        return rc, "\n".join(lines)

    def test_out_of_window_is_held_exit_0(self):
        s = Site(self)
        s.post("a", "2026-11-13T07:00-05:00", pub=None)
        rc, out = self.run_pub(s, k(2026, 11, 14, 4, 39))  # the real-world 11-13 case: 04:39 KST
        self.assertEqual(rc, 0)
        self.assertIn("held:", out)
        self.assertIn("not in window", out)
        self.assertIn("newly published: —", out)
        self.assertFalse(s.exists("journal/posts/a.md"))

    def test_in_window_publishes_exactly_one_per_run(self):
        s = Site(self)
        s.post("a", "2026-11-12T07:00-05:00", pub=None)
        s.post("b", "2026-11-12T08:00-05:00", pub=None)
        rc, out = self.run_pub(s, k(2026, 11, 14, 13, 5))
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a", out)
        self.assertTrue(s.exists("journal/posts/a.md"))
        self.assertFalse(s.exists("journal/posts/b.md"))
        self.assertIn("max 1 post per day", out)

    def test_second_run_same_day_is_held(self):
        s = Site(self)
        s.post("a", "2026-11-12T07:00-05:00", pub=None)
        s.post("b", "2026-11-12T08:00-05:00", pub=None)
        self.run_pub(s, k(2026, 11, 14, 13, 5))
        rc, out = self.run_pub(s, k(2026, 11, 14, 15, 0))
        self.assertEqual(rc, 0)
        self.assertIn("already published today", out)
        self.assertFalse(s.exists("journal/posts/b.md"))
        rc, out = self.run_pub(s, k(2026, 11, 15, 13, 5))  # next day, same hour 13 as a -> held
        self.assertIn("same hour slot", out)
        rc, out = self.run_pub(s, k(2026, 11, 15, 14, 0))
        self.assertIn("newly published: b", out)

    def test_slug_refused_when_gated(self):
        s = Site(self)
        s.post("a", "2026-11-12T07:00-05:00", pub=None)
        rc, out = self.run_pub(s, k(2026, 11, 14, 4, 39), slug="a")
        self.assertEqual(rc, 3)
        self.assertIn("REFUSED", out)

    def test_report_depth_and_next_eligible(self):
        s = Site(self)
        s.post("a", "2026-11-12T07:00-05:00", pub=None)
        rc, out = self.run_pub(s, k(2026, 11, 14, 4, 39), dry_run=True)
        self.assertIn("queue depth: 1 (min 3)", out)
        self.assertIn("WARN: queue depth 1 is below 3", out)
        self.assertIn("next eligible publish: 2026-11-14T12:00+09:00 (a)", out)

    def test_empty_queue_next_eligible(self):
        s = Site(self)
        s.post("old", "2026-11-12T22:30-05:00", pub="2026-11-13T13:20+09:00")
        rc, out = self.run_pub(s, k(2026, 11, 13, 21, 24), dry_run=True)
        self.assertIn("queue depth: 0 (min 3)", out)
        self.assertIn("next eligible publish: 2026-11-14T12:00+09:00", out)

    def test_no_warn_at_depth_3(self):
        s = Site(self)
        for i, slug in enumerate("abc"):
            s.post(slug, "2026-11-2%dT00:30-05:00" % i, pub=None)
        rc, out = self.run_pub(s, k(2026, 11, 14, 4, 0), dry_run=True)
        self.assertIn("queue depth: 3 (min 3)", out)
        self.assertNotIn("WARN: queue depth", out)
        self.assertIn("next eligible publish: 2026-11-20T14:30+09:00 (a)", out)

    def test_lint_warns_off_window_floor(self):
        s = Site(self)
        s.post("a", "2026-11-14T07:30-05:00", pub=None)  # 21:30 KST
        posts, _ = bj.load_posts(s.root, None)
        _, warnings = bj.lint(posts, k(2026, 11, 14, 4), s.root)
        self.assertTrue(any("outside the 12:00-17:59 slot" in w for w in warnings))


class Schedule(unittest.TestCase):
    def test_random_slots_obey_rules_and_dst(self):
        rng = random.Random(1)
        last = k(2026, 10, 30, 14, 10)
        now = k(2026, 10, 29, 9)
        for _ in range(200):
            slot = ss.pick_slot(last, now, rng)
            kk = bj.kst(slot)
            self.assertEqual(kk.date(), dt.date(2026, 10, 31))
            self.assertIn(kk.hour, sr.SLOT_HOURS)
            self.assertNotEqual(kk.hour, 14)
            last = k(2026, 10, 30, 14, 10)
        # chain across the 2026-11-01 DST end: ET offset flips from -04:00 to -05:00 and round-trips through parse_stamp
        seen = set()
        last = k(2026, 10, 30, 14)
        for _ in range(6):
            slot = ss.pick_slot(last, now, rng)
            s = bj.et_stamp_str(slot)
            self.assertEqual(bj.parse_stamp(s), slot)
            seen.add(s[-6:])
            self.assertNotEqual(bj.kst(slot).hour, bj.kst(last).hour)
            self.assertEqual((bj.kst(slot).date() - bj.kst(last).date()).days, 1)
            last = slot
        self.assertEqual(seen, {"-04:00", "-05:00"})

    def test_after_and_never_past(self):
        rng = random.Random(2)
        slot = ss.pick_slot(None, k(2026, 11, 14, 9), rng, after=dt.date(2026, 11, 20))
        self.assertEqual(bj.kst(slot).date(), dt.date(2026, 11, 21))
        slot = ss.pick_slot(k(2026, 11, 1, 13), k(2026, 11, 14, 9), rng)
        self.assertEqual(bj.kst(slot).date(), dt.date(2026, 11, 15))

    def test_cli_prints_et_offset(self):
        s = Site(self)
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ss.main(["--root", str(s.root), "--queue", str(s.root / "journal" / "queue"), "--now", "2026-11-14T09:00+09:00", "--after", "2026-11-20", "--seed", "3"])
        self.assertEqual(rc, 0)
        self.assertRegex(buf.getvalue(), r"^publish_at: 2026-11-2\dT\d\d:\d\d-05:00   # KST 2026-11-21T1[2-7]:\d\d\+09:00")


if __name__ == "__main__":
    unittest.main()
