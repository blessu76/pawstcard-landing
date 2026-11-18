import datetime as dt
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import iris_review_evidence as ire  # noqa: E402
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


class IrisEvidenceGate(unittest.TestCase):
    """Stamp + Iris's sidecar evidence (<queue>/reviews/<slug>.iris.json, sha256 of the text without the stamp lines)."""

    def run_pub(self, s, **kw):
        lines = []
        rc = pj.run(s.root, NOW, out=lines.append, slot_gates=kw.pop("slot_gates", True), **kw)
        return rc, "\n".join(lines)

    def lint_errors(self, s):
        posts, errors = bj.load_posts(s.root)
        self.assertEqual(errors, [])
        return bj.lint(posts, NOW.astimezone(dt.timezone.utc), s.root)[0]

    def evidence(self, s, slug):
        return s.root / "journal" / "queue" / "reviews" / (slug + ".iris.json")

    def test_a_stamp_only_without_evidence_is_held(self):
        s = Site(self)
        s.post("a", DUE, pub=None, evidence=False)  # stamped, no review evidence
        rc, out = self.run_pub(s)
        self.assertEqual(rc, 0)
        self.assertIn("no Iris review evidence", out)
        self.assertIn("unreviewed: 1", out)
        self.assertFalse(s.exists("journal/posts/a.md"))
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 3)
        self.assertIn("no Iris review evidence", out)
        self.assertIn("no Iris review evidence", self.lint_errors(s)[0])

    def test_b_matching_evidence_passes(self):
        s = Site(self)
        s.post("a", DUE, pub=None)  # Site.post writes the evidence for the text as it is
        self.assertTrue(self.evidence(s, "a").is_file())
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a", out)
        self.assertTrue(s.exists("journal/posts/a.md"))
        self.assertEqual(bj.load_posts(s.root)[1], [])

    def test_c_body_edited_after_review_is_stale(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        path = s.root / "journal" / "queue" / "a.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nAn added sentence after review.\n", encoding="utf-8")
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 3)
        self.assertIn("review evidence stale (manuscript changed after review)", out)
        self.assertFalse(s.exists("journal/posts/a.md"))
        self.assertIn("review evidence stale", self.lint_errors(s)[0])

    def test_d_reviewer_other_than_iris_is_held(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        rec = json.loads(self.evidence(s, "a").read_text(encoding="utf-8"))
        rec["reviewer"] = "bob"
        self.evidence(s, "a").write_text(json.dumps(rec), encoding="utf-8")
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 3)
        self.assertIn("names reviewer 'bob'", out)
        self.assertFalse(s.exists("journal/posts/a.md"))

    def test_e_published_post_is_grandfathered(self):
        s = Site(self)
        s.post("old", "2026-10-01T07:00-04:00", copy_review=None, copy_review_date=None)  # published_at, no stamp, no evidence
        self.assertEqual(self.lint_errors(s), [])
        rc, out = self.run_pub(s)
        self.assertEqual(rc, 0)
        self.assertIn("unreviewed: 0", out)
        self.assertNotIn("held:", out)

    def test_stamp_lines_do_not_change_the_hash(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        path = s.root / "journal" / "queue" / "a.md"
        with_stamp = bj.manuscript_sha256(path)
        path.write_text("".join(ln for ln in path.read_text(encoding="utf-8").splitlines(True)
                                if not ln.startswith(("copy_review:", "copy_review_date:"))), encoding="utf-8")
        self.assertEqual(bj.manuscript_sha256(path), with_stamp)
        self.assertEqual(bj.evidence_problem(path), None)

    def test_evidence_path_keeps_the_language_of_a_translation(self):
        self.assertEqual(bj.evidence_path(Path("/q/my-post.es.md")), Path("/q/reviews/my-post.es.iris.json"))
        self.assertEqual(bj.evidence_path(Path("/q/my-post.md")), Path("/q/reviews/my-post.iris.json"))

    def test_cli_writes_evidence_and_the_gate_passes(self):
        s = Site(self)
        s.post("a", DUE, pub=None, evidence=False)
        self.assertEqual(ire.main([str(s.root / "journal" / "queue" / "a.md"), "--note", "review/a.md"]), 0)
        self.assertEqual(json.loads(self.evidence(s, "a").read_text(encoding="utf-8"))["reviewer"], "iris")
        rc, out = self.run_pub(s, slug="a")
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a", out)

    def test_cli_refuses_without_note_and_for_published(self):
        s = Site(self)
        s.post("a", DUE, pub=None, evidence=False)
        self.assertEqual(ire.main([str(s.root / "journal" / "queue" / "a.md"), "--note", " "]), 2)
        self.assertFalse(self.evidence(s, "a").exists())
        s.post("old", "2026-10-01T07:00-04:00", copy_review=None, copy_review_date=None)
        self.assertEqual(ire.main([str(s.root / "journal" / "queue" / "old.md"), "--note", "x"]), 3)
        self.assertFalse((s.root / "journal" / "queue" / "reviews" / "old.iris.json").exists())


if __name__ == "__main__":
    unittest.main()
