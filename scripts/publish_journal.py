#!/usr/bin/env python3
"""Publish what is due: run the journal build against the clock and say what went live.

    python3 scripts/publish_journal.py                  # publish every manuscript whose publish_at has passed
    python3 scripts/publish_journal.py --slug my-post   # same, but REFUSE (exit 3) if my-post is not due yet
    python3 scripts/publish_journal.py --dry-run        # report only, write nothing
    python3 scripts/publish_journal.py --now 2026-10-25T14:00+09:00   # test with a fixed clock

Exit codes: 0 ok · 1 bad manuscript / bad arguments · 2 unknown --slug · 3 --slug is scheduled for the future (nothing written)

This script only writes files (journal/**, sitemap.xml, llms.txt). Committing and pushing to main is a separate, deliberate step:
    git add journal/en journal/index.html journal/feed.xml sitemap.xml llms.txt <due manuscripts> && git commit && git push
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402


def run(root, now, slug=None, dry_run=False, out=print):
    posts, errors = bj.load_posts(Path(root).resolve())
    if errors:
        out("journal: errors\n  " + "\n  ".join(errors))
        return 1
    if slug:
        match = [p for p in posts if p["slug"] == slug]
        if not match:
            out("publish: no manuscript with slug %r in journal/queue/" % slug)
            return 2
        p = match[0]
        if p["_at"] > now:
            out("publish: REFUSED — %s is scheduled for %s, now is %s" % (slug, p["publish_at"], bj.stamp_str(now)))
            return 3
        if p["draft"]:
            out("publish: REFUSED — %s is still marked draft: true" % slug)
            return 3
    rep = bj.build(root, now, check_only=dry_run)
    out("publish: now %s%s" % (bj.stamp_str(now), " (dry run, nothing written)" if dry_run else ""))
    out("  newly published: %s" % (", ".join(rep["new"]) or "—"))
    out("  live in total:   %d" % len(rep["due"]))
    for s, at in rep["waiting"]:
        out("  scheduled:       %s @ %s" % (s, at))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--now", help="ISO 8601 with offset (default: real clock)")
    ap.add_argument("--slug", help="require this post to be due; refuse otherwise")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    try:
        now = bj.parse_now(a.now) if a.now else dt.datetime.now(bj.KST)
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1
    return run(a.root, now, a.slug, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
