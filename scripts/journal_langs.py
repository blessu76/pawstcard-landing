#!/usr/bin/env python3
"""Translation status and skeletons for the 12-language journal (design: _ipe/foundry/F-016_pawstcard/web/JOURNAL_I18N.md).

    python3 scripts/journal_langs.py status                       # matrix: every English post x every enabled language
    python3 scripts/journal_langs.py scaffold --lang ko --slug my-post --out ~/pawstcard-translations

status cells:  ✓ published · R queued, clean and reviewed (goes out with / after the English post) · U queued, copy_review missing
               ! queued with a format / structure / placeholder problem (python3 scripts/build_journal.py --check-queue names it) · · missing
               The `ui` row: ✓ i18n/<lang>.json ready · · not ready (empty strings / no copy_review).
scaffold writes <out>/<slug>.<lang>.md: the translation front matter (title, description, copy_review empty) and the English body under a
TODO line, so every check fails until it is really translated and reviewed. It never overwrites a file and never writes into the queue dir
(the queue belongs to the journal writer — a finished, reviewed translation is moved there by hand).
Read only otherwise: nothing in the repo is changed.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import languages as LANGS  # noqa: E402

LEGEND = "✓ published · R ready (queued, reviewed) · U unreviewed · ! problem · · missing"


def cell(t):
    if t is None:
        return "·"
    if t["_pub"] is not None:
        return "✓"
    kinds = [k for k, _ in t["_problems"]]
    if any(k != "review" for k in kinds):
        return "!"
    return "U" if kinds else "R"


def status(root, queue_dir, out=print):
    _ui, ready, ui_errors, _w = bj.load_ui(root)
    posts, orphans, errors = bj.load_all(root, queue_dir)
    if ui_errors + errors:
        out("journal_langs: errors\n  " + "\n  ".join(ui_errors + errors))
        return 1
    enabled = bj.enabled_langs(root)
    if len(enabled) == 1:
        out("only English is enabled here (no i18n/<lang>.json files)")
        return 0
    width = max([len(L) for L in enabled] + [2])
    name_w = max([len(p["slug"]) for p in posts] + [len("ui")]) + 2
    out(" " * name_w + "  " + " ".join(L.rjust(width) for L in enabled[1:]))
    out("ui".ljust(name_w) + "  " + " ".join(("✓" if ready.get(L) else "·").rjust(width) for L in enabled[1:]))
    for p in posts:
        state = "draft" if p["draft"] else ("live" if p["_pub"] is not None else "queued")
        row = " ".join(cell(p["_tr"].get(L)).rjust(width) for L in enabled[1:])
        line = p["slug"].ljust(name_w) + "  " + row + "  " + state
        if state == "queued":
            line += "  " + bj.lang_status(p, enabled, ready)[1]
        out(line)
    out(LEGEND)
    for o in orphans:
        out("ignored: " + o)
    return 0


def scaffold(root, queue_dir, lang, slug, out_dir, out=print):
    if lang not in LANGS.SUPPORTED[1:]:
        out("scaffold: %r is not a translation language (one of %s)" % (lang, ", ".join(LANGS.SUPPORTED[1:])))
        return 1
    out_dir = Path(out_dir).expanduser().resolve()
    if queue_dir and out_dir == Path(queue_dir).expanduser().resolve():
        out("scaffold: refusing to write into the queue dir %s — scaffold elsewhere and move the finished, reviewed file there" % out_dir)
        return 1
    if out_dir == Path(root).resolve().joinpath(*bj.POSTS_REL):
        out("scaffold: refusing to write into journal/posts/ (published manuscripts only)")
        return 1
    posts, _orphans, errors = bj.load_all(root, queue_dir)
    p = next((x for x in posts if x["slug"] == slug), None)
    if p is None:
        out("scaffold: no English manuscript %s.md%s" % (slug, " (errors: %s)" % "; ".join(errors) if errors else ""))
        return 1
    dest = out_dir / ("%s.%s.md" % (slug, lang))
    if dest.exists():
        out("scaffold: %s exists — not overwritten" % dest)
        return 1
    lines = ["---", "slug: " + slug, "lang: " + lang, "translation_of: " + slug, 'title: ""', 'description: ""']
    if p.get("image"):
        lines.append('image_alt: ""')
    lines += ["tags: ", 'copy_review: ""', 'copy_review_date: ""', "---", "",
              "TODO: translate everything below into %s (%s). Keep every heading and its level (## / ###); then delete this line." % (LANGS.NAMES[lang], lang),
              "", p["_body"].rstrip("\n"), ""]
    out_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines), encoding="utf-8")
    out("scaffold: wrote %s" % dest)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument("--queue", default=str(bj.default_queue_dir()))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sc = sub.add_parser("scaffold")
    sc.add_argument("--lang", required=True)
    sc.add_argument("--slug", required=True)
    sc.add_argument("--out", required=True, help="drafts dir (never the queue dir)")
    a = ap.parse_args(argv)
    if a.cmd == "status":
        return status(Path(a.root), a.queue)
    return scaffold(Path(a.root), a.queue, a.lang, a.slug, a.out)


if __name__ == "__main__":
    sys.exit(main())
