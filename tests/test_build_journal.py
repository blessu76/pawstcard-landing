"""Green gate for the journal build:  python3 -m unittest discover -s tests -v"""
import datetime as dt
import io
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402
import publish_journal as pj  # noqa: E402

ET = bj.TZ  # publish_at floors are Eastern Time; everything recorded/shown is KST (+09:00)
SEED_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://pawstcard.ipe.rest/</loc>
    <lastmod>2026-07-18</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
SEED_LLMS = """# Pawstcard

> Landing blurb.

## Key facts
- Name: Pawstcard

## Usage
Cite as Pawstcard.
"""


def md(slug, at, **extra):
    fm = {"slug": slug, "title": "Title of %s" % slug, "description": "About %s." % slug, "publish_at": at}
    fm.update(extra)
    return "---\n" + "\n".join("%s: %s" % kv for kv in fm.items()) + "\n---\n\n# Heading\n\nBody of **%s** with a [link](https://example.com/x).\n" % slug


class Site:
    """A throwaway site root: seeded sitemap/llms/css + queue manuscripts."""

    def __init__(self, tc):
        self.root = Path(tempfile.mkdtemp())
        tc.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "sitemap.xml").write_text(SEED_SITEMAP, encoding="utf-8")
        (self.root / "llms.txt").write_text(SEED_LLMS, encoding="utf-8")
        (self.root / "journal" / "queue").mkdir(parents=True)
        (self.root / "journal" / "assets").mkdir()
        shutil.copy(REPO / "journal" / "assets" / "journal.css", self.root / "journal" / "assets" / "journal.css")

    def post(self, slug, at, pub="same", **extra):
        """pub="same": already published at `at`; pub=None: unstamped manuscript (publish_journal.py will stamp it)."""
        if pub == "same":
            try:
                extra.setdefault("published_at", bj.stamp_str(bj.parse_stamp(at)))  # same instant, written the KST way
            except ValueError:  # deliberately malformed publish_at (validation tests)
                pass
        elif pub:
            extra["published_at"] = pub
        (self.root / "journal" / "queue" / (slug + ".md")).write_text(md(slug, at, **extra), encoding="utf-8")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def exists(self, rel):
        return (self.root / rel).exists()


NOW = dt.datetime(2026, 10, 25, 14, 0, tzinfo=ET)


class FutureGate(unittest.TestCase):
    def test_future_post_is_not_built_anywhere(self):
        s = Site(self)
        s.post("due-now", "2026-10-25T14:00-04:00")
        s.post("tomorrow", "2026-10-26T07:00-04:00")
        rep = bj.build(s.root, NOW)
        self.assertEqual(rep["due"], ["due-now"])
        self.assertEqual(rep["waiting"], [("tomorrow", "2026-10-26T07:00-04:00")])
        self.assertTrue(s.exists("journal/en/due-now/index.html"))
        self.assertFalse(s.exists("journal/en/tomorrow/index.html"))
        for rel in ("journal/index.html", "journal/feed.xml", "sitemap.xml", "llms.txt"):
            self.assertNotIn("tomorrow", s.read(rel), rel)

    def test_one_minute_early_is_future(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:01-04:00")
        self.assertEqual(bj.build(s.root, NOW)["due"], [])

    def test_clock_in_another_offset_is_compared_correctly(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00-04:00")  # == 18:00 UTC == 03:00 KST next day
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-10-25T17:59+00:00"))["due"], [])
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-10-25T18:00Z"))["due"], ["x"])
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-10-26T03:00+09:00"))["due"], ["x"])

    def test_draft_never_published(self):
        s = Site(self)
        s.post("d", "2026-10-01T07:00-04:00", draft="true")
        self.assertEqual(bj.build(s.root, NOW)["due"], [])
        self.assertFalse(s.exists("journal/en/d/index.html"))

    def test_page_removed_when_post_is_pushed_back_to_the_future(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00-04:00")
        bj.build(s.root, NOW)
        self.assertTrue(s.exists("journal/en/x/index.html"))
        s.post("x", "2026-10-30T07:00-04:00")
        bj.build(s.root, NOW)
        self.assertFalse(s.exists("journal/en/x/index.html"))
        self.assertNotIn("/journal/en/x/", s.read("sitemap.xml"))

    def test_publish_script_refuses_future_slug(self):
        s = Site(self)
        s.post("later", "2026-10-26T07:00-04:00", pub=None)
        buf = []
        code = pj.run(s.root, NOW, slug="later", out=buf.append)
        self.assertEqual(code, 3)
        self.assertIn("REFUSED", buf[0])
        self.assertFalse(s.exists("journal/index.html"), "nothing may be written on refusal")

    def test_publish_script_publishes_due_slug_and_skips_future_ones(self):
        s = Site(self)
        s.post("now", "2026-10-25T07:00-04:00", pub=None)
        s.post("later", "2026-10-26T07:00-04:00", pub=None)
        buf = []
        self.assertEqual(pj.run(s.root, NOW, slug="now", out=buf.append), 0)
        self.assertTrue(s.exists("journal/en/now/index.html"))
        self.assertFalse(s.exists("journal/en/later/index.html"))
        self.assertIn("now", buf[1])

    def test_publish_script_unknown_slug_and_dry_run(self):
        s = Site(self)
        s.post("now", "2026-10-25T07:00-04:00", pub=None)
        self.assertEqual(pj.run(s.root, NOW, slug="nope", out=lambda m: None), 2)
        self.assertEqual(pj.run(s.root, NOW, dry_run=True, out=lambda m: None), 0)
        self.assertFalse(s.exists("journal/index.html"))


class ActualPublishTime(unittest.TestCase):
    """publish_at is a floor; the page shows the real publish_journal.py run time."""

    def test_due_but_unstamped_post_is_not_live(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00-04:00", pub=None)
        rep = bj.build(s.root, NOW)
        self.assertEqual(rep["due"], [])
        self.assertEqual(rep["ready"], ["x"])
        self.assertFalse(s.exists("journal/en/x/index.html"))

    def test_actual_time_everywhere_not_publish_at(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00-04:00", pub=None)
        now = dt.datetime(2026, 10, 25, 14, 13, 41, tzinfo=ET)
        self.assertEqual(pj.run(s.root, now, out=lambda m: None), 0)
        self.assertIn("published_at: 2026-10-26T03:13+09:00", s.read("journal/queue/x.md"))
        page = s.read("journal/en/x/index.html")
        self.assertIn('"datePublished": "2026-10-26T03:13:00+09:00"', page)
        self.assertIn('"dateModified": "2026-10-26T03:13:00+09:00"', page)
        self.assertIn("Oct 26, 2026, 03:13 KST", page)
        self.assertIn("2026-10-26T03:13:00+09:00", page)
        self.assertNotIn("14:00", page.split("</head>")[1])
        self.assertIn("Oct 26, 2026, 03:13 KST", s.read("journal/index.html"))
        self.assertIn("<pubDate>Mon, 26 Oct 2026 03:13:00 +0900</pubDate>", s.read("journal/feed.xml"))
        self.assertIn("<lastmod>2026-10-26T03:13:00+09:00</lastmod>", s.read("sitemap.xml"))
        self.assertIn("(2026-10-26)", s.read("llms.txt"))

    def test_lastmod_follows_actual_date_when_it_slips_past_midnight(self):
        s = Site(self)
        s.post("x", "2026-10-25T23:00-04:00", pub=None)
        pj.run(s.root, dt.datetime(2026, 10, 26, 0, 20, tzinfo=ET), out=lambda m: None)
        self.assertIn("<lastmod>2026-10-26T13:20:00+09:00</lastmod>", s.read("sitemap.xml"))

    def test_stamp_only_touches_front_matter(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00-04:00", pub=None)
        before = s.read("journal/queue/x.md")
        pj.run(s.root, NOW, out=lambda m: None)
        after = s.read("journal/queue/x.md")
        self.assertEqual(after.replace("published_at: 2026-10-26T03:00+09:00\n", "", 1), before)

    def test_republish_keeps_first_stamp(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00-04:00", pub=None)
        pj.run(s.root, dt.datetime(2026, 10, 25, 14, 13, tzinfo=ET), out=lambda m: None)
        first = s.read("journal/queue/x.md")
        pj.run(s.root, dt.datetime(2026, 10, 25, 18, 2, tzinfo=ET), out=lambda m: None)
        self.assertEqual(first, s.read("journal/queue/x.md"))
        self.assertIn("2026-10-26T03:13:00+09:00", s.read("journal/en/x/index.html"))

    def test_slug_run_stamps_only_that_post(self):
        s = Site(self)
        s.post("a", "2026-10-25T07:00-04:00", pub=None)
        s.post("b", "2026-10-25T07:00-04:00", pub=None)
        pj.run(s.root, NOW, slug="a", out=lambda m: None)
        self.assertTrue(s.exists("journal/en/a/index.html"))
        self.assertFalse(s.exists("journal/en/b/index.html"))
        self.assertNotIn("published_at", s.read("journal/queue/b.md"))

    def test_dry_run_and_refusal_do_not_stamp(self):
        s = Site(self)
        s.post("a", "2026-10-25T07:00-04:00", pub=None)
        s.post("f", "2026-10-30T07:00-04:00", pub=None)
        before = {n: s.read("journal/queue/%s.md" % n) for n in "af"}
        pj.run(s.root, NOW, dry_run=True, out=lambda m: None)
        pj.run(s.root, NOW, slug="f", out=lambda m: None)
        self.assertEqual(before, {n: s.read("journal/queue/%s.md" % n) for n in "af"})

    def test_run_without_slug_never_stamps_future_post(self):
        s = Site(self)
        s.post("a", "2026-10-25T07:00-04:00", pub=None)
        s.post("f", "2026-10-26T07:00-04:00", pub=None)
        pj.run(s.root, NOW, out=lambda m: None)
        self.assertNotIn("published_at", s.read("journal/queue/f.md"))
        self.assertFalse(s.exists("journal/en/f/index.html"))

    def test_published_at_before_publish_at_is_rejected(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00-04:00", published_at="2026-10-26T02:59+09:00")
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        self.assertIn("published_at is earlier", str(cm.exception))

    def test_published_at_after_now_hidden(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00-04:00", published_at="2026-10-26T04:00+09:00")
        self.assertEqual(bj.build(s.root, NOW)["due"], [])


class EasternTime(unittest.TestCase):
    """publish_at floors are America/New_York: offsets are derived and verified, never trusted. Recorded times are KST."""

    def test_offset_must_match_eastern_rules(self):
        self.assertEqual(bj.et_stamp_str(bj.parse_stamp("2026-10-25T07:13-04:00")), "2026-10-25T07:13-04:00")
        self.assertEqual(bj.et_stamp_str(bj.parse_stamp("2026-11-02T07:13-05:00")), "2026-11-02T07:13-05:00")
        self.assertEqual(bj.stamp_str(bj.parse_stamp("2026-10-25T07:13-04:00")), "2026-10-25T20:13+09:00")  # = KST
        for bad in ("2026-11-02T07:13-04:00", "2026-10-25T07:13-05:00", "2026-10-25T07:13+09:00"):
            with self.assertRaises(ValueError, msg=bad):
                bj.parse_stamp(bad)

    def test_dst_boundary_2026_11_01(self):
        # EDT ends 2026-11-01 02:00 EDT -> 01:00 EST. Before: -04:00, after: -05:00.
        before = bj.parse_stamp("2026-11-01T00:30-04:00")
        after = bj.parse_stamp("2026-11-01T02:30-05:00")
        self.assertEqual((after - before).total_seconds(), 3 * 3600)  # 00:30 EDT -> 02:30 EST = 3h of real time (not the 2h a wall-clock subtraction gives)
        # the repeated hour exists twice and both offsets are valid there
        first, second = bj.parse_stamp("2026-11-01T01:30-04:00"), bj.parse_stamp("2026-11-01T01:30-05:00")
        self.assertEqual((second - first).total_seconds(), 3600)
        # wall-clock times with the wrong side's offset are rejected
        with self.assertRaises(ValueError):
            bj.parse_stamp("2026-11-01T02:30-04:00")
        with self.assertRaises(ValueError):
            bj.parse_stamp("2026-11-01T00:30-05:00")

    def test_comparisons_use_real_instants_in_the_repeated_hour(self):
        s = Site(self)
        s.post("x", "2026-11-01T01:30-04:00", pub=None)  # floor = 05:30Z
        # 01:10 EST (06:10Z) is later than the floor in real time even though the wall clock (01:10) reads earlier
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-11-01T01:10-05:00"))["ready"], ["x"])
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-11-01T01:29-04:00"))["ready"], [])

    def test_spring_forward_gap_does_not_exist(self):
        with self.assertRaises(ValueError):
            bj.parse_stamp("2026-03-08T02:30-05:00")
        bj.parse_stamp("2026-03-08T03:30-04:00")

    def test_stamp_after_dst_switch_uses_est_offset(self):
        s = Site(self)
        s.post("x", "2026-10-31T07:13-04:00", pub=None)
        now = bj.parse_now("2026-11-02T12:20:30Z")  # = 07:20 EST
        pj.run(s.root, now, out=lambda m: None)
        self.assertIn("published_at: 2026-11-02T21:20+09:00", s.read("journal/queue/x.md"))
        page = s.read("journal/en/x/index.html")
        self.assertIn('"datePublished": "2026-11-02T21:20:00+09:00"', page)
        self.assertIn("Nov 2, 2026, 21:20 KST", page)

    def test_stamp_across_the_boundary_day(self):
        s = Site(self)
        s.post("x", "2026-11-01T01:30-04:00", pub=None)
        now = bj.parse_now("2026-11-01T06:45:00Z")  # 01:45 EST, second pass through the 01:00 hour
        pj.run(s.root, now, out=lambda m: None)
        self.assertIn("published_at: 2026-11-01T15:45+09:00", s.read("journal/queue/x.md"))

    def test_run_before_floor_is_refused_in_eastern_terms(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:13-04:00", pub=None)
        early = bj.parse_now("2026-10-25T11:12:59Z")  # 07:12:59 EDT
        self.assertEqual(pj.run(s.root, early, slug="x", out=lambda m: None), 3)
        self.assertNotIn("published_at", s.read("journal/queue/x.md"))
        self.assertFalse(s.exists("journal/en/x/index.html"))
        pj.run(s.root, early, out=lambda m: None)  # without --slug: skipped, not stamped
        self.assertNotIn("published_at", s.read("journal/queue/x.md"))
        self.assertEqual(pj.run(s.root, bj.parse_now("2026-10-25T11:13:00Z"), slug="x", out=lambda m: None), 0)
        self.assertIn("published_at: 2026-10-25T20:13+09:00", s.read("journal/queue/x.md"))

    def test_kst_record_static_kst_text_and_device_time_hook(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:13-04:00")
        bj.build(s.root, NOW)
        page, lst = s.read("journal/en/x/index.html"), s.read("journal/index.html")
        want = '<time datetime="2026-10-25T20:13:00+09:00" data-localize>Oct 25, 2026, 20:13 KST</time>'
        for text in (page, lst):
            self.assertIn(want, text)  # recorded in KST, static text HH:MM KST, hook for the device time zone
            self.assertIn("Intl.DateTimeFormat", text)
            self.assertIn("hourCycle: 'h23'", text)
            self.assertIn("'Asia/Seoul': 'KST'", text)
            self.assertNotIn("-04:00", text)  # no Eastern time anywhere in what is recorded/shown
        for text in (page, lst, s.read("journal/feed.xml"), s.read("sitemap.xml")):
            self.assertNotIn("-0400", text)

    def test_recorded_times_must_be_kst(self):
        for bad in ("2026-10-25T07:13-04:00", "2026-10-25T20:13Z", "2026-10-25T20:13+08:00", "2026-10-25T20:13:00+09:00", "2026-10-25"):
            with self.assertRaises(ValueError, msg=bad):
                bj.parse_kst_stamp(bad)
        self.assertEqual(bj.parse_kst_stamp("2026-10-25T20:13+09:00"), bj.parse_stamp("2026-10-25T07:13-04:00"))


class FrontMatter(unittest.TestCase):
    def build_err(self, **kw):
        s = Site(self)
        s.post(kw.pop("slug", "p"), kw.pop("at", "2026-10-25T07:00-04:00"), **kw)
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        return "\n".join(cm.exception.errors)

    def test_publish_at_must_be_eastern_stamp(self):
        for bad in ("2026-10-25", "2026-10-25 07:00", "2026-10-25T07:00:00-04:00", "2026-10-25T07:00Z", "2026-10-25T07:00+00:00", "2026-10-25T07:00+09:00", "2026-13-40T07:00-04:00", "2026-11-02T07:00-04:00", "2026-10-25T07:00-05:00"):
            self.assertIn("publish_at", self.build_err(at=bad), bad)

    def test_missing_fields_and_bad_slug(self):
        s = Site(self)
        (s.root / "journal/queue/p.md").write_text("---\nslug: p\ntitle: T\n---\nbody\n", encoding="utf-8")
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        self.assertIn("description", str(cm.exception))
        self.assertIn("publish_at", str(cm.exception))
        self.assertIn("slug must match", self.build_err(slug="Bad_Slug"))

    def test_filename_must_match_slug_and_reserved_slug(self):
        s = Site(self)
        (s.root / "journal/queue/a.md").write_text(md("b", "2026-10-25T07:00-04:00"), encoding="utf-8")
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        self.assertIn("file name must be", str(cm.exception))
        self.assertIn("reserved", self.build_err(slug="feed"))

    def test_future_manuscripts_are_still_validated(self):
        s = Site(self)
        s.post("ok", "2026-10-25T07:00-04:00")
        (s.root / "journal/queue/bad.md").write_text("no front matter", encoding="utf-8")
        with self.assertRaises(bj.JournalError):
            bj.build(s.root, NOW)

    def test_description_max_155(self):
        self.assertIn("155", self.build_err(description="x" * 156))
        s = Site(self)
        s.post("ok155", "2026-10-25T07:00-04:00", description="x" * 155)
        bj.build(s.root, NOW)

    def test_tags_list_becomes_keywords(self):
        s = Site(self)
        s.post("t", "2026-10-25T07:00-04:00", tags="[pet sitting, visit reports, dog walking]")
        bj.build(s.root, NOW)
        page = s.read("journal/en/t/index.html")
        self.assertIn('"keywords": "pet sitting, visit reports, dog walking"', page)
        self.assertIn('<meta property="article:tag" content="visit reports">', page)
        s.post("k", "2026-10-25T07:00-04:00", keywords="a, b")  # alias still works
        bj.build(s.root, NOW)
        self.assertIn('"keywords": "a, b"', s.read("journal/en/k/index.html"))

    def test_colon_in_title_survives(self):
        s = Site(self)
        s.post("c", "2026-10-25T07:00-04:00", title="Rover vs Wag: which pays more?")
        bj.build(s.root, NOW)
        self.assertIn("Rover vs Wag: which pays more?", s.read("journal/en/c/index.html"))


class SitemapMerge(unittest.TestCase):
    def test_landing_entry_preserved_and_journal_added(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00-04:00")
        s.post("b", "2026-10-25T07:00-04:00", updated="2026-10-25T22:00+09:00")
        bj.build(s.root, NOW)
        sm = s.read("sitemap.xml")
        self.assertIn(SEED_SITEMAP.split("</urlset>")[0].split("<urlset")[1].split(">", 1)[1], sm)  # landing <url> byte-for-byte
        self.assertIn("<lastmod>2026-07-18</lastmod>", sm)
        for loc in ("https://pawstcard.ipe.rest/", "https://pawstcard.ipe.rest/journal/",
                    "https://pawstcard.ipe.rest/journal/en/a/", "https://pawstcard.ipe.rest/journal/en/b/"):
            self.assertIn("<loc>%s</loc>" % loc, sm)
        self.assertEqual(sm.count("<loc>https://pawstcard.ipe.rest/</loc>"), 1)
        self.assertIn('hreflang="en" href="https://pawstcard.ipe.rest/journal/en/a/"', sm)
        self.assertIn('hreflang="x-default" href="https://pawstcard.ipe.rest/journal/en/a/"', sm)
        self.assertIn("<image:loc>https://pawstcard.ipe.rest/og-image.png</image:loc>", sm)
        self.assertIn('xmlns:xhtml="', sm)
        self.assertIn('xmlns:image="', sm)
        self.assertIn("<lastmod>2026-10-25T22:00:00+09:00</lastmod>", sm)
        import xml.dom.minidom
        xml.dom.minidom.parseString(sm)  # well-formed

    def test_rebuild_is_idempotent_and_grows(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00-04:00")
        s.post("b", "2026-10-26T07:00-04:00")
        bj.build(s.root, NOW)
        first = s.read("sitemap.xml")
        bj.build(s.root, NOW)
        self.assertEqual(first, s.read("sitemap.xml"))
        self.assertEqual(first.count(bj.SM_START), 1)
        bj.build(s.root, dt.datetime(2026, 10, 26, 7, 0, tzinfo=ET))
        self.assertIn("/journal/en/b/", s.read("sitemap.xml"))
        self.assertEqual(s.read("sitemap.xml").count("<loc>https://pawstcard.ipe.rest/journal/</loc>"), 1)

    def test_existing_markers_are_replaced_in_place(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00-04:00")
        seeded = SEED_SITEMAP.replace("</urlset>", "  %s\n  <url><loc>stale</loc></url>\n  %s\n</urlset>" % (bj.SM_START, bj.SM_END))
        (s.root / "sitemap.xml").write_text(seeded, encoding="utf-8")
        bj.build(s.root, NOW)
        sm = s.read("sitemap.xml")
        self.assertNotIn("stale", sm)
        self.assertEqual(sm.count(bj.SM_START), 1)
        self.assertIn("/journal/en/a/", sm)

    def test_no_posts_leaves_no_journal_urls(self):
        s = Site(self)
        bj.build(s.root, NOW)
        self.assertNotIn("/journal/", s.read("sitemap.xml"))
        self.assertIn("https://pawstcard.ipe.rest/</loc>", s.read("sitemap.xml"))


class LlmsTxt(unittest.TestCase):
    def test_journal_block_added_before_usage_and_rest_untouched(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00-04:00")
        bj.build(s.root, NOW)
        t = s.read("llms.txt")
        self.assertTrue(t.startswith(SEED_LLMS.split("## Usage")[0]))  # landing text before the block untouched
        self.assertTrue(t.rstrip().endswith("## Usage\nCite as Pawstcard."))
        self.assertIn("## Journal", t)
        self.assertIn("- [Title of a](https://pawstcard.ipe.rest/journal/en/a/) — About a. (2026-10-24)", t)
        self.assertLess(t.index("## Journal"), t.index("## Usage"))
        self.assertIn("https://pawstcard.ipe.rest/journal/feed.xml", t)

    def test_second_post_appears_and_no_duplicate_block(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00-04:00")
        s.post("b", "2026-10-25T07:00-04:00")
        bj.build(s.root, dt.datetime(2026, 10, 24, 12, 0, tzinfo=ET))
        self.assertNotIn("journal/en/b/", s.read("llms.txt"))
        bj.build(s.root, NOW)
        t = s.read("llms.txt")
        self.assertIn("journal/en/b/", t)
        self.assertIn("journal/en/a/", t)
        self.assertEqual(t.count("## Journal"), 1)
        self.assertEqual(t.count(bj.LLMS_START), 1)
        self.assertLess(t.index("journal/en/b/"), t.index("journal/en/a/"), "newest first")

    def test_appended_when_no_usage_section(self):
        s = Site(self)
        (s.root / "llms.txt").write_text("# Pawstcard\n\n> blurb\n", encoding="utf-8")
        s.post("a", "2026-10-24T07:00-04:00")
        bj.build(s.root, NOW)
        t = s.read("llms.txt")
        self.assertTrue(t.startswith("# Pawstcard\n\n> blurb\n"))
        self.assertIn("## Journal", t)


class Pages(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        self.s.post("a", "2026-10-25T14:00-04:00", category="guides", keywords="pet sitter, report card")
        bj.build(self.s.root, NOW)
        self.post = self.s.read("journal/en/a/index.html")
        self.lst = self.s.read("journal/index.html")

    def ld_types(self, text):
        return re.findall(r'"@type": "(\w+)"', text)

    def test_post_page_seo(self):
        p = self.post
        self.assertIn('<link rel="canonical" href="https://pawstcard.ipe.rest/journal/en/a/">', p)
        self.assertIn('"datePublished": "2026-10-26T03:00:00+09:00"', p)
        self.assertIn('hreflang="x-default"', p)
        self.assertIn("BlogPosting", self.ld_types(p))
        self.assertIn("BreadcrumbList", self.ld_types(p))
        self.assertIn("<h2>Heading</h2>", p)  # body # -> h2
        self.assertEqual(p.count("<h1>"), 1)
        self.assertIn('rel="noopener">link</a>', p)

    def test_post_links_to_landing_waitlist(self):
        self.assertIn('href="/#signup"', self.post)

    def test_analytics_same_as_landing_and_nothing_new(self):
        landing = (REPO / "index.html").read_text(encoding="utf-8")
        for page in (self.post, self.lst):
            self.assertIn("G-XG4BH800J0", page)
            self.assertIn("fbq('init', '1932639057434633')", page)
            self.assertIn("32d73b01c2de4d46a9de77a88952a654", page)
            self.assertNotIn("fbq('track', 'Lead'", page)
        self.assertIn("G-XG4BH800J0", landing)
        self.assertIn("1932639057434633", landing)
        self.assertIn("32d73b01c2de4d46a9de77a88952a654", landing)
        # the set of third-party script hosts must be exactly the landing page's analytics trio (+ fonts)
        hosts = set(re.findall(r'(?:src|href)="https?://([^/"]+)', self.post))
        allowed = {"www.googletagmanager.com", "connect.facebook.net", "www.facebook.com", "static.cloudflareinsights.com",
                   "fonts.googleapis.com", "fonts.gstatic.com", "pawstcard.ipe.rest", "example.com"}  # example.com = the body link in md()
        self.assertLessEqual(hosts, allowed)

    def test_css_cache_busting(self):
        m = re.search(r'/journal/assets/journal\.css\?v=([0-9a-f]{8})"', self.post)
        self.assertTrue(m)
        self.assertEqual(m.group(1), bj.asset_v(self.s.root))
        (self.s.root / "journal/assets/journal.css").write_text("/* changed */", encoding="utf-8")
        bj.build(self.s.root, NOW)
        self.assertNotIn("v=" + m.group(1), self.s.read("journal/en/a/index.html"))

    def test_list_page_and_feed(self):
        self.assertIn("Blog", self.ld_types(self.lst))
        self.assertIn("ItemList", self.ld_types(self.lst))
        self.assertIn('<a href="/journal/en/a/">Title of a</a>', self.lst)
        feed = self.s.read("journal/feed.xml")
        self.assertIn("<link>https://pawstcard.ipe.rest/journal/en/a/</link>", feed)
        self.assertIn("<pubDate>Mon, 26 Oct 2026 03:00:00 +0900</pubDate>", feed)
        import xml.dom.minidom
        xml.dom.minidom.parseString(feed)

    def test_empty_list_is_noindex(self):
        s = Site(self)
        bj.build(s.root, NOW)
        self.assertIn("noindex", s.read("journal/index.html"))

    def test_html_in_manuscript_is_escaped(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00-04:00", title="A <b>bold</b> claim")
        p = s.root / "journal/queue/x.md"
        p.write_text(p.read_text(encoding="utf-8") + "\n<script>alert(1)</script>\n[bad](javascript:alert(1))\n", encoding="utf-8")
        bj.build(s.root, NOW)
        page = s.read("journal/en/x/index.html")
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn("javascript:", page)
        self.assertNotIn("<b>bold</b>", page)


class RepoState(unittest.TestCase):
    """Guards on the real repo files."""

    def test_landing_and_deploy_untouched_markers(self):
        sm = (REPO / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn("<loc>https://pawstcard.ipe.rest/</loc>", sm)
        self.assertTrue((REPO / "CNAME").exists())

    def test_real_manuscripts_validate(self):
        posts, errors = bj.load_posts(REPO)
        self.assertEqual(errors, [])

    def test_landing_links_to_journal_in_footer_only(self):
        landing = (REPO / "index.html").read_text(encoding="utf-8")
        self.assertEqual(landing.count('href="/journal/"'), 1)
        self.assertGreater(landing.index('href="/journal/"'), landing.index("<footer>"))


if __name__ == "__main__":
    unittest.main()
