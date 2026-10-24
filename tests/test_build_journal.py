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

KST = bj.KST
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

    def post(self, slug, at, **extra):
        (self.root / "journal" / "queue" / (slug + ".md")).write_text(md(slug, at, **extra), encoding="utf-8")

    def read(self, rel):
        return (self.root / rel).read_text(encoding="utf-8")

    def exists(self, rel):
        return (self.root / rel).exists()


NOW = dt.datetime(2026, 10, 25, 14, 0, tzinfo=KST)


class FutureGate(unittest.TestCase):
    def test_future_post_is_not_built_anywhere(self):
        s = Site(self)
        s.post("due-now", "2026-10-25T14:00+09:00")
        s.post("tomorrow", "2026-10-26T07:00+09:00")
        rep = bj.build(s.root, NOW)
        self.assertEqual(rep["due"], ["due-now"])
        self.assertEqual(rep["waiting"], [("tomorrow", "2026-10-26T07:00+09:00")])
        self.assertTrue(s.exists("journal/en/due-now/index.html"))
        self.assertFalse(s.exists("journal/en/tomorrow/index.html"))
        for rel in ("journal/index.html", "journal/feed.xml", "sitemap.xml", "llms.txt"):
            self.assertNotIn("tomorrow", s.read(rel), rel)

    def test_one_minute_early_is_future(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:01+09:00")
        self.assertEqual(bj.build(s.root, NOW)["due"], [])

    def test_clock_in_another_offset_is_compared_correctly(self):
        s = Site(self)
        s.post("x", "2026-10-25T14:00+09:00")  # == 05:00 UTC
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-10-25T04:59+00:00"))["due"], [])
        self.assertEqual(bj.build(s.root, bj.parse_now("2026-10-25T05:00Z"))["due"], ["x"])

    def test_draft_never_published(self):
        s = Site(self)
        s.post("d", "2026-10-01T07:00+09:00", draft="true")
        self.assertEqual(bj.build(s.root, NOW)["due"], [])
        self.assertFalse(s.exists("journal/en/d/index.html"))

    def test_page_removed_when_post_is_pushed_back_to_the_future(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00+09:00")
        bj.build(s.root, NOW)
        self.assertTrue(s.exists("journal/en/x/index.html"))
        s.post("x", "2026-10-30T07:00+09:00")
        bj.build(s.root, NOW)
        self.assertFalse(s.exists("journal/en/x/index.html"))
        self.assertNotIn("/journal/en/x/", s.read("sitemap.xml"))

    def test_publish_script_refuses_future_slug(self):
        s = Site(self)
        s.post("later", "2026-10-26T07:00+09:00")
        buf = []
        code = pj.run(s.root, NOW, slug="later", out=buf.append)
        self.assertEqual(code, 3)
        self.assertIn("REFUSED", buf[0])
        self.assertFalse(s.exists("journal/index.html"), "nothing may be written on refusal")

    def test_publish_script_publishes_due_slug_and_skips_future_ones(self):
        s = Site(self)
        s.post("now", "2026-10-25T07:00+09:00")
        s.post("later", "2026-10-26T07:00+09:00")
        buf = []
        self.assertEqual(pj.run(s.root, NOW, slug="now", out=buf.append), 0)
        self.assertTrue(s.exists("journal/en/now/index.html"))
        self.assertFalse(s.exists("journal/en/later/index.html"))
        self.assertIn("now", buf[1])

    def test_publish_script_unknown_slug_and_dry_run(self):
        s = Site(self)
        s.post("now", "2026-10-25T07:00+09:00")
        self.assertEqual(pj.run(s.root, NOW, slug="nope", out=lambda m: None), 2)
        self.assertEqual(pj.run(s.root, NOW, dry_run=True, out=lambda m: None), 0)
        self.assertFalse(s.exists("journal/index.html"))


class FrontMatter(unittest.TestCase):
    def build_err(self, **kw):
        s = Site(self)
        s.post(kw.pop("slug", "p"), kw.pop("at", "2026-10-25T07:00+09:00"), **kw)
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        return "\n".join(cm.exception.errors)

    def test_publish_at_must_be_kst_stamp(self):
        for bad in ("2026-10-25", "2026-10-25 07:00", "2026-10-25T07:00:00+09:00", "2026-10-25T07:00Z", "2026-10-25T07:00+00:00", "2026-13-40T07:00+09:00"):
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
        (s.root / "journal/queue/a.md").write_text(md("b", "2026-10-25T07:00+09:00"), encoding="utf-8")
        with self.assertRaises(bj.JournalError) as cm:
            bj.build(s.root, NOW)
        self.assertIn("file name must be", str(cm.exception))
        self.assertIn("reserved", self.build_err(slug="feed"))

    def test_future_manuscripts_are_still_validated(self):
        s = Site(self)
        s.post("ok", "2026-10-25T07:00+09:00")
        (s.root / "journal/queue/bad.md").write_text("no front matter", encoding="utf-8")
        with self.assertRaises(bj.JournalError):
            bj.build(s.root, NOW)

    def test_colon_in_title_survives(self):
        s = Site(self)
        s.post("c", "2026-10-25T07:00+09:00", title="Rover vs Wag: which pays more?")
        bj.build(s.root, NOW)
        self.assertIn("Rover vs Wag: which pays more?", s.read("journal/en/c/index.html"))


class SitemapMerge(unittest.TestCase):
    def test_landing_entry_preserved_and_journal_added(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00+09:00")
        s.post("b", "2026-10-25T07:00+09:00", updated="2026-10-25T09:00+09:00")
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
        self.assertIn("<lastmod>2026-10-25</lastmod>", sm)
        import xml.dom.minidom
        xml.dom.minidom.parseString(sm)  # well-formed

    def test_rebuild_is_idempotent_and_grows(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00+09:00")
        s.post("b", "2026-10-26T07:00+09:00")
        bj.build(s.root, NOW)
        first = s.read("sitemap.xml")
        bj.build(s.root, NOW)
        self.assertEqual(first, s.read("sitemap.xml"))
        self.assertEqual(first.count(bj.SM_START), 1)
        bj.build(s.root, dt.datetime(2026, 10, 26, 7, 0, tzinfo=KST))
        self.assertIn("/journal/en/b/", s.read("sitemap.xml"))
        self.assertEqual(s.read("sitemap.xml").count("<loc>https://pawstcard.ipe.rest/journal/</loc>"), 1)

    def test_existing_markers_are_replaced_in_place(self):
        s = Site(self)
        s.post("a", "2026-10-24T07:00+09:00")
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
        s.post("a", "2026-10-24T07:00+09:00")
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
        s.post("a", "2026-10-24T07:00+09:00")
        s.post("b", "2026-10-25T07:00+09:00")
        bj.build(s.root, dt.datetime(2026, 10, 24, 12, 0, tzinfo=KST))
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
        s.post("a", "2026-10-24T07:00+09:00")
        bj.build(s.root, NOW)
        t = s.read("llms.txt")
        self.assertTrue(t.startswith("# Pawstcard\n\n> blurb\n"))
        self.assertIn("## Journal", t)


class Pages(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        self.s.post("a", "2026-10-25T14:00+09:00", category="guides", keywords="pet sitter, report card")
        bj.build(self.s.root, NOW)
        self.post = self.s.read("journal/en/a/index.html")
        self.lst = self.s.read("journal/index.html")

    def ld_types(self, text):
        return re.findall(r'"@type": "(\w+)"', text)

    def test_post_page_seo(self):
        p = self.post
        self.assertIn('<link rel="canonical" href="https://pawstcard.ipe.rest/journal/en/a/">', p)
        self.assertIn('"datePublished": "2026-10-25T14:00:00+09:00"', p)
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
        self.assertIn("<pubDate>Sun, 25 Oct 2026 14:00:00 +0900</pubDate>", feed)
        import xml.dom.minidom
        xml.dom.minidom.parseString(feed)

    def test_empty_list_is_noindex(self):
        s = Site(self)
        bj.build(s.root, NOW)
        self.assertIn("noindex", s.read("journal/index.html"))

    def test_html_in_manuscript_is_escaped(self):
        s = Site(self)
        s.post("x", "2026-10-25T07:00+09:00", title="A <b>bold</b> claim")
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
