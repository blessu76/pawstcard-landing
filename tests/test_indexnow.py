"""IndexNow (SEO guide P0-3): only changed, indexable URLs; key file is live and self-describing.  Nothing here touches the network."""
import contextlib
import io
import re
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import indexnow as ix  # noqa: E402

SITE = "https://pawstcard.ipe.rest"
KEY = "0123456789abcdef0123456789abcdef"


def git(cwd, *args):
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=str(cwd), capture_output=True, text=True, check=True).stdout.strip()


class UrlMapping(unittest.TestCase):
    def test_indexable_pages_map_to_their_public_url(self):
        self.assertEqual(ix.url_for("index.html"), SITE + "/")
        self.assertEqual(ix.url_for("journal/index.html"), SITE + "/journal/")
        self.assertEqual(ix.url_for("journal/en/some-post-2/index.html"), SITE + "/journal/en/some-post-2/")

    def test_everything_else_is_not_sent(self):
        for path in ("404.html", "sitemap.xml", "llms.txt", "robots.txt", "journal/feed.xml", "journal/assets/journal.css",
                     "journal/posts/a.md", "scripts/build_journal.py", KEY + ".txt", "journal/en/a/other.html", "journal/en/A_b/index.html"):
            self.assertIsNone(ix.url_for(path), path)


class ChangedUrls(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(self.d)]))
        git(self.d, "init", "-q")
        for rel in ("index.html", "journal/index.html", "journal/en/a/index.html", "journal/en/b/index.html", "404.html", "sitemap.xml"):
            (self.d / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.d / rel).write_text("v1")
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "base")
        self.base = git(self.d, "rev-parse", "HEAD")

    def test_only_added_or_modified_indexable_pages(self):
        (self.d / "journal/en/b/index.html").write_text("v2")          # modified
        (self.d / "journal/en/c").mkdir()
        (self.d / "journal/en/c/index.html").write_text("new")         # added
        (self.d / "journal/index.html").write_text("v2")
        (self.d / "sitemap.xml").write_text("v2")                      # not sent
        (self.d / "404.html").write_text("v2")                         # not sent
        (self.d / "journal/en/a/index.html").unlink()                  # deleted: not sent
        git(self.d, "add", "-A")
        git(self.d, "commit", "-qm", "change")
        self.assertEqual(sorted(ix.changed_urls(self.base, self.d)),
                         [SITE + "/journal/", SITE + "/journal/en/b/", SITE + "/journal/en/c/"])

    def test_nothing_changed_nothing_sent(self):
        git(self.d, "commit", "-q", "--allow-empty", "-m", "empty")
        self.assertEqual(ix.changed_urls(self.base, self.d), [])

    def test_unknown_or_null_before_sha_sends_nothing_instead_of_everything(self):
        self.assertEqual(ix.changed_urls(ix.NULL_SHA, self.d), [])
        self.assertEqual(ix.changed_urls("", self.d), [])
        self.assertEqual(ix.changed_urls("f" * 40, self.d), [])


class PayloadAndKey(unittest.TestCase):
    def test_payload_shape_and_host_guard(self):
        p = ix.build_payload(KEY, [SITE + "/journal/"])
        self.assertEqual(p, {"host": "pawstcard.ipe.rest", "key": KEY, "keyLocation": "%s/%s.txt" % (SITE, KEY), "urlList": [SITE + "/journal/"]})
        with self.assertRaises(SystemExit):
            ix.build_payload(KEY, ["https://example.com/x/"])

    def test_the_repo_key_file_exists_and_contains_its_own_name(self):
        key = ix.find_key(REPO)
        self.assertRegex(key, r"^[0-9a-f]{32}$")
        self.assertEqual((REPO / (key + ".txt")).read_text(encoding="utf-8").strip(), key)

    def test_key_file_is_not_a_page_nor_in_the_sitemap(self):
        key = ix.find_key(REPO)
        self.assertNotIn(key, (REPO / "sitemap.xml").read_text(encoding="utf-8"))

    def test_key_live_check_polls_until_the_file_appears(self):
        class Resp:
            def __init__(self, status, body):
                self.status, self.body = status, body
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return self.body.encode()
        answers = [urllib.error.URLError("not yet"), Resp(404, ""), Resp(200, KEY + "\n")]
        calls, waits = [], []
        def opener(url, timeout):
            calls.append(url)
            a = answers.pop(0)
            if isinstance(a, Exception):
                raise a
            return a
        self.assertTrue(ix.key_is_live(KEY, opener=opener, sleep=waits.append))
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(waits), 2)
        self.assertFalse(ix.key_is_live(KEY, tries=2, opener=lambda u, timeout: Resp(200, "other"), sleep=lambda s: None))


class Cli(unittest.TestCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ix.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_nothing_to_send_is_success_without_a_request(self):
        code, out, _ = self.run_main("--changed-since", ix.NULL_SHA)
        self.assertEqual(code, 0)
        self.assertIn("nothing to send", out)

    def test_dry_run_never_prints_the_key(self):
        code, out, _ = self.run_main("--dry-run", SITE + "/journal/")
        self.assertEqual(code, 0)
        self.assertIn(SITE + "/journal/", out)
        self.assertNotRegex(out, r"[0-9a-f]{32}")


class WorkflowWiring(unittest.TestCase):
    def test_deploy_runs_indexnow_after_the_deploy_step_and_never_fails_it(self):
        wf = (REPO / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
        self.assertLess(wf.index("id: deployment"), wf.index("scripts/indexnow.py --changed-since"))
        step = wf[wf.index("IndexNow — changed pages"):wf.index("Notify Slack — success")]
        self.assertIn("continue-on-error: true", step)
        self.assertIn("github.event.before", step)
        self.assertRegex(wf, r"fetch-depth: 2")


if __name__ == "__main__":
    unittest.main()
