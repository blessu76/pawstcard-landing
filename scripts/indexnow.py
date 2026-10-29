#!/usr/bin/env python3
"""Tell IndexNow (Bing, Naver, Yandex, ... — Google does not use it; Google reads sitemap.xml) which URLs changed.

Called by .github/workflows/deploy.yml AFTER the site is deployed (the key file must already be live):

    python3 scripts/indexnow.py --changed-since <git sha>   # only the pages that differ from <sha> (the push's "before")
    python3 scripts/indexnow.py URL [URL ...]               # only these URLs
    python3 scripts/indexnow.py --dry-run ...               # print the payload, send nothing

Changed URLs = added/modified index.html pages (landing, /journal/, /journal/en/<slug>/) between <sha> and HEAD. Nothing else is sent:
not the sitemap, not the 404, not deleted pages. No changed page -> exit 0 without a request.
The key is the repo-root file named <32 hex>.txt whose single line is the key itself (public by design). Standard library only.
Exit 0 = sent (HTTP 200/202) or nothing to send; 1 = IndexNow refused / key file not live.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://pawstcard.ipe.rest"
ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_FILE_RE = re.compile(r"^([0-9a-f]{32})\.txt$")
NULL_SHA = "0" * 40


def find_key(root):
    """The key whose <key>.txt file in `root` contains exactly that key."""
    for p in sorted(Path(root).iterdir()):
        m = KEY_FILE_RE.match(p.name)
        if m and p.read_text(encoding="utf-8").strip() == m.group(1):
            return m.group(1)
    raise SystemExit("no IndexNow key file (<32 hex>.txt containing its own name) in " + str(root))


def url_for(path):
    """Repo path -> public URL of an indexable page, else None (404, assets, scripts, sitemap, ...)."""
    if path == "index.html":
        return SITE + "/"
    if path == "journal/index.html":
        return SITE + "/journal/"
    m = re.fullmatch(r"journal/en/([a-z0-9-]+)/index\.html", path)
    return "%s/journal/en/%s/" % (SITE, m.group(1)) if m else None


def changed_urls(since, root=ROOT):
    """URLs of the indexable pages added or modified between `since` and HEAD. An unknown/empty `since` (first push, force push) -> []."""
    if not since or since == NULL_SHA:
        return []
    try:
        out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", since, "HEAD"], cwd=str(root),
                             capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return []
    urls = [url_for(line.strip()) for line in out.splitlines()]
    return list(dict.fromkeys(u for u in urls if u))


def build_payload(key, urls, site=SITE):
    host = site.split("://", 1)[1]
    bad = [u for u in urls if not u.startswith(site + "/")]
    if bad:
        raise SystemExit("URLs outside %s: %s" % (site, ", ".join(bad)))
    return {"host": host, "key": key, "keyLocation": "%s/%s.txt" % (site, key), "urlList": list(urls)}


def key_is_live(key, site=SITE, tries=6, wait=10, opener=urllib.request.urlopen, sleep=time.sleep):
    """The deploy action returns before every CDN edge serves the new files: poll the (public) key file for up to ~1 minute."""
    for i in range(tries):
        try:
            with opener("%s/%s.txt?v=%d" % (site, key, time.time()), timeout=15) as r:
                if r.status == 200 and r.read().decode("utf-8").strip() == key:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        if i < tries - 1:
            sleep(wait)
    return False


def send(payload, endpoint=ENDPOINT, timeout=30):
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="*", help="URLs to submit")
    ap.add_argument("--changed-since", metavar="SHA", help="submit the indexable pages that changed between SHA and HEAD")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true", help="print the payload, send nothing")
    a = ap.parse_args(argv)

    urls = list(a.urls) + (changed_urls(a.changed_since, a.root) if a.changed_since is not None else [])
    if not urls:
        print("IndexNow: no changed page, nothing to send")
        return 0
    payload = build_payload(find_key(a.root), urls)
    if a.dry_run:
        print("POST " + ENDPOINT)
        print(json.dumps(dict(payload, key="<key>", keyLocation="%s/<key>.txt" % SITE), indent=2))  # never print the key
        return 0
    if not key_is_live(payload["key"]):
        print("IndexNow: the key file is not live at %s — not sending" % payload["keyLocation"].replace(payload["key"], "<key>"), file=sys.stderr)
        return 1
    status = send(payload)
    print("IndexNow %s: HTTP %d (%d URLs)" % (payload["host"], status, len(urls)))
    for u in urls:
        print("  " + u)
    if status in (200, 202):
        return 0
    print("200/202 = ok; 403 = key mismatch; 422 = URL host mismatch; 429 = too many requests", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
