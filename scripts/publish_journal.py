#!/usr/bin/env python3
"""Publish what is due: stamp it with the real time, then run the journal build.

`publish_at` in a manuscript is only a floor ("not before"). Running this script is what publishes: every manuscript whose
publish_at has passed gets `published_at: <now, KST, HH:MM>` written into its front matter, and the build then renders it.
Pages, sitemap lastmod, JSON-LD datePublished and the feed all carry that actual time. Future publish_at -> refused/skipped.

    python3 scripts/publish_journal.py                  # stamp + publish every due, not-yet-published manuscript
    python3 scripts/publish_journal.py --slug my-post   # only that one; REFUSE (exit 3) if it is not due yet
    python3 scripts/publish_journal.py --dry-run        # report only, write nothing (no stamping)
    python3 scripts/publish_journal.py --now 2026-10-25T14:13+09:00   # test with a fixed clock

Exit codes: 0 ok · 1 bad manuscript / bad arguments · 2 unknown --slug · 3 --slug is not due / still draft (nothing written)

This script only writes files (journal/**, sitemap.xml, llms.txt, and the published_at line of the manuscripts it publishes).
Committing and pushing to main is a separate, deliberate step:
    git add journal sitemap.xml llms.txt && git commit && git push      # (queue/ holds only manuscripts that are already due)
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402


def run(root, now, slug=None, dry_run=False, out=print):
    root = Path(root).resolve()
    posts, errors = bj.load_posts(root)
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
            out("publish: REFUSED — %s may not go live before %s, now is %s" % (slug, p["publish_at"], bj.stamp_str(now)))
            return 3
        if p["draft"]:
            out("publish: REFUSED — %s is still marked draft: true" % slug)
            return 3
    stamp = bj.stamp_str(now.replace(second=0, microsecond=0))
    todo = [p for p in posts if not p["draft"] and p["_pub"] is None and p["_at"] <= now and (not slug or p["slug"] == slug)]
    if not dry_run:
        for p in todo:
            bj.stamp_published(root / "journal" / "queue" / p["_src"], stamp)
    rep = bj.build(root, now, check_only=dry_run)
    out("publish: now %s%s" % (bj.stamp_str(now), " (dry run, nothing written)" if dry_run else ""))
    out("  %s: %s" % ("would publish" if dry_run else "newly published", ", ".join(p["slug"] for p in todo) or "—"))
    out("  live in total:   %d" % (len(rep["due"]) + (len(todo) if dry_run else 0)))
    for s, at in rep["waiting"]:
        if dry_run and s in {p["slug"] for p in todo}:
            continue
        out("  not yet:         %s (publish_at %s)" % (s, at))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--now", help="ISO 8601 with offset (default: real clock)")
    ap.add_argument("--slug", help="publish only this post; refuse if it is not due")
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
