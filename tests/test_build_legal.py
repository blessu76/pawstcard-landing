import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_legal as bl  # noqa: E402


class BuildLegalTest(unittest.TestCase):
    def test_generated_redirects_are_current(self):
        self.assertEqual(bl.build(ROOT, check_only=True), [])

    def test_sources_carry_no_internal_text(self):
        for slug, *_ in bl.PAGES:
            src = (ROOT / "legal" / (slug + ".md")).read_text(encoding="utf-8")
            self.assertEqual(bl.internal_problems(src), [], slug)

    def test_redirect_points_at_the_ipe_rest_page(self):
        for slug, h1, title, desc in bl.PAGES:
            page = bl.redirect_page(slug, h1, title, desc)
            url = "https://ipe.rest/en/legal/%s/" % slug
            self.assertIn('<meta http-equiv="refresh" content="0; url=%s">' % url, page, slug)
            self.assertIn('<link rel="canonical" href="%s">' % url, page, slug)
            self.assertIn('<meta name="robots" content="noindex,follow">', page, slug)
            self.assertIn('<a href="%s">click here</a>' % url, page, slug)


if __name__ == "__main__":
    unittest.main()
