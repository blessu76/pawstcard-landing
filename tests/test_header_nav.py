"""Homepage header nav links to the Journal.  python3 -m unittest discover -s tests"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class HomeHeaderNav(unittest.TestCase):
    def test_header_has_journal_link_between_logo_and_cta(self):
        html = (REPO / "index.html").read_text(encoding="utf-8")
        header = re.search(r"<header\b.*?</header>", html, re.S).group(0)
        self.assertRegex(header, r'<a class="nav-journal" href="/journal/">Journal</a>')
        self.assertLess(header.index('class="logo"'), header.index("nav-journal"))
        self.assertLess(header.index("nav-journal"), header.index('class="cta-mini"'))


if __name__ == "__main__":
    unittest.main()
