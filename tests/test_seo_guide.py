"""Common SEO guide v1 (company-ops 2026-10-29) checks against the REAL files in this repo.  python3 -m unittest discover -s tests"""
import datetime as dt
import json
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import build_journal as bj  # noqa: E402

LD_RE = re.compile(r'<script type="application/ld\+json">\s*(.*?)\s*</script>', re.S)
POST_PAGES = sorted((REPO / "journal" / "en").glob("*/index.html"))


def ld_blocks(html):
    return [json.loads(b.replace("<\\/", "</")) for b in LD_RE.findall(html)]  # every block must parse


def parse_iso(s):
    d = dt.datetime.fromisoformat(s)
    assert d.tzinfo is not None, "date without offset: " + s
    return d


class BlogPostingJsonLd(unittest.TestCase):
    """P0-8: every published post carries a complete BlogPosting + BreadcrumbList, one publisher (ipe() @id), no future dates."""
    REQUIRED = ("headline", "description", "datePublished", "dateModified", "inLanguage", "url", "mainEntityOfPage",
                "image", "author", "publisher")

    def test_there_are_published_posts(self):
        self.assertGreaterEqual(len(POST_PAGES), 1)

    def test_every_post_has_the_complete_blogposting(self):
        now = dt.datetime.now(dt.timezone.utc)
        for page in POST_PAGES:
            html = page.read_text(encoding="utf-8")
            by_type = {b["@type"]: b for b in ld_blocks(html)}
            post = by_type["BlogPosting"]
            slug = page.parent.name
            url = "%s/journal/en/%s/" % (bj.SITE, slug)
            for key in self.REQUIRED:
                self.assertTrue(post.get(key), "%s: BlogPosting.%s missing" % (slug, key))
            self.assertEqual(post["url"], url, slug)
            self.assertEqual(post["mainEntityOfPage"], {"@type": "WebPage", "@id": url}, slug)
            self.assertEqual(post["inLanguage"], "en", slug)
            self.assertEqual(post["image"]["@type"], "ImageObject", slug)
            self.assertTrue(post["image"]["url"].startswith("https://"), slug)
            title = re.search(r"<title>(.*?)</title>", html).group(1).replace("&amp;", "&")
            self.assertIn(post["headline"].replace("&amp;", "&"), title, slug)  # headline is a part of <title>
            pub, mod = parse_iso(post["datePublished"]), parse_iso(post["dateModified"])
            self.assertLessEqual(pub, mod, slug)
            self.assertLessEqual(mod, now, "%s: dateModified is in the future" % slug)
            for node in (post["author"], post["publisher"]):
                self.assertEqual(node["@id"], bj.ORG_ID, slug)
                self.assertEqual(node["name"], "ipe()", slug)
            logo = post["publisher"]["logo"]
            self.assertEqual(logo["@type"], "ImageObject", slug)
            self.assertTrue(logo["url"].startswith("https://"), slug)

    def test_every_post_has_a_breadcrumb_ending_at_itself(self):
        for page in POST_PAGES:
            slug = page.parent.name
            crumb = {b["@type"]: b for b in ld_blocks(page.read_text(encoding="utf-8"))}["BreadcrumbList"]
            items = crumb["itemListElement"]
            self.assertEqual([i["position"] for i in items], list(range(1, len(items) + 1)), slug)
            self.assertEqual(items[0]["item"], bj.SITE + "/", slug)
            self.assertEqual(items[1]["item"], bj.SITE + "/journal/", slug)
            self.assertEqual(items[-1]["item"], "%s/journal/en/%s/" % (bj.SITE, slug), slug)

    def test_no_future_date_anywhere_in_the_generated_json_ld(self):
        now = dt.datetime.now(dt.timezone.utc)
        pages = [REPO / "index.html", REPO / "journal" / "index.html"] + POST_PAGES
        for page in pages:
            for m in re.finditer(r'"(?:datePublished|dateModified|dateCreated)":\s*"([^"]+)"', page.read_text(encoding="utf-8")):
                if re.match(r"\d{4}-\d{2}-\d{2}T", m.group(1)):
                    self.assertLessEqual(parse_iso(m.group(1)), now, "%s: %s" % (page.relative_to(REPO), m.group(1)))


class Sitemap(unittest.TestCase):
    """P0-4: every indexable URL is listed, each maps to a real file (= 200 on Pages), no duplicates, lastmod == dateModified."""
    NS = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    @classmethod
    def setUpClass(cls):
        root = ET.parse(REPO / "sitemap.xml").getroot()
        cls.entries = {u.find("s:loc", cls.NS).text.strip(): u.find("s:lastmod", cls.NS).text.strip() for u in root.findall("s:url", cls.NS)}
        cls.locs = [u.find("s:loc", cls.NS).text.strip() for u in root.findall("s:url", cls.NS)]

    @staticmethod
    def file_of(url):
        path = url[len(bj.SITE):]
        return REPO / (path.lstrip("/") + "index.html" if path.endswith("/") else path.lstrip("/"))

    def test_no_duplicates_and_all_absolute_https_on_the_site_host(self):
        self.assertEqual(len(self.locs), len(set(self.locs)))
        for loc in self.locs:
            self.assertTrue(loc.startswith(bj.SITE + "/"), loc)

    def test_every_url_has_a_file_so_pages_answers_200(self):
        for loc in self.locs:
            self.assertTrue(self.file_of(loc).is_file(), loc)

    def test_every_indexable_page_is_listed_and_the_404_is_not(self):
        expected = {bj.SITE + "/", bj.SITE + "/journal/"} | {"%s/journal/en/%s/" % (bj.SITE, p.parent.name) for p in POST_PAGES}
        self.assertEqual(set(self.locs), expected)
        self.assertNotIn("404", " ".join(self.locs))

    def test_post_lastmod_equals_json_ld_date_modified(self):
        for page in POST_PAGES:
            url = "%s/journal/en/%s/" % (bj.SITE, page.parent.name)
            post = {b["@type"]: b for b in ld_blocks(page.read_text(encoding="utf-8"))}["BlogPosting"]
            self.assertEqual(parse_iso(self.entries[url]), parse_iso(post["dateModified"]), url)

    def test_home_and_list_lastmod_follow_the_newest_post_and_nothing_is_in_the_future(self):
        newest = max(parse_iso(v) for k, v in self.entries.items() if "/journal/en/" in k)
        self.assertEqual(parse_iso(self.entries[bj.SITE + "/"]), newest)
        self.assertEqual(parse_iso(self.entries[bj.SITE + "/journal/"]), newest)
        now = dt.datetime.now(dt.timezone.utc)
        for url, last in self.entries.items():
            self.assertLessEqual(parse_iso(last), now, url)

    def test_robots_txt_points_at_the_sitemap(self):
        lines = (REPO / "robots.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual([l for l in lines if l.lower().startswith("sitemap:")], ["Sitemap: " + bj.SITE + "/sitemap.xml"])


class GeneratedFilesInSync(unittest.TestCase):
    """The committed generated files are exactly what the generator makes from journal/posts/ (a stale commit fails here)."""

    def test_rebuild_changes_nothing(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        for name in ("index.html", "sitemap.xml", "llms.txt"):
            shutil.copy(REPO / name, tmp / name)
        shutil.copytree(REPO / "journal", tmp / "journal")
        bj.build(tmp, dt.datetime.now(dt.timezone.utc), queue_dir=tmp / "no-queue")
        stale = [str(p.relative_to(REPO)) for p in sorted((REPO / "journal").rglob("*"))
                 if p.is_file() and p.name != "feed.xml" and p.read_bytes() != (tmp / p.relative_to(REPO)).read_bytes()]
        stale += [n for n in ("index.html", "sitemap.xml", "llms.txt") if (REPO / n).read_bytes() != (tmp / n).read_bytes()]
        self.assertEqual(stale, [], "run scripts/build_journal.py and commit the result")


if __name__ == "__main__":
    unittest.main()
