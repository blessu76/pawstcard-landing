import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_legal as bl  # noqa: E402


class BuildLegalTest(unittest.TestCase):
    def test_generated_pages_are_current(self):
        self.assertEqual(bl.build(ROOT, check_only=True), [])

    def test_sources_carry_no_internal_text(self):
        for slug, *_ in bl.PAGES:
            src = (ROOT / "legal" / (slug + ".md")).read_text(encoding="utf-8")
            self.assertEqual(bl.internal_problems(src), [], slug)

    def test_open_questions_are_highlighted_not_removed(self):
        src = (ROOT / "legal" / "privacy.md").read_text(encoding="utf-8")
        page = bl.render_page("privacy", "Privacy Policy", "Privacy Policy — Pawstcard", "d", src, "0")
        self.assertIn('<mark class="confirm">[confirm P1:', page)
        self.assertEqual(page.count('<mark class="confirm">'), src.count("[confirm"))

    def test_draft_banner_and_english_only_page(self):
        src = (ROOT / "legal" / "terms.md").read_text(encoding="utf-8")
        page = bl.render_page("terms", "Terms of Use", "Terms of Use — Pawstcard", "d", src, "0")
        self.assertIn("DRAFT — not legally reviewed.", page)
        self.assertIsNone(bl.INTERNAL_RE.search(page.split("<main", 1)[1].split("<footer", 1)[0]))

    def test_tables_render_inside_scroll_wrapper(self):
        page = bl.render_page("privacy", "Privacy Policy", "Privacy Policy — Pawstcard", "d",
                              "## T\n\n| A | B |\n|---|---|\n| 1 | 2 |\n", "0")
        self.assertIn('<div class="table-wrap"><table>', page)


if __name__ == "__main__":
    unittest.main()
