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


ALL_PAGES = [REPO / "index.html", REPO / "journal" / "index.html"] + POST_PAGES  # every indexable page
SITE_PAGES = ALL_PAGES + [REPO / "404.html"]


def url_of(page):
    rel = page.relative_to(REPO).as_posix()
    return bj.SITE + "/" + rel[: -len("index.html")] if rel.endswith("index.html") else bj.SITE + "/" + rel


def meta(html, pattern):
    m = re.search(pattern, html, re.S)
    return m.group(1) if m else None


class CanonicalAndRobots(unittest.TestCase):
    """P0-5: canonical = the page's own absolute https URL on every indexable page; noindex only on the 404."""

    def test_canonical_is_the_pages_own_absolute_url(self):
        for page in ALL_PAGES:
            html = page.read_text(encoding="utf-8")
            canon = re.findall(r'<link rel="canonical" href="([^"]+)"', html)
            self.assertEqual(canon, [url_of(page)], page.relative_to(REPO))
            self.assertTrue(canon[0].startswith("https://"), page)

    def test_noindex_only_on_the_404(self):
        for page in SITE_PAGES:
            robots = meta(page.read_text(encoding="utf-8"), r'<meta name="robots" content="([^"]+)"')
            if page.name == "404.html":
                self.assertIn("noindex", robots)
            else:
                self.assertTrue(robots is None or "noindex" not in robots, page.relative_to(REPO))

    def test_the_404_has_no_canonical(self):  # one canonical for every unknown URL would be wrong
        self.assertNotIn('rel="canonical"', (REPO / "404.html").read_text(encoding="utf-8"))

    def test_journal_pages_carry_a_self_referencing_hreflang_and_x_default(self):
        for page in POST_PAGES + [REPO / "journal" / "index.html"]:
            html = page.read_text(encoding="utf-8")
            url = url_of(page)
            self.assertIn('<link rel="alternate" hreflang="en" href="%s">' % url, html, page)
            self.assertIn('<link rel="alternate" hreflang="x-default" href="%s">' % url, html, page)


class UniqueMeta(unittest.TestCase):
    """P0-7: unique <title> and description on every page, exactly one <h1>, <html lang>."""

    def pages(self):
        for page in SITE_PAGES:
            yield page, page.read_text(encoding="utf-8")

    def test_titles_are_unique_and_non_empty(self):
        titles = {}
        for page, html in self.pages():
            t = meta(html, r"<title>(.*?)</title>")
            self.assertTrue(t and t.strip(), page)
            titles.setdefault(t, []).append(page.relative_to(REPO).as_posix())
        self.assertEqual({t: v for t, v in titles.items() if len(v) > 1}, {})

    def test_descriptions_are_unique_and_non_empty(self):
        descs = {}
        for page, html in self.pages():
            d = meta(html, r'<meta name="description" content="([^"]*)"')
            self.assertTrue(d and d.strip(), page)
            descs.setdefault(d, []).append(page.relative_to(REPO).as_posix())
        self.assertEqual({d: v for d, v in descs.items() if len(v) > 1}, {})

    def test_exactly_one_h1_and_a_language(self):
        for page, html in self.pages():
            self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, page.relative_to(REPO))
            self.assertRegex(html, r'<html lang="en">', page.relative_to(REPO))

    def test_post_h1_is_the_post_title_and_og_title_matches_the_title_tag(self):
        for page in POST_PAGES:
            html = page.read_text(encoding="utf-8")
            post = {b["@type"]: b for b in ld_blocks(html)}["BlogPosting"]
            h1 = meta(html, r"<h1>(.*?)</h1>")
            self.assertEqual(h1.replace("&amp;", "&"), post["headline"].replace("&amp;", "&"), page)
            self.assertEqual(meta(html, r'<meta property="og:title" content="([^"]*)"'), meta(html, r"<title>(.*?)</title>"), page)


class NotFoundPage(unittest.TestCase):
    """P0-10: GitHub Pages serves /404.html for every unknown URL with HTTP 404 — the file must be there, noindex, with ways back."""

    def test_404_is_a_root_file_noindex_with_home_and_journal_links(self):
        html = (REPO / "404.html").read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex, follow">', html)
        self.assertRegex(html, r'<a [^>]*href="/"')
        self.assertRegex(html, r'<a [^>]*href="/journal/"')

    def test_404_uses_root_absolute_asset_paths_so_it_renders_at_any_depth(self):
        html = (REPO / "404.html").read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"#][^"]*)"', html):
            self.assertTrue(ref.startswith(("/", "https://", "mailto:")), ref)

    def test_404_is_not_in_the_sitemap_or_a_redirect_file(self):
        self.assertNotIn("404", (REPO / "sitemap.xml").read_text(encoding="utf-8"))
        self.assertFalse((REPO / "_redirects").exists())


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
