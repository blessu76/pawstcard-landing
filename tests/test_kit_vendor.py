"""vendor/ipe_web_kit is an untouched copy of one kit tag (network- and token-free):  python3 -m unittest discover -s tests -v"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


class KitVendor(unittest.TestCase):
    def test_kit_untouched(self):
        r = subprocess.run([sys.executable, "vendor/ipe_web_kit/vendor.py", "verify", "."], capture_output=True, text=True, cwd=str(REPO))
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
