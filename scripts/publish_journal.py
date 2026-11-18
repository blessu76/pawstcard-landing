#!/usr/bin/env python3
"""Publish what is due: stamp it with the real time, then run the journal build.

`publish_at` in a manuscript is only a floor ("not before"). Running this script is what publishes: every manuscript whose
publish_at has passed is MOVED from the queue dir (outside the repo, --queue / $PAWSTCARD_JOURNAL_QUEUE / ~/pawstcard-journal-queue) into journal/posts/ with
`published_at: <now, KST, YYYY-MM-DDTHH:MM+09:00>` written into its front matter, and the build then renders it.
Pages, sitemap lastmod, JSON-LD datePublished and the feed all carry that actual time. Future publish_at -> refused/skipped.

    python3 scripts/publish_journal.py                  # stamp + publish every due, not-yet-published manuscript
    python3 scripts/publish_journal.py --slug my-post   # only that one; REFUSE (exit 3) if it is not due yet
    python3 scripts/publish_journal.py --dry-run        # report only, write nothing (no stamping)
    python3 scripts/publish_journal.py --now 2026-10-25T07:13-04:00   # test with a fixed clock

Slot gates (slot_rules.py; CLI default on, --no-slot-gates = manual override): a post goes live only when the real KST time is 12:00-17:59,
no post was published yet that KST day, and the KST hour differs from the previous post's. At most one post per run (oldest publish_at first).
Blocked -> a `held:` line, exit 0 (--slug: REFUSED, exit 3). Every run ends with `queue depth: N (min 3)` (WARN below 3) and `next eligible publish: <KST>`.

Copy-review gate (always on, also with --no-slot-gates): a not-yet-published post without `copy_review: iris` + `copy_review_date: YYYY-MM-DD` is never published,
and the stamp alone is not enough: Iris's evidence `<queue>/reviews/<slug>.iris.json` must exist and its sha256 must match the text (scripts/iris_review_evidence.py).
Due -> a `held: <slug> (copy review missing: …)` line, exit 0 (--slug: REFUSED, exit 3); every run prints `unreviewed: N`. Already published posts are grandfathered.

12-language gate (on when i18n/<lang>.json files exist; design: _ipe/foundry/F-016_pawstcard/web/JOURNAL_I18N.md): a new post goes live only
together with a translation for every enabled language (<slug>.<lang>.md in the queue: clean, with its own copy_review) and with every language's
UI strings ready. Otherwise a `held: <slug> (langs 4/12 — missing: … · unreviewed: … · problems: … · ui strings: …)` line, exit 0 (--slug: exit 3).
Publishing moves the English manuscript and its translations together, all with the same published_at.
Backfill: a clean, reviewed queued translation of an ALREADY published post (grandfathered: it went out before the gate) is moved in with its own
stamp as soon as its language's UI strings are ready — no slot gates (it is not a new post). The line then reads `would publish: new-post (+11 langs), old-post.ko`.

Exit codes: 0 ok · 1 bad manuscript / bad arguments · 2 unknown --slug · 3 --slug is not due / still draft (nothing written)

This script only writes files (journal/**, sitemap.xml, llms.txt, and the published_at line of the manuscripts it publishes).
Committing and pushing to main is a separate, deliberate step:
    git add journal sitemap.xml llms.txt && git commit && git push      # (journal/posts/ holds only published manuscripts; unpublished ones stay in the queue dir outside the repo)
"""
import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import slot_rules as sr  # noqa: E402


def run(root, now, slug=None, dry_run=False, out=print, queue_dir=None, slot_gates=False):
    root = Path(root).resolve()
    now = now.astimezone(dt.timezone.utc)
    posts, orphans, errors = bj.load_all(root, queue_dir)
    _ui, ui_ready, ui_errors, ui_warnings = bj.load_ui(root)
    errors = ui_errors + errors
    if errors:
        out("journal: errors\n  " + "\n  ".join(errors))
        return 1
    problems, warnings = bj.lint(posts, now, root, review=False)  # unreviewed posts are held below, not an error
    if problems:
        out("journal: errors\n  " + "\n  ".join(problems))
        return 1
    warnings = ui_warnings + ["%s — ignored until it is fixed" % o for o in orphans] + warnings
    unrev = bj.unreviewed(posts)
    enabled = bj.enabled_langs(root)
    langheld = {}  # slug -> "langs n/N — …" for new posts that may not go out yet (12-language gate)
    if len(enabled) > 1:
        for p in posts:
            if p["_pub"] is None and not p["draft"] and p not in unrev:
                complete, summary = bj.lang_status(p, enabled, ui_ready)
                if not complete:
                    langheld[p["slug"]] = summary
    if slug:
        match = [p for p in posts if p["slug"] == slug]
        if not match:
            out("publish: no manuscript with slug %r in the queue (%s) or journal/posts/" % (slug, queue_dir or root / "journal" / "queue"))
            return 2
        p = match[0]
        if p["_at"] > now:
            out("publish: REFUSED — %s may not go live before %s, now is %s (%s)" % (slug, p["publish_at"], bj.et_stamp_str(now), bj.stamp_str(now)))
            return 3
        if p["draft"]:
            out("publish: REFUSED — %s is still marked draft: true" % slug)
            return 3
        if p in unrev:
            out("publish: REFUSED — %s is held: copy review missing (%s)" % (slug, bj.review_problem(p)))
            return 3
        if slug in langheld:
            out("publish: REFUSED — %s is held: %s" % (slug, langheld[slug]))
            return 3
    stamp = bj.stamp_str(now.replace(second=0, microsecond=0))
    todo = [p for p in posts if not p["draft"] and p["_pub"] is None and p["_at"] <= now and (not slug or p["slug"] == slug)]
    held = [(p["slug"], "copy review missing: %s" % bj.review_problem(p)) for p in unrev if p["_at"] <= now]
    held += [(s, why) for s, why in langheld.items() if next(p for p in posts if p["slug"] == s)["_at"] <= now]
    todo = [p for p in todo if p not in unrev and p["slug"] not in langheld]
    backfill, bf_held = [], []  # queued translations of posts that are already published
    for p in posts:
        if p["_pub"] is None or (slug and p["slug"] != slug):
            continue
        for L, t in sorted(p["_tr"].items()):
            if t["_pub"] is not None:
                continue
            kinds = [k for k, _ in t["_problems"]]
            if kinds:
                bf_held.append(("%s.%s" % (p["slug"], L), "copy review missing: %s" % bj.review_problem(t) if kinds == ["review"]
                                else "fix it first: " + ", ".join(dict.fromkeys(k for k in kinds if k != "review"))))
            elif not ui_ready.get(L):
                bf_held.append(("%s.%s" % (p["slug"], L), "ui strings for %s are not ready (i18n/%s.json)" % (L, L)))
            else:
                backfill.append(t)
    held += bf_held
    if slot_gates:  # extra gates on top of the publish_at floor: KST 12-17 window, max 1 per KST day, hour != previous post's hour
        first, slot_held = sr.pick([p for p in posts if p not in unrev and p["slug"] not in langheld], now)
        if slug and slot_held and not first:
            out("publish: REFUSED — %s is held: %s" % (slug, slot_held[0][1]))
            return 3
        todo = [first] if first and first in todo else []
        held += [h for h in slot_held if h[0] in {p["slug"] for p in posts if p["_pub"] is None}]
    if not dry_run:
        posts_dir = root.joinpath(*bj.POSTS_REL)
        posts_dir.mkdir(parents=True, exist_ok=True)
        moves = [m for p in todo for m in [p] + [t for _, t in sorted(p["_tr"].items()) if t["_pub"] is None]] + backfill
        for m in moves:  # move the manuscript (+ its translations) from the queue into the repo, stamped; from here on it is public
            dest = posts_dir / m["_src"]
            shutil.copyfile(m["_file"], dest)
            bj.stamp_published(dest, stamp)
            m["_file"].unlink()
    rep = bj.build(root, now, check_only=dry_run, queue_dir=queue_dir)
    for w in warnings:
        out("  " + (w if w.startswith("WARN:") else "warning: " + w))
    out("publish: now %s = %s%s" % (bj.stamp_str(now), bj.et_stamp_str(now), " (dry run, nothing written)" if dry_run else ""))
    names = (["%s%s" % (p["slug"], " (+%d langs)" % n if n else "") for p in todo for n in [sum(t["_pub"] is None for t in p["_tr"].values())]]
             + ["%s.%s" % (t["slug"], t["_lang"]) for t in backfill])
    out("  %s: %s" % ("would publish" if dry_run else "newly published", ", ".join(names) or "—"))
    out("  live in total:   %d" % (len(rep["due"]) + (len(todo) if dry_run else 0)))
    for s, why in held:
        out("  held:            %s (%s)" % (s, why))
    for s, at in rep["waiting"]:
        if (dry_run and s in {p["slug"] for p in todo}) or s in {h[0] for h in held}:
            continue
        out("  not yet:         %s (publish_at %s)" % (s, at))
    out("  unreviewed: %d" % len(unrev))
    if len(enabled) > 1:
        out("  languages: %d enabled (%s), ui ready: %s" % (len(enabled), " ".join(enabled), " ".join(L for L in enabled if ui_ready.get(L))))
    if slot_gates:
        for line in sr.report([dict(p, _pub=p["_pub"] or (now if p in todo else None)) for p in posts], now):
            out("  " + line)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--now", help="ISO 8601 with offset (default: real clock)")
    ap.add_argument("--slug", help="publish only this post; refuse if it is not due")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-slot-gates", action="store_true", help="manual override: skip the KST 12-17 / 1-per-day / hour-differs gates (the unattended publisher never uses it)")
    ap.add_argument("--queue", default=str(bj.default_queue_dir()), help="unpublished manuscripts (outside the repo); default ~/pawstcard-journal-queue or $%s" % bj.QUEUE_ENV)
    a = ap.parse_args(argv)
    try:
        now = bj.parse_now(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
    except ValueError as ex:
        print(str(ex), file=sys.stderr)
        return 1
    return run(a.root, now, a.slug, a.dry_run, queue_dir=a.queue, slot_gates=not a.no_slot_gates)


if __name__ == "__main__":
    sys.exit(main())
