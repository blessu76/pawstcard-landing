"""Common SEO guide v1 (company-ops 2026-10-29) checks against the REAL files in this repo.  python3 -m unittest discover -s tests"""
import datetime as dt
import json
import re
import sys
import unittest
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


if __name__ == "__main__":
    unittest.main()
