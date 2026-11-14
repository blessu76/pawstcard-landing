import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import publish_journal as pj  # noqa: E402
from test_build_journal import Site  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 11, 14, 14, 30, tzinfo=KST)  # inside the slot window
DUE = "2026-11-13T07:00-05:00"


class CopyReviewGate(unittest.TestCase):
    def run_pub(self, s, **kw):
        lines = []
        rc = pj.run(s.root, NOW, out=lines.append, slot_gates=kw.pop("slot_gates", True), **kw)
        return rc, "\n".join(lines)

    def test_unreviewed_is_held_exit_0_and_counted(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review=None, copy_review_date=None)
        rc, out = self.run_pub(s)
        self.assertEqual(rc, 0)
        self.assertIn("held:", out)
        self.assertIn("copy review missing", out)
        self.assertIn("unreviewed: 1", out)
        self.assertIn("newly published: —", out)
        self.assertFalse(s.exists("journal/posts/a.md"))

    def test_held_even_without_slot_gates(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review=None, copy_review_date=None)
        rc, out = self.run_pub(s, slot_gates=False)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: —", out)
        self.assertFalse(s.exists("journal/posts/a.md"))

    def test_reviewed_passes(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        rc, out = self.run_pub(s)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a", out)
        self.assertIn("unreviewed: 0", out)
        self.assertTrue(s.exists("journal/posts/a.md"))

    def test_unreviewed_is_skipped_and_the_reviewed_one_goes(self):
        s = Site(self)
        s.post("old", "2026-11-12T07:00-05:00", pub=None, copy_review=None, copy_review_date=None)
        s.post("new", DUE, pub=None)
        rc, out = self.run_pub(s)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: new", out)
        self.assertIn("held:            old (copy review missing", out)
        self.assertIn("unreviewed: 1", out)

    def test_slug_refused_exit_3(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review=None, copy_review_date=None)
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 3)
        self.assertIn("REFUSED", out)
        self.assertFalse(s.exists("journal/posts/a.md"))

    def test_bad_date_format_is_held(self):
        for bad in ("2026/11/13", "11-13-2026", "2026-13-40", "2026-11-13T09:00"):
            s = Site(self)
            s.post("a", DUE, pub=None, copy_review_date=bad)
            rc, out = self.run_pub(s, slug="a")
            self.assertEqual(rc, 3, bad)
            self.assertIn("copy_review_date", out)

    def test_wrong_reviewer_or_missing_date_is_held(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review="bob")
        self.assertEqual(self.run_pub(s, slug="a")[0], 3)
        s = Site(self)
        s.post("b", DUE, pub=None, copy_review_date=None)
        self.assertEqual(self.run_pub(s, slug="b")[0], 3)
        s = Site(self)
        s.post("c", DUE, pub=None, copy_review=None)
        self.assertEqual(self.run_pub(s, slug="c")[0], 3)


class CopyReviewLint(unittest.TestCase):
    def lint(self, s):
        posts, errors = bj.load_posts(s.root)
        self.assertEqual(errors, [])
        return bj.lint(posts, NOW.astimezone(dt.timezone.utc), s.root)[0]

    def test_unpublished_without_review_fails(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review=None, copy_review_date=None)
        errs = self.lint(s)
        self.assertEqual(len(errs), 1)
        self.assertIn("copy review missing", errs[0])

    def test_unpublished_with_review_ok(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        self.assertEqual(self.lint(s), [])

    def test_published_posts_are_grandfathered(self):
        s = Site(self)
        s.post("old", "2026-10-01T07:00-04:00", copy_review=None, copy_review_date=None)  # stamped published_at, no review
        self.assertEqual(self.lint(s), [])

    def test_drafts_are_not_checked(self):
        s = Site(self)
        s.post("d", DUE, pub=None, copy_review=None, copy_review_date=None, draft="true")
        self.assertEqual(self.lint(s), [])

    def test_bad_date_fails_lint(self):
        s = Site(self)
        s.post("a", DUE, pub=None, copy_review_date="2026-02-30")
        self.assertIn("copy_review_date", self.lint(s)[0])


if __name__ == "__main__":
    unittest.main()
