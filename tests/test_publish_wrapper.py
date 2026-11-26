"""The unattended publisher wrapper must stage Iris evidence and verify the live pages.

publish_journal.py reads <queue>/reviews/<slug>.iris.json. The wrapper builds a staging copy of the queue (step 4); if that copy
does not include reviews/, every due post is held as "copy review missing". This test runs the real staging block of the script
(the lines from `STAGE=` up to `REPORT=`) against a temp queue and checks that the evidence arrives.
"""
import os
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WRAPPER = REPO / "scripts" / "ops" / "pawstcard_publish.sh"


def staging_block(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('STAGE="$(mktemp -d'))
    end = next(i for i, l in enumerate(lines) if l.startswith("REPORT="))
    return "\n".join(lines[start:end])


class StagingCarriesIrisEvidence(unittest.TestCase):
    def test_stage_copies_manuscript_and_reviews(self):
        block = staging_block(WRAPPER.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            base, queue, work = Path(tmp, "base"), Path(tmp, "queue"), Path(tmp, "work")
            for d in (base, work, queue / "reviews"):
                d.mkdir(parents=True)
            (queue / "x.md").write_text("---\nslug: x\n---\nbody\n", encoding="utf-8")
            (queue / "reviews" / "x.iris.json").write_text('{"reviewer": "iris"}', encoding="utf-8")
            script = 'set -u\nBASE="$1"\nQUEUE="$2"\ncd "$3"\n' + block + '\necho "$STAGE"\n'
            env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
            out = subprocess.run(["bash", "-c", script, "wrapper-test", str(base), str(queue), str(work)],
                                 capture_output=True, text=True, env=env, check=True).stdout.strip().splitlines()
            stage = Path(out[-1])
            self.assertTrue((stage / "x.md").is_file(), "manuscript not staged")
            self.assertTrue((stage / "reviews" / "x.iris.json").is_file(),
                            "Iris evidence reviews/x.iris.json not carried into the staging queue")


class LiveVerification(unittest.TestCase):
    def run_verification(self, *ids):
        block = WRAPPER.read_text(encoding="utf-8").split("# ---- 6. ", 1)[1].split("\n", 1)[1]
        harness = r'''
set -u
BASE="$1"
shift
SLUGS="$*"
LIVE=https://pawstcard.example/
SHA=abc1234
ts() { echo 'test time'; }
log() { printf '%s\n' "$*"; }
notify() { printf '%s\n' "$*" >> "$BASE/notifications"; }
sleep() { printf '%s\n' "$1" >> "$BASE/delays"; }
curl() {
  [ "$1 $2 $3 $4 $5 $6 $7" = '-s --max-time 10 -o /dev/null -w %{http_code}' ] || return 2
  printf '%s\n' "$8" >> "$BASE/requests"
  case "$8" in
    */de/*'?v=abc1234-1') printf 404 ;;
    */id/*) printf 503 ;;
    */zh-Hant/*) printf 200; return 18 ;;  # a response with a failed transfer
    *) printf 200 ;;
  esac
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            result = subprocess.run(
                ["/bin/bash", "-c", harness + block, "wrapper-test", tmp, *ids],
                capture_output=True, text=True, check=True, timeout=5,
                env={**os.environ, "PAWSTCARD_NO_VERIFY": "0"},
            )
            return result.stdout, {path.name: path.read_text() for path in base.iterdir()}

    def test_uses_canonical_url_for_each_language_and_slug(self):
        log, files = self.run_verification("first-post", "first-post.pt-BR", "second-post.ko")
        for lang, slug in (("en", "first-post"), ("pt-BR", "first-post"), ("ko", "second-post")):
            url = f"https://pawstcard.example/journal/{lang}/{slug}/"
            self.assertIn(f"live OK: {url} -> 200", log)
            self.assertIn(f"{url}?v=abc1234-1", files["requests"].splitlines())
        self.assertEqual(files["delays"].splitlines(), ["30"])
        self.assertNotIn("WARN:", log)

    def test_recovered_page_does_not_warn(self):
        log, files = self.run_verification("sample", "sample.de")
        requests = Counter(files["requests"].splitlines())
        self.assertEqual(requests, {
            "https://pawstcard.example/journal/en/sample/?v=abc1234-1": 1,
            "https://pawstcard.example/journal/de/sample/?v=abc1234-1": 1,
            "https://pawstcard.example/journal/de/sample/?v=abc1234-2": 1,
        })
        self.assertEqual(files["delays"].splitlines(), ["30", "30"])
        self.assertIn("live OK: https://pawstcard.example/journal/de/sample/ -> 200", log)
        self.assertNotIn("WARN:", log)
        self.assertNotIn("SOFT_ALERT", files)
        self.assertNotIn("notifications", files)

    def test_warns_once_with_only_the_pages_that_never_passed(self):
        log, files = self.run_verification("sample.de", "sample.id", "sample.zh-Hant")
        warnings = [line for line in log.splitlines() if line.startswith("WARN:")]
        self.assertEqual(len(warnings), 1)
        warning = warnings[0]
        self.assertIn('No artifacts named "github-pages"', warning)
        self.assertIn('gh workflow run "Deploy to GitHub Pages"', warning)
        self.assertNotIn("/de/", warning)
        self.assertEqual(files["delays"].splitlines(), ["30", "30", "60", "120", "180", "240", "420"])
        expected_requests = [f"https://pawstcard.example/journal/de/sample/?v=abc1234-{i}" for i in (1, 2)]
        for lang in ("id", "zh-Hant"):
            url = f"https://pawstcard.example/journal/{lang}/sample/"
            self.assertIn(f"{lang} ({url})", warning)
            expected_requests.extend(f"{url}?v=abc1234-{i}" for i in range(1, 8))
        self.assertCountEqual(files["requests"].splitlines(), expected_requests)
        self.assertIn(warning.removeprefix("WARN: "), files["SOFT_ALERT"])
        self.assertEqual(len(files["notifications"].splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
