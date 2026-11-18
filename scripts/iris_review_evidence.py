#!/usr/bin/env python3
"""Record Iris's copy review of a queued journal manuscript (or translation) as evidence the publish gate checks.

    python3 scripts/iris_review_evidence.py my-post --note <review record path>
    python3 scripts/iris_review_evidence.py /path/to/queue/my-post.es.md --note <review record path>

Writes <queue dir>/reviews/<stem>.iris.json = {reviewer: "iris", sha256, reviewed_at, note}. The sha256 is taken over the manuscript
text WITHOUT its copy_review / copy_review_date lines, so the stamp can be added by hand before or after. Any later body edit makes
the evidence stale and the post is held again until Iris reviews the new text and this script is run again.
Only Iris writes this record; the stamp lines themselves stay manual.
Refuses (exit 3) a file that is already published (published_at) or missing; exit 2 on bad arguments.
"""
import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402


def resolve(arg, queue_dir):
    p = Path(arg)
    if p.is_file():
        return p
    name = arg if arg.endswith(".md") else arg + ".md"
    return Path(queue_dir) / name


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("manuscript", help="queue slug (e.g. my-post or my-post.es) or a path to the .md file")
    ap.add_argument("--note", required=True, help="path of the review record (where Iris's review is written down)")
    ap.add_argument("--queue", help="queue dir (default: $PAWSTCARD_JOURNAL_QUEUE or ~/pawstcard-journal-queue)")
    ap.add_argument("--reviewed-at", help="review date YYYY-MM-DD (default: today, KST)")
    a = ap.parse_args(argv)
    if not a.note.strip():
        print("iris_review_evidence: --note must not be empty", file=sys.stderr)
        return 2
    qdir = Path(a.queue) if a.queue else bj.default_queue_dir()
    f = resolve(a.manuscript, qdir)
    if not f.is_file():
        print("iris_review_evidence: no manuscript %s" % f, file=sys.stderr)
        return 3
    meta, _body = bj.read_front_matter(f)
    if meta.get("published_at"):
        print("iris_review_evidence: %s is already published (published_at) — grandfathered, no evidence needed" % f.name, file=sys.stderr)
        return 3
    if a.reviewed_at:
        try:
            dt.date.fromisoformat(a.reviewed_at)
        except ValueError:
            print("iris_review_evidence: --reviewed-at must be YYYY-MM-DD", file=sys.stderr)
            return 2
    side = bj.write_iris_evidence(f, a.note, reviewed_at=a.reviewed_at)
    print("iris evidence written: %s (sha256 %s)" % (side, bj.manuscript_sha256(f)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
