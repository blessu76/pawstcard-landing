#!/usr/bin/env python3
"""Build the Pawstcard Journal (pawstcard.ipe.rest/journal/) — no dependencies (Python 3.8+ stdlib only).

Reads   journal/posts/<slug>.md           PUBLISHED manuscripts (stamped with published_at; committed — this is the build input)
        <queue dir>/<slug>.md             UNPUBLISHED manuscripts. NOT in the repo (main is public and everything in it is served):
                                          --queue DIR, env PAWSTCARD_JOURNAL_QUEUE, default ~/pawstcard-journal-queue
                                          (front matter + Markdown, English)
        journal/posts/<slug>.<lang>.md    translations (published / queued the same way); <lang> = one of languages.SUPPORTED but en
        <queue dir>/<slug>.<lang>.md      (front matter: TRANSLATION_REQUIRED, see parse_translation; design: _ipe/foundry/F-016_pawstcard/web/JOURNAL_I18N.md)
        i18n/<lang>.json                  UI strings (nav, footer, buttons) per language; en.json is the source. A language is ENABLED when its
                                          file exists (a site root without i18n/ = English only) and READY when every string is filled in and
                                          `_meta` carries copy_review: iris + copy_review_date. Not ready -> a build warning, no pages in that
                                          language and its new posts are held (never an English fallback).
Writes  journal/en/<slug>/index.html      one page per published post (Article JSON-LD + BreadcrumbList)
        journal/index.html                list page (Blog + ItemList JSON-LD)
        journal/feed.xml                  RSS 2.0
        journal/<lang>/<slug>/index.html  the same three per language, for the translations that are live
        journal/<lang>/index.html         (only when that language has at least one live post); every page lists its live
        journal/<lang>/feed.xml           language versions as hreflang + x-default (= English) and in the header's #ipe-langs JSON
        sitemap.xml                       journal URLs between <!-- journal:start --> / <!-- journal:end -->
                                          (hreflang + lastmod + image); the landing entry is untouched except its lastmod = newest post
        llms.txt                          "Journal" section between <!-- journal:llms:start --> / <!-- journal:llms:end -->
        index.html                        landing page: the "Journal" card section (newest HOME_CARDS = 3 published posts) between
                                          <!-- journal:home:start --> / <!-- journal:home:end -->; the rest of the file is never touched.
                                          --check fails when that block is not exactly what the published posts say it should be.

`publish_at` is only a floor ("never before this time"). A post goes live when scripts/publish_journal.py stamps it with
`published_at` = the real run time (KST = Asia/Seoul, HH:MM+09:00; the site-wide rule is "registration = KST"). Pages, list, feed, sitemap lastmod, JSON-LD datePublished all show
`published_at`, never `publish_at`. A post without `published_at` (or with one after --now) produces no page, no list entry,
no sitemap/llms/feed line. The build is a pure function of (manuscripts, now).
A translation is live when it is stamped (publish_journal.py gives a new post's translations the English stamp, a late one its own),
its English post is live and its language is ready.

Front matter (between two `---` lines, `key: value` per line):
    slug:         required, [a-z0-9-]+, must equal the file name (<slug>.md)
    title:        required
    description:  required, one sentence, <= 155 characters (meta description, list card, RSS)
    publish_at:   required, YYYY-MM-DDTHH:MM-04:00  (America/New_York; the offset is verified against the real EDT/EST rule,
                  e.g. -04:00 until 2026-11-01, -05:00 after) — earliest time the post may go live
    published_at: written by scripts/publish_journal.py as YYYY-MM-DDTHH:MM+09:00 (KST); the actual publication time. Do not write it by hand.
    updated:      optional, YYYY-MM-DDTHH:MM+09:00 (KST) -> dateModified / sitemap lastmod
    category:     optional, e.g. guides
    tags:         optional, list `[a, b, c]` or comma separated -> keywords / article:tag (`keywords:` is accepted as an alias)
    image:        optional, hero image (/journal/assets/<slug>/x.jpg or https URL); default /og-image.png
    image_alt:    optional, alt text of the hero image
    draft:        optional, true -> skipped everywhere (use --drafts to preview on a COPY of the site)
    copy_review:  `iris` + copy_review_date: YYYY-MM-DD — the copy review stamp. REQUIRED for every post that is not published yet:
                  publish_journal.py holds an unreviewed one and `--check` fails on it. Published posts (stamped published_at) are grandfathered.

Usage:
    python3 scripts/build_journal.py                      # build into this repo (real clock)
    python3 scripts/build_journal.py --now 2026-10-25T07:13-04:00
    python3 scripts/build_journal.py --check              # validate only, write nothing
    python3 scripts/build_journal.py --check-queue        # --check, and a NEW manuscript under 300 words is an error (run when a manuscript lands in the queue)
    python3 scripts/build_journal.py --root /tmp/preview --drafts
"""
import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo  # Python 3.9+

import languages as LANGS  # the 12 site languages (same values as ipe_web_kit v0.7.1)

SITE = "https://pawstcard.ipe.rest"
GA_ID = "G-CGW3MH2S00"
CF_TOKEN = "32d73b01c2de4d46a9de77a88952a654"
PIXEL_ID = "1932639057434633"
GEN_MARK = "generated by scripts/build_journal.py"
REQUIRED = ("slug", "title", "description", "publish_at")
DESC_MAX = 155
RESERVED_SLUGS = ("index", "feed", "assets", "queue", "posts")
POSTS_REL = ("journal", "posts")  # published manuscripts (in the repo)
QUEUE_ENV = "PAWSTCARD_JOURNAL_QUEUE"
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REVIEWER = "iris"  # the only accepted `copy_review` value
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})([+-]\d{2}:\d{2})$")
KST_STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\+09:00$")
TZ = ZoneInfo("America/New_York")  # the scheduling clock: publish_at floors are Eastern Time (EDT -04:00 / EST -05:00)
OUT_TZ = ZoneInfo("Asia/Seoul")    # everything that is shown or recorded (published_at, JSON-LD, sitemap, feed, page text) is KST +09:00
DEFAULT_OG_IMAGE = SITE + "/og-image.png"
OG_IMAGE_SIZE = (1200, 630)  # pixels of /og-image.png
I18N_REL = "i18n"  # i18n/<lang>.json — UI strings per language
EN_UI_PATH = Path(__file__).resolve().parent.parent / I18N_REL / "en.json"  # the English source strings (this repo's copy, also for other site roots)
EN_UI = {k: v for k, v in json.loads(EN_UI_PATH.read_text(encoding="utf-8")).items() if k != "_meta"}
UI_KEYS = tuple(EN_UI)
OG_IMAGE_ALT = EN_UI["og_image_alt"]
IMG_NS = "http://www.google.com/schemas/sitemap-image/1.1"
XHTML_NS = "http://www.w3.org/1999/xhtml"
ORG_ID = "https://ipe.rest/#organization"   # the company node: ipe.rest defines it, this landing page and every journal page point at it
BRAND_ID = SITE + "/#brand"                 # the product (defined on the landing page)
ORG = {"@type": "Organization", "@id": ORG_ID, "name": "ipe()", "url": "https://ipe.rest/",
       "brand": {"@type": "Brand", "@id": BRAND_ID, "name": "Pawstcard"}}
OG_IMAGE = {"@type": "ImageObject", "url": SITE + "/og-image.png", "width": 1200, "height": 630}   # tests pin these to the real file
APP_ICON = {"@type": "ImageObject", "url": SITE + "/app-icon.png", "width": 1024, "height": 1024}  # square app icon = publisher logo
SM_START, SM_END = "<!-- journal:start -->", "<!-- journal:end -->"
LLMS_START, LLMS_END = "<!-- journal:llms:start -->", "<!-- journal:llms:end -->"
CSS_REL = "journal/assets/journal.css"
HOME_START, HOME_END = "<!-- journal:home:start -->", "<!-- journal:home:end -->"
HOME_CARDS = 3  # the landing page shows the newest 3 published posts
BLOG_DESC = EN_UI["blog_desc"]
TRANSLATION_REQUIRED = ("slug", "lang", "translation_of", "title", "description")
TRANSLATION_FORBIDDEN = ("publish_at", "image", "draft", "category")  # inherited from the English post; published_at only by the publisher


class JournalError(Exception):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


def esc(s):
    return html.escape(str(s), quote=True)


# ---------------------------------------------------------------- time
def parse_stamp(value, field="publish_at"):
    """YYYY-MM-DDTHH:MM-04:00 -> aware datetime (America/New_York). The offset must be the one Eastern Time really has at
    that wall-clock time (-04:00 in EDT, -05:00 in EST; DST switches on 2026-11-01) — it is checked, never trusted."""
    m = STAMP_RE.match(value or "")
    if not m:
        raise ValueError("%s must look like YYYY-MM-DDTHH:MM-04:00 (America/New_York, offset included): %r" % (field, value))
    try:
        naive = dt.datetime.fromisoformat(m.group(1))
    except ValueError:
        raise ValueError("%s is not a real date/time: %r" % (field, value))
    for fold in (0, 1):  # fold=1 only matters for the repeated hour at the end of DST
        cand = naive.replace(tzinfo=TZ, fold=fold)
        if cand.astimezone(dt.timezone.utc).astimezone(TZ).replace(tzinfo=None) != naive:
            raise ValueError("%s: %s does not exist in America/New_York (DST gap)" % (field, m.group(1)))
        if offset_str(cand) == m.group(2):
            return cand.astimezone(dt.timezone.utc)  # compare instants, never same-zone wall clocks (that is wrong across DST)
    raise ValueError("%s: wrong UTC offset for America/New_York at that time (it is %s): %r" % (field, offset_str(naive.replace(tzinfo=TZ)), value))


def offset_str(d):
    s = d.strftime("%z")
    return s[:3] + ":" + s[3:]


def parse_now(value):
    """--now accepts YYYY-MM-DDTHH:MM[:SS] with an explicit offset (-04:00, +09:00, Z, ...)."""
    s = value.strip().replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        raise ValueError("--now must be ISO 8601 with an offset, e.g. 2026-10-25T14:00-04:00: %r" % value)
    if d.tzinfo is None:
        raise ValueError("--now needs an explicit UTC offset, e.g. 2026-10-25T14:00-04:00: %r" % value)
    return d.astimezone(dt.timezone.utc)


def parse_kst_stamp(value, field="published_at"):
    """YYYY-MM-DDTHH:MM+09:00 -> aware datetime (UTC instant). Korea has no DST, so the offset must be exactly +09:00."""
    m = KST_STAMP_RE.match(value or "")
    if not m:
        raise ValueError("%s must look like YYYY-MM-DDTHH:MM+09:00 (KST): %r" % (field, value))
    try:
        naive = dt.datetime.fromisoformat(m.group(1))
    except ValueError:
        raise ValueError("%s is not a real date/time: %r" % (field, value))
    return naive.replace(tzinfo=OUT_TZ).astimezone(dt.timezone.utc)


def kst(d):
    return d.astimezone(OUT_TZ)


def et(d):
    return d.astimezone(TZ)


def stamp_str(d):
    """minute precision, KST: 2026-10-25T20:13+09:00 (what is written to published_at)"""
    return kst(d).strftime("%Y-%m-%dT%H:%M") + "+09:00"


def et_stamp_str(d):
    """minute precision, Eastern Time with its real offset (publish_at terms): 2026-10-25T07:13-04:00"""
    d = et(d)
    return d.strftime("%Y-%m-%dT%H:%M") + offset_str(d)


def iso_sec(d):
    return kst(d).strftime("%Y-%m-%dT%H:%M:%S") + "+09:00"


def fmt_date(d):
    """static text (crawlers, no-JS readers): 2026-10-25 20:13 KST  (24-hour, no seconds)"""
    return kst(d).strftime("%Y-%m-%d %H:%M") + " KST"


def ymd(d):
    return kst(d).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- front matter
def read_front_matter(path):
    """-> (meta with lower-cased keys, body). Raises ValueError when the front matter is missing or malformed."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        raise ValueError("missing front matter (file must start with ---)")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("front matter is not closed with ---")
    meta = {}
    for line in text[4:end].split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            raise ValueError("bad front matter line: %r" % line)
        k, v = line.split(":", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        meta[k.strip().lower()] = v
    return meta, text[end + 4:].lstrip("\n")


def parse_keywords(meta):
    raw_tags = (meta.get("tags") or meta.get("keywords") or "").strip()
    if raw_tags.startswith("[") and raw_tags.endswith("]"):
        raw_tags = raw_tags[1:-1]
    return [x.strip().strip("\"'").strip() for x in raw_tags.split(",") if x.strip()]


def parse_post(path):
    meta, body = read_front_matter(path)
    missing = [k for k in REQUIRED if not meta.get(k)]
    if missing:
        raise ValueError("missing front matter: " + ", ".join(missing))
    if not SLUG_RE.match(meta["slug"]):
        raise ValueError("slug must match [a-z0-9-]+: %r" % meta["slug"])
    if meta["slug"] in RESERVED_SLUGS:
        raise ValueError("slug %r is reserved" % meta["slug"])
    if path.stem != meta["slug"]:
        raise ValueError("file name must be <slug>.md (slug is %r)" % meta["slug"])
    meta["_at"] = parse_stamp(meta["publish_at"])
    meta["_pub"] = parse_kst_stamp(meta["published_at"], "published_at") if meta.get("published_at") else None
    if meta["_pub"] and meta["_pub"] < meta["_at"]:
        raise ValueError("published_at is earlier than publish_at")
    meta["_updated"] = parse_kst_stamp(meta["updated"], "updated") if meta.get("updated") else None
    if meta["_updated"] and meta["_updated"] < (meta["_pub"] or meta["_at"]):
        raise ValueError("updated is earlier than the publication time")
    meta["draft"] = str(meta.get("draft", "false")).lower() in ("true", "yes", "1")
    if len(meta["description"]) > DESC_MAX:
        raise ValueError("description is %d characters (max %d)" % (len(meta["description"]), DESC_MAX))
    meta["_keywords"] = parse_keywords(meta)
    if meta.get("image") and not re.match(r"^(https://|/)", meta["image"]):
        raise ValueError("image must be https://... or a site path starting with /: %r" % meta["image"])
    meta["_body"] = body
    meta["_src"] = path.name
    return meta


def heading_levels(body, title):
    """The <h2>-<h4> sequence a body renders to (outside code fences; the leading '# <title>' dropped like the page does)."""
    levels, fence = [], False
    for line in drop_title_h1(body, title).split("\n"):
        st = line.strip()
        if st.startswith("```"):
            fence = not fence
            continue
        m = None if fence else re.match(r"^(#{1,4})\s+", st)
        if m:
            levels.append({1: 2, 2: 2, 3: 3, 4: 4}[len(m.group(1))])
    return levels


def parse_translation(path, published):
    """<slug>.<lang>.md -> translation dict. Never raises: every problem goes into t["_problems"] as (kind, message),
    kind = format | structure | placeholder | review. `published` = the file is in journal/posts/ (published_at required there,
    forbidden in the queue: the publisher writes it). The heading structure is compared with the English post in load_all."""
    base, _, lang = path.stem.rpartition(".")
    t = {"slug": base, "_lang": lang, "title": "", "description": "", "_body": "", "_src": path.name, "_file": path,
         "_pub": None, "_updated": None, "_keywords": None, "_problems": []}

    def bad(kind, msg):
        t["_problems"].append((kind, msg))

    try:
        meta, body = read_front_matter(path)
    except ValueError as ex:
        bad("format", str(ex))
        return t
    t.update({k: v for k, v in meta.items() if not k.startswith("_")}, _body=body)
    t["slug"], t["_lang"] = base, lang
    missing = [k for k in TRANSLATION_REQUIRED if not meta.get(k)]
    if missing:
        bad("format", "missing front matter: " + ", ".join(missing))
    for k, want in (("slug", base), ("translation_of", base), ("lang", lang)):
        if meta.get(k) and meta[k] != want:
            bad("format", "%s must be %r (file name %s), got %r" % (k, want, path.name, meta[k]))
    forbidden = [k for k in TRANSLATION_FORBIDDEN if k in meta] + (["published_at"] if "published_at" in meta and not published else [])
    if forbidden:
        bad("format", "not allowed in a translation: %s (inherited from the English post; published_at is written by the publisher)" % ", ".join(forbidden))
    if published and not meta.get("published_at"):
        bad("format", "a translation in journal/posts/ needs published_at")
    if len(t["description"]) > DESC_MAX:
        bad("format", "description is %d characters (max %d)" % (len(t["description"]), DESC_MAX))
    for field, key in (("published_at", "_pub"), ("updated", "_updated")):
        if meta.get(field) and (published or field == "updated"):
            try:
                t[key] = parse_kst_stamp(meta[field], field)
            except ValueError as ex:
                bad("format", str(ex))
    if t["_pub"] and t["_updated"] and t["_updated"] < t["_pub"]:
        bad("format", "updated is earlier than published_at")
    t["_keywords"] = parse_keywords(meta) if (meta.get("tags") or meta.get("keywords")) else None
    for field in ("title", "description"):
        if PLACEHOLDER_RE.search(t[field]):
            bad("placeholder", "placeholder text in %s" % field)
    if PLACEHOLDER_RE.search(body):
        bad("placeholder", "placeholder text in the body")
    if not published and review_problem(meta):
        bad("review", review_problem(meta))
    return t


def review_problem(meta):
    """-> None when the copy-review stamp (copy_review: iris + copy_review_date: YYYY-MM-DD) is present and valid, else a short reason."""
    who, day = (meta.get("copy_review") or "").strip(), (meta.get("copy_review_date") or "").strip()
    if not who and not day:
        return "no copy_review"
    if who.lower() != REVIEWER:
        return "copy_review must be %r (got %r)" % (REVIEWER, who) if who else "copy_review is missing (copy_review: %s)" % REVIEWER
    if not day:
        return "copy_review_date is missing (YYYY-MM-DD)"
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError
        dt.date.fromisoformat(day)
    except ValueError:
        return "copy_review_date must be a real date like YYYY-MM-DD (got %r)" % day
    return None


def unreviewed(posts):
    """unpublished, non-draft manuscripts without a valid copy-review stamp (published posts are grandfathered)"""
    return [p for p in posts if p["_pub"] is None and not p["draft"] and review_problem(p)]


def default_queue_dir():
    """Where unpublished manuscripts live (outside the repo): $PAWSTCARD_JOURNAL_QUEUE or ~/pawstcard-journal-queue."""
    return Path(os.environ.get(QUEUE_ENV) or Path.home() / "pawstcard-journal-queue")


def enabled_langs(root):
    """en + every other site language that has an i18n/<lang>.json (a site root without i18n/ is English only)."""
    d = Path(root) / I18N_REL
    return ["en"] + [L for L in LANGS.SUPPORTED[1:] if (d / (L + ".json")).is_file()]


def load_ui(root):
    """i18n/<lang>.json -> (strings {lang: {key: text}}, ready {lang: bool}, errors, warnings).
    errors (stop the build): broken JSON, missing / unknown / non-string keys, a file that is not a site language, an i18n/en.json
    that differs from the builder's source strings. warnings (the language is NOT ready: no pages, new posts held — never an English
    fallback): empty strings, placeholder text, `_meta` without copy_review: iris + copy_review_date."""
    d = Path(root) / I18N_REL
    strings, ready, errors, warnings = {"en": dict(EN_UI)}, {"en": True}, [], []
    waiting = {}
    if not d.is_dir():
        return strings, ready, errors, warnings
    known = {L + ".json" for L in LANGS.SUPPORTED}
    for f in sorted(d.glob("*.json")):
        if f.name not in known:
            errors.append("i18n/%s: not a site language (supported: %s; never %s, zh, pt)" % (f.name, ", ".join(LANGS.SUPPORTED), ", ".join(LANGS.ENDED)))
    for L in LANGS.SUPPORTED:
        f = d / (L + ".json")
        if not f.is_file():
            continue
        name = "i18n/" + f.name
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as ex:
            errors.append("%s: not valid JSON (%s)" % (name, ex))
            continue
        if not isinstance(data, dict):
            errors.append("%s: must be a JSON object" % name)
            continue
        meta = data.get("_meta") if isinstance(data.get("_meta"), dict) else {}
        missing = [k for k in UI_KEYS if k not in data]
        unknown = [k for k in data if k not in UI_KEYS and k != "_meta"]
        nonstr = [k for k in UI_KEYS if k in data and not isinstance(data[k], str)]
        for what, keys in (("missing keys", missing), ("unknown keys", unknown), ("non-string values", nonstr)):
            if keys:
                errors.append("%s: %s: %s (the keys are exactly those of i18n/en.json)" % (name, what, ", ".join(keys)))
        if meta.get("lang", L) != L:
            errors.append("%s: _meta.lang is %r" % (name, meta.get("lang")))
        if missing or unknown or nonstr or meta.get("lang", L) != L:
            continue
        if L == "en":
            if {k: data[k] for k in UI_KEYS} != EN_UI:
                errors.append("%s: differs from the builder's source strings (%s) — edit that file" % (name, EN_UI_PATH))
            continue
        problems = []
        empty = [k for k in UI_KEYS if not data[k].strip()]
        if empty:
            problems.append("%d of %d strings empty" % (len(empty), len(UI_KEYS)))
        ph = [k for k in UI_KEYS if PLACEHOLDER_RE.search(data[k])]
        if ph:
            problems.append("placeholder text in " + ", ".join(ph))
        if review_problem(meta):
            problems.append(review_problem(meta))
        strings[L] = {k: data[k] for k in UI_KEYS}
        ready[L] = not problems
        if problems:
            waiting.setdefault("; ".join(problems), []).append(L)
    for why, langs in waiting.items():  # one line per distinct problem (11 untranslated files are one line, not 11)
        if len(langs) == 1:
            warnings.append("i18n/%s.json: %s — no %s pages are built and new posts wait for it" % (langs[0], why, langs[0]))
        else:
            warnings.append("i18n/{%s}.json: %s — no pages in these languages are built and new posts wait for them" % (",".join(langs), why))
    return strings, ready, errors, warnings


def load_all(root, queue_dir=None):
    """-> (posts sorted newest first, orphans, errors). Every English post carries p["_tr"] = {lang: translation}.
    Reads journal/posts/ (published) and the queue dir (unpublished). queue_dir=None -> <root>/journal/queue (tests, previews).
    English manuscripts: every problem is an error. Translations in journal/posts/: every problem but `review` is an error, and so is
    a language that is not enabled, a missing or unpublished English post and a second file for the same (slug, lang).
    Translations in the queue never stop a build: such files are `orphans` (message strings) and their problems stay in t["_problems"]."""
    root = Path(root)
    posts, errors, orphans, seen, trs = [], [], [], {}, []
    qdir = Path(queue_dir) if queue_dir else root / "journal" / "queue"
    enabled = enabled_langs(root)
    for d, queued in ((root.joinpath(*POSTS_REL), False), (qdir, True)):
        for f in sorted(d.glob("*.md")) if d.is_dir() else []:
            if f.name.lower() == "readme.md":
                continue
            if "." in f.stem:
                trs.append((parse_translation(f, published=not queued), queued))
                continue
            try:
                p = parse_post(f)
            except ValueError as ex:
                errors.append("%s: %s" % (f.name, ex))
                continue
            if p["slug"] in seen:
                errors.append("%s: duplicate slug %r (also %s)" % (f.name, p["slug"], seen[p["slug"]]))
                continue
            seen[p["slug"]] = f.name
            p["_file"] = f
            p["_tr"] = {}
            posts.append(p)
    by_slug = {p["slug"]: p for p in posts}
    for t, queued in trs:
        L, p, name = t["_lang"], by_slug.get(t["slug"]), t["_src"]
        if L not in LANGS.SUPPORTED[1:]:
            why = "%r is not a translation language (use one of %s; never %s, zh, pt)" % (L, ", ".join(LANGS.SUPPORTED[1:]), ", ".join(LANGS.ENDED))
        elif L not in enabled:
            why = "i18n/%s.json does not exist, so %s is not a site language here" % (L, L)
        elif p is None:
            why = "no English post %s.md" % t["slug"]
        elif not queued and p["_pub"] is None:
            why = "its English post %s is not published" % p["_src"]
        elif L in p["_tr"]:
            why = "a second %s translation of %s (also %s)" % (L, t["slug"], p["_tr"][L]["_src"])
        else:
            why = None
            if not any(k == "format" for k, _ in t["_problems"]):
                want, got = heading_levels(p["_body"], p["title"]), heading_levels(t["_body"], t["title"])
                if want != got:
                    i = next((k for k in range(min(len(want), len(got))) if want[k] != got[k]), min(len(want), len(got)))
                    t["_problems"].append(("structure", "headings differ from the English post at heading %d (English: %s, here: %s)"
                                           % (i + 1, " ".join("h%d" % x for x in want) or "none", " ".join("h%d" % x for x in got) or "none")))
            fatal = [m for k, m in t["_problems"] if k != "review"]
            if not queued and fatal:
                errors += ["%s: %s" % (name, m) for m in fatal]
                continue
            p["_tr"][L] = t
            continue
        (orphans if queued else errors).append("%s: %s" % (name, why))
    posts.sort(key=lambda p: (p["_pub"] or p["_at"], p["slug"]), reverse=True)
    return posts, orphans, errors


def load_posts(root, queue_dir=None):
    """-> (posts sorted newest first, errors) — load_all without the queue orphans (each post still carries p["_tr"])."""
    posts, _orphans, errors = load_all(root, queue_dir)
    return posts, errors


def lang_status(p, enabled, ui_ready):
    """-> (complete, summary) for an English post. complete = every enabled language but en has a translation (published, or queued
    without problems and with copy_review) and ready UI strings. summary: 'langs 3/12 — missing: ja, … · unreviewed: ko · problems: es (structure) · ui strings: fr'."""
    have, missing, unrev, probs, ui = 1, [], [], [], []
    for L in enabled[1:]:
        t = p.get("_tr", {}).get(L)
        if not ui_ready.get(L):
            ui.append(L)
        if t is None:
            missing.append(L)
            continue
        kinds = [k for k, _ in t["_problems"] if k != "review"]
        if kinds:
            probs.append("%s (%s)" % (L, ", ".join(dict.fromkeys(kinds))))
        elif any(k == "review" for k, _ in t["_problems"]):
            unrev.append(L)
        else:
            have += 1
    parts = [("missing", missing), ("unreviewed", unrev), ("problems", probs), ("ui strings", ui)]
    text = " · ".join("%s: %s" % (k, ", ".join(v)) for k, v in parts if v)
    return not text, "langs %d/%d%s" % (have, len(enabled), " — " + text if text else "")


WORDS_TARGET = 400  # SEO guide v1 P0-9: below this -> warning
WORDS_MIN = 300     # a NEW (unpublished) manuscript below this fails the queue check (--check-queue); publishing it still goes ahead, with a WARN
CJK_CHARS_PER_WORD = 2  # guide v1: 400 words == 800 CJK characters (Hangul/Kana/Han), so 300 words == 600 characters
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]")
TITLE_LONG = 60   # SEO guide v1: a <title> over ~60 characters is cut off in results
DESC_LONG = 160
PLACEHOLDER_RE = re.compile(r"\b(?:TODO|TBD|FIXME|lorem ipsum)\b|YYYY-MM-DD|\[(?:slug|title|description)\]", re.I)


def word_count(text):
    """Words of plain text; CJK characters count CJK_CHARS_PER_WORD to a word (guide v1 conversion), everything else by whitespace."""
    cjk = len(CJK_RE.findall(text))
    return len(CJK_RE.sub(" ", text).split()) + -(-cjk // CJK_CHARS_PER_WORD)


def lint(posts, now, root=None, queue_check=False, review=True):
    """SEO guide v1, pre-publish checks on every manuscript -> (errors, warnings).
    errors (stop the build/publish): placeholder text, a stamped date in the future, a local image that does not exist.
    (Required fields, bad dates, duplicate/reserved slugs are already rejected by load_posts.)
    Body length (P0-9): every post under WORDS_TARGET words warns. A NEW manuscript (not yet published) under WORDS_MIN is an
    error only with queue_check=True (`build_journal.py --check-queue`, the pre-publish queue check); in the normal/publish path it is
    a loud "WARN:" line and publishing goes on, so the unattended publisher never silently drops a post. Published posts under WORDS_MIN only warn.
    Copy review (review=True; publish_journal.py passes False and holds such posts instead): an unpublished, non-draft manuscript without a valid
    `copy_review: iris` + `copy_review_date: YYYY-MM-DD` is an error; posts that already have `published_at` are grandfathered.
    Other warnings (never fail): <title> > TITLE_LONG, description > DESC_LONG, duplicate <title>.
    Queued translations (p["_tr"]): a format / structure / placeholder problem warns (it is held), and is an error with queue_check."""
    errors, warnings, titles = [], [], {}
    for p in sorted(posts, key=lambda x: x["slug"]):
        name = p["_src"]
        for field in ("title", "description"):
            if PLACEHOLDER_RE.search(p[field]):
                errors.append("%s: placeholder text in %s" % (name, field))
        if PLACEHOLDER_RE.search(p["_body"]):
            errors.append("%s: placeholder text in the body" % name)
        for field, value in (("published_at", p["_pub"]), ("updated", p["_updated"])):
            if value is not None and value > now and not p["draft"]:
                errors.append("%s: %s %s is in the future" % (name, field, stamp_str(value)))
        if review and unreviewed([p]):
            errors.append("%s: copy review missing — %s (add `copy_review: iris` and `copy_review_date: YYYY-MM-DD` after Iris's review)" % (name, review_problem(p)))
        img = p.get("image")
        if img and img.startswith("/") and root is not None and not (Path(root) / img.lstrip("/")).is_file():
            errors.append("%s: image %s does not exist" % (name, img))
        words = word_count(plain_text(markdown(drop_title_h1(p["_body"], p["title"]))))
        if words < WORDS_MIN and p["_pub"] is None:
            if queue_check:
                errors.append("%s: %d words — a new post needs at least %d (target %d)" % (name, words, WORDS_MIN, WORDS_TARGET))
            else:
                warnings.append("WARN: %s: only %d words (< %d minimum, target %d) — it is published anyway; fix it with an `updated:` edit" % (name, words, WORDS_MIN, WORDS_TARGET))
        elif words < WORDS_MIN:
            warnings.append("%s: %d words (< %d minimum, target %d)" % (name, words, WORDS_MIN, WORDS_TARGET))
        elif words < WORDS_TARGET:
            warnings.append("%s: %d words (< %d target)" % (name, words, WORDS_TARGET))
        shown = post_title(p["title"])
        if len(shown) > TITLE_LONG:
            warnings.append("%s: <title> is %d characters (> %d)" % (name, len(shown), TITLE_LONG))
        if len(p["description"]) > DESC_LONG:
            warnings.append("%s: description is %d characters (> %d)" % (name, len(p["description"]), DESC_LONG))
        titles.setdefault(shown, []).append(name)
    warnings += ["duplicate <title> %r in %s" % (t, ", ".join(n)) for t, n in titles.items() if len(n) > 1]
    for p in sorted(posts, key=lambda x: x["slug"]):  # queued translations: a problem holds that translation (and a new post with it)
        for t in (t for _, t in sorted(p.get("_tr", {}).items()) if t["_pub"] is None):
            for kind, msg in t["_problems"]:
                if kind == "review":  # shown on the `langs:` lines, never an error (the publisher holds it)
                    continue
                if queue_check:
                    errors.append("%s: %s" % (t["_src"], msg))
                else:
                    warnings.append("%s: %s — held until it is fixed" % (t["_src"], msg))
    import slot_rules  # late: slot_rules imports this module
    warnings += slot_rules.warn_manuscripts(posts)  # publish-slot hints (KST 12-17, 1/day); never errors: publish_at is only a floor
    return errors, warnings


def split_due(posts, now, drafts_ok=False):
    """-> (live, waiting, ready). live = stamped with published_at <= now (drafts only with drafts_ok, shown at publish_at).
    ready = waiting posts whose publish_at has passed but that publish_journal.py has not stamped yet."""
    live, waiting = [], []
    for p in posts:
        if p["draft"] and not drafts_ok:
            continue
        if p["draft"] and p["_pub"] is None:
            p["_pub"] = p["_at"]  # preview only
        (live if p["_pub"] and p["_pub"] <= now else waiting).append(p)
    ready = [p for p in waiting if p["_at"] <= now and not p["draft"]]
    return live, waiting, ready


def stamp_published(path, stamp):
    """Add `published_at: <stamp>` right after the publish_at line of a manuscript's front matter (a translation has no publish_at:
    at the end of the front matter); body untouched. False when it is already stamped."""
    text = path.read_text(encoding="utf-8")
    end = text.find("\n---", 4)
    lines = text[:end].split("\n")
    if any(l.lower().startswith("published_at:") for l in lines):
        return False
    i = next((i + 1 for i, l in enumerate(lines) if l.lower().startswith("publish_at:")), len(lines))  # a translation has none: last line
    lines.insert(i, "published_at: %s" % stamp)
    path.write_text("\n".join(lines) + text[end:], encoding="utf-8")
    return True


# ---------------------------------------------------------------- markdown (small, safe subset)
def safe_url(u):
    u = u.strip()
    if re.match(r"^(https?://|/|#|mailto:)", u):
        return u
    return "#"


def inline(text):
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append("<code>%s</code>" % esc(p[1:-1]))
            continue
        s = esc(p)
        s = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                   lambda m: '<img src="%s" alt="%s" loading="lazy" decoding="async">' % (esc(safe_url(html.unescape(m.group(2)))), m.group(1)), s)

        def link(m):
            url = safe_url(html.unescape(m.group(2)))
            ext = url.startswith("http") and not url.startswith(SITE)
            return '<a href="%s"%s>%s</a>' % (esc(url), ' rel="noopener"' if ext else "", m.group(1))
        s = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*(?![\s*])(.+?)(?<![\s*])\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])", r"<em>\1</em>", s)
        out.append(s)
    return "".join(out)


def drop_title_h1(body, title):
    """The page template owns the <h1>; a leading '# <same title>' in the manuscript would come out as a duplicate <h2>."""
    m = re.match(r"\s*#\s+(.+?)\s*\n", body)
    if m and re.sub(r"\s+", " ", m.group(1)).strip() == re.sub(r"\s+", " ", title).strip():
        return body[m.end():]
    return body


TABLE_SEP_RE = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$")


def table_cells(row):
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") else row
    return [c.strip() for c in row.split("|")]


FIG_RE = re.compile(r'^!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)$')


def markdown(src):
    lines = src.split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>%s</p>" % inline(" ".join(x.strip() for x in para)))
            para.clear()

    while i < len(lines):
        st = lines[i].strip()
        if st.startswith("```"):
            flush()
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            out.append("<pre><code>%s</code></pre>" % esc("\n".join(code)))
            i += 1
            continue
        if not st:
            flush()
            i += 1
            continue
        fm = FIG_RE.match(st)
        if fm:
            flush()
            cap = "<figcaption>%s</figcaption>" % inline(fm.group(3)) if fm.group(3) else ""
            out.append('<figure><img src="%s" alt="%s" loading="lazy" decoding="async">%s</figure>'
                       % (esc(safe_url(fm.group(2))), esc(fm.group(1)), cap))
            i += 1
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", st)
        if m:
            flush()
            level = {1: 2, 2: 2, 3: 3, 4: 4}[len(m.group(1))]  # the page template owns the <h1>
            out.append("<h%d>%s</h%d>" % (level, inline(m.group(2)), level))
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,})$", st):
            flush()
            out.append("<hr>")
            i += 1
            continue
        if st.startswith(">"):
            flush()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip()[1:].strip())
                i += 1
            out.append("<blockquote><p>%s</p></blockquote>" % inline(" ".join(quote)))
            continue
        if st.startswith("|") and i + 1 < len(lines) and TABLE_SEP_RE.match(lines[i + 1].strip()):
            flush()
            head_cells = table_cells(st)
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(table_cells(lines[i]))
                i += 1
            out.append('<div class="table-wrap"><table><thead><tr>%s</tr></thead><tbody>%s</tbody></table></div>' % (
                "".join("<th>%s</th>" % inline(c) for c in head_cells),
                "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(c) for c in r) for r in rows)))
            continue
        if re.match(r"^[-*+]\s+", st) or re.match(r"^\d+[.)]\s+", st):
            flush()
            ordered = bool(re.match(r"^\d", st))
            pat = r"^\d+[.)]\s+" if ordered else r"^[-*+]\s+"
            items = []
            while i < len(lines) and re.match(pat, lines[i].strip()):
                items.append(re.sub(pat, "", lines[i].strip()))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue
        para.append(lines[i])
        i += 1
    flush()
    return "\n".join(out)


def plain_text(html_body):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", html_body))).strip()


# ---------------------------------------------------------------- page chrome
def asset_v(root):
    f = root / CSS_REL
    try:
        return hashlib.sha1(f.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


def ld(obj):
    return '<script type="application/ld+json">\n%s\n</script>\n' % json.dumps(obj, ensure_ascii=False, indent=2).replace("</", "<\\/")


def post_path(p):
    return "/journal/%s/%s/" % (p.get("_lang", "en"), p["slug"])


def list_path(lang="en"):
    return "/journal/" if lang == "en" else "/journal/%s/" % lang


def feed_path(lang="en"):
    return list_path(lang) + "feed.xml"


def post_url(p):
    return SITE + post_path(p)


def abs_url(u):
    return SITE + u if u.startswith("/") else u


TITLE_SUFFIX = " | Pawstcard"
TITLE_MAX = 65
LIST_TITLE = EN_UI["list_title"]  # 52 chars


def post_title(title):
    """<title>: the post title plus a short brand suffix, unless that would run past ~65 chars (then the title alone)."""
    return title + TITLE_SUFFIX if len(title) + len(TITLE_SUFFIX) <= TITLE_MAX else title


def hero(p):
    return abs_url(p["image"]) if p.get("image") else DEFAULT_OG_IMAGE


def hero_object(p):
    """JSON-LD image: ImageObject. Only the default og-image has known dimensions; a per-post image carries its url only."""
    return dict(OG_IMAGE) if not p.get("image") else {"@type": "ImageObject", "url": hero(p)}


def txt(s):
    """escape for a text node (quotes are left as they are)"""
    return html.escape(str(s), quote=False)


def lang_menu(lang, S, versions):
    """The header's language slot and its data (JOURNAL_I18N.md §6). This repo renders no control: webkit v0.7.2 fills the slot.
    options = the language versions this page really has, in languages.SUPPORTED order."""
    data = {"current": lang, "label": S["lang_label"],
            "options": [{"lang": L, "name": LANGS.NAMES[L], "href": path} for L, path in versions]}
    return ('      <span class="lang-slot" data-ipe-lang-slot></span>\n'
            '      <script type="application/json" id="ipe-langs">%s</script>\n' % json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def head(title, desc, canonical, v, noindex=False, extra="", og_type="website", image=None, alternates="", image_alt=None,
         lang="en", S=None, versions=None):
    """<head> + site header. lang / S (that language's UI strings, default English) / versions ([(lang, path)] of this page,
    default just this one) drive <html lang>, og:locale(:alternate), the RSS link, the nav texts and the #ipe-langs data."""
    S = S or EN_UI
    versions = versions or [(lang, canonical[len(SITE):] if canonical.startswith(SITE) else canonical)]
    locale = ('<meta property="og:locale" content="%s">\n' % LANGS.OG_LOCALE[lang]
              + "".join('<meta property="og:locale:alternate" content="%s">\n' % LANGS.OG_LOCALE[L] for L, _ in versions if L != lang))
    # same text as the landing page's og:image:alt; width/height are only known for the default /og-image.png
    image = image or DEFAULT_OG_IMAGE
    if image == DEFAULT_OG_IMAGE:
        size = ('<meta property="og:image:width" content="%d">\n<meta property="og:image:height" content="%d">\n'
                % OG_IMAGE_SIZE)
        image_alt = image_alt or S["og_image_alt"]
    else:
        size = ""
        image_alt = image_alt or title
    robots = "noindex, follow" if noindex else "index, follow, max-image-preview:large"
    return f"""<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<!-- {GEN_MARK} — do not hand-edit; edit journal/posts/*.md and rebuild -->
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="{robots}">
<meta name="theme-color" content="#2E5941">
<link rel="canonical" href="{esc(canonical)}">
{alternates}<link rel="alternate" type="application/rss+xml" title="{esc(S['blog_name'])}" href="{SITE}{feed_path(lang)}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="Pawstcard">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
<meta property="og:image" content="{esc(image)}">
{size}<meta property="og:image:alt" content="{esc(image_alt)}">
{locale}<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<meta name="twitter:image" content="{esc(image)}">
<meta name="twitter:image:alt" content="{esc(image_alt)}">
{extra}
<!-- reused ipe.rest GA4 property; filter reports by hostname=pawstcard.ipe.rest (same tag as the landing page) -->
<script async src="https://www.googletagmanager.com/gtag/js?id={GA_ID}"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{dataLayer.push(arguments);}}
  gtag('js', new Date());
  gtag('config', '{GA_ID}');
</script>

<!-- Meta Pixel (same pixel as the landing page) -->
<script>
!function(f,b,e,v,n,t,s)
{{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '{PIXEL_ID}');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id={PIXEL_ID}&ev=PageView&noscript=1"/></noscript>
<!-- End Meta Pixel -->

<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="192x192" href="/icon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/{CSS_REL}?v={v}">
<!-- Cloudflare Web Analytics -->
<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{{"token": "{CF_TOKEN}"}}'></script>
<!-- End Cloudflare Web Analytics -->
</head>
<body>
<header class="wrap">
  <nav class="nav">
    <a class="logo" href="/"><span class="paw">🐾</span>Pawstcard</a>
    <span class="nav-links">
      <a class="nav-journal" href="{list_path(lang)}">{txt(S['nav_journal'])}</a>
{lang_menu(lang, S, versions)}      <a class="cta-mini" href="/#signup">{txt(S['nav_cta'])}</a>
    </span>
  </nav>
</header>
"""


# ipe-localtime v2 — canonical copy of ipe-rest/shared/ipe-localtime.js (SHA-256 57326449…f74b8), kept byte-for-byte and
# inlined before </body>. Never edit it here; replace the file with the next canonical version and update the hash in tests.
LOCALTIME_JS_PATH = Path(__file__).resolve().parent / "ipe-localtime.js"
LOCALIZE_JS = "<script>" + LOCALTIME_JS_PATH.read_bytes().decode("utf-8") + "</script>\n"


def footer(lang="en", S=None):
    S = {k: txt(x) for k, x in (S or EN_UI).items()}
    return f"""<footer>
  <div class="wrap">
    <p>{S['footer_tagline']}</p>
    <p class="foot-links"><a href="/">{S['footer_home']}</a> · <a href="{list_path(lang)}">{S['footer_journal']}</a> · <a href="{feed_path(lang)}">{S['footer_rss']}</a> · <a href="/#signup">{S['footer_waitlist']}</a> · <a href="/privacy/">{S['footer_privacy']}</a> · <a href="/terms/">{S['footer_terms']}</a></p>
  </div>
</footer>
""" + LOCALIZE_JS + """</body>
</html>
"""


def breadcrumb(name=None, url=None, lang="en", S=None):
    items = [("Pawstcard", SITE + "/"), ((S or EN_UI)["list_h1"], SITE + list_path(lang))] + ([(name, url)] if name else [])
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}


def alt_links(versions):
    """hreflang <link>s: one per language version, then x-default = the English one. versions = [(lang, path)] or one English URL."""
    if isinstance(versions, str):
        versions = [("en", versions[len(SITE):] if versions.startswith(SITE) else versions)]
    en = abs_url(dict(versions).get("en", versions[0][1]))
    return ("".join('<link rel="alternate" hreflang="%s" href="%s">\n' % (LANGS.hreflang(L), esc(abs_url(u))) for L, u in versions)
            + '<link rel="alternate" hreflang="x-default" href="%s">\n' % esc(en))


# ---------------------------------------------------------------- pages
RELATED_POSTS = 3  # "More from the journal": the newest N other posts


def post_links(p, posts, S=None):
    """Previous / next post (older / newer neighbour in `posts`, newest first) and the newest RELATED_POSTS others, as HTML.
    `posts` = the live posts of p's language; S = that language's UI strings."""
    S = S or EN_UI
    i = next((k for k, x in enumerate(posts) if x["slug"] == p["slug"]), None)
    if i is None or len(posts) < 2:
        return ""
    newer = posts[i - 1] if i > 0 else None
    older = posts[i + 1] if i + 1 < len(posts) else None
    cell = lambda cls, label, q: ('<a class="%s" href="%s" rel="%s"><span class="post-nav__label">%s</span><span class="post-nav__title">%s</span></a>'
                                  % (cls, post_path(q), "prev" if cls.endswith("prev") else "next", txt(label), esc(q["title"])))
    nav = ""
    if older or newer:
        nav = ('    <nav class="post-nav" aria-label="%s">\n' % esc(S["post_nav_aria"])
               + ("      " + cell("post-nav__prev", S["post_prev"], older) + "\n" if older else "")
               + ("      " + cell("post-nav__next", S["post_next"], newer) + "\n" if newer else "")
               + "    </nav>\n")
    others = [q for q in posts if q["slug"] != p["slug"]][:RELATED_POSTS]
    items = "\n".join('        <li><a href="%s">%s</a></li>' % (post_path(q), esc(q["title"])) for q in others)
    related = ('    <section class="related" aria-labelledby="related-h">\n      <h2 id="related-h">%s</h2>\n      <ul>\n%s\n      </ul>\n    </section>\n'
               % (txt(S["related_h"]), items)) if others else ""
    return nav + related


def render_post(p, v, posts=(), S=None):
    """One post page. p is an English post or a translation view (tr_view); posts = the live posts of its language, S = its UI strings."""
    S = S or EN_UI
    lang = p.get("_lang", "en")
    versions = p.get("_versions") or [(lang, post_path(p))]
    url = post_url(p)
    modified = p["_updated"] or p["_pub"]
    data = {
        "@context": "https://schema.org", "@type": "BlogPosting",
        "headline": p["title"], "description": p["description"],
        "datePublished": iso_sec(p["_pub"]), "dateModified": iso_sec(modified),
        "inLanguage": lang,
        "mainEntityOfPage": {"@type": "WebPage", "@id": url}, "url": url,
        "image": hero_object(p),
        "wordCount": word_count(plain_text(p["_html"])),
        "author": dict(ORG),
        "publisher": dict(ORG, logo=dict(APP_ICON)),
        "isPartOf": {"@type": "Blog", "name": S["blog_name"], "url": SITE + list_path(lang)},
    }
    if lang != "en":
        data["translationOfWork"] = {"@type": "BlogPosting", "url": abs_url(versions[0][1]), "inLanguage": "en"}
    elif len(versions) > 1:
        data["workTranslation"] = [{"@type": "BlogPosting", "url": abs_url(u), "inLanguage": L} for L, u in versions[1:]]
    if p.get("category"):
        data["articleSection"] = p["category"]
    if p["_keywords"]:
        data["keywords"] = ", ".join(p["_keywords"])
    extra = ('<meta property="article:published_time" content="%s">\n<meta property="article:modified_time" content="%s">\n'
             % (iso_sec(p["_pub"]), iso_sec(modified))
             + ('<meta property="article:section" content="%s">\n' % esc(p["category"]) if p.get("category") else "")
             + "".join('<meta property="article:tag" content="%s">\n' % esc(k) for k in p["_keywords"])
             + ld(data) + ld(breadcrumb(p["title"], url, lang, S)))
    cat = ' <span aria-hidden="true">·</span> <span>%s</span>' % esc(p["category"]) if p.get("category") else ""
    hero_img = ('    <figure class="hero-img"><img src="%s" alt="%s"></figure>\n' % (esc(p["image"]), esc(p.get("image_alt", "")))
                if p.get("image") else "")
    return (head(post_title(p["title"]), p["description"], url, v, p["draft"], extra, "article", hero(p), alt_links(versions),
                 p.get("image_alt") if p.get("image") else None, lang, S, versions)
            + f"""<main class="wrap article-wrap">
  <article class="article">
    <header class="article-head">
      <p class="j-meta"><a href="{list_path(lang)}">{txt(S['list_h1'])}</a> <span aria-hidden="true">·</span> <time datetime="{stamp_str(p['_pub'])}" data-ipe-time>{fmt_date(p['_pub'])}</time>{cat}{' <span class="draft-flag">DRAFT</span>' if p['draft'] else ''}</p>
      <h1>{esc(p['title'])}</h1>
      <p class="lede">{esc(p['description'])}</p>
    </header>
{hero_img}    <div class="prose">
{p['_html']}
    </div>
    <aside class="waitlist-cta" aria-label="{esc(S['cta_aria'])}">
      <h2>{txt(S['post_cta_h'])}</h2>
      <p>{txt(S['post_cta_p'])}</p>
      <a class="btn" href="/#signup">{txt(S['cta_button'])}</a>
    </aside>
{post_links(p, posts, S)}    <p class="back"><a href="{list_path(lang)}"><span aria-hidden="true">←</span> {txt(S['back_all'])}</a></p>
  </article>
</main>
""" + footer(lang, S))


def render_list(posts, v, lang="en", S=None, versions=None):
    """The list page of one language. versions = [(lang, list path)] of every language that has a list (hreflang + #ipe-langs)."""
    S = S or EN_UI
    url = SITE + list_path(lang)
    versions = versions or [(lang, list_path(lang))]
    data = {"@context": "https://schema.org", "@type": "Blog", "name": S["blog_name"], "url": url,
            "description": S["blog_desc"], "inLanguage": lang, "publisher": dict(ORG, logo=dict(APP_ICON)),
            "blogPost": [{"@type": "BlogPosting", "headline": p["title"], "url": post_url(p),
                          "datePublished": iso_sec(p["_pub"]), "inLanguage": lang,
                          "description": p["description"], "image": hero_object(p), "author": {"@id": ORG_ID}} for p in posts]}
    itemlist = {"@context": "https://schema.org", "@type": "ItemList", "name": S["blog_name"], "url": url,
                "numberOfItems": len(posts), "itemListOrder": "https://schema.org/ItemListOrderDescending",
                "itemListElement": [{"@type": "ListItem", "position": i + 1, "url": post_url(p), "name": p["title"]}
                                    for i, p in enumerate(posts)]}
    if posts:
        items = "\n".join(f"""      <li>
        <p class="j-meta"><time datetime="{stamp_str(p['_pub'])}" data-ipe-time>{fmt_date(p['_pub'])}</time>{' · ' + esc(p['category']) if p.get('category') else ''}</p>
        <h2><a href="{post_path(p)}">{esc(p['title'])}</a></h2>
        <p>{esc(p['description'])}</p>
      </li>""" for p in posts)
        body = '    <ol class="j-list">\n%s\n    </ol>' % items
    else:
        body = '    <p class="empty-note">%s</p>' % txt(S["list_empty"])
    return (head(S["list_title"], S["blog_desc"], url, v, not posts,
                 ld(data) + ld(itemlist) + ld(breadcrumb(lang=lang, S=S)), alternates=alt_links(versions),
                 lang=lang, S=S, versions=versions)
            + f"""<main class="wrap list-wrap">
  <div class="page-head">
    <h1>{txt(S['list_h1'])}</h1>
    <p class="lede">{esc(S['blog_desc'])}</p>
  </div>
{body}
  <aside class="waitlist-cta" aria-label="{esc(S['cta_aria'])}">
    <h2>{txt(S['list_cta_h'])}</h2>
    <p>{txt(S['list_cta_p'])}</p>
    <a class="btn" href="/#signup">{txt(S['cta_button'])}</a>
  </aside>
</main>
""" + footer(lang, S))


def rfc822(d):
    return kst(d).strftime("%a, %d %b %Y %H:%M:%S %z")


def render_feed(posts, now, lang="en", S=None):
    S = S or EN_UI
    items = "\n".join(f"""    <item>
      <title>{esc(p['title'])}</title>
      <link>{post_url(p)}</link>
      <guid isPermaLink="true">{post_url(p)}</guid>
      <pubDate>{rfc822(p['_pub'])}</pubDate>{'' if not p.get('category') else chr(10) + '      <category>' + esc(p['category']) + '</category>'}
      <description>{esc(p['description'])}</description>
    </item>""" for p in posts)
    last = rfc822(max((p["_updated"] or p["_pub"]) for p in posts)) if posts else rfc822(now)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(S['blog_name'])}</title>
    <link>{SITE}{list_path(lang)}</link>
    <atom:link href="{SITE}{feed_path(lang)}" rel="self" type="application/rss+xml"/>
    <description>{esc(S['blog_desc'])}</description>
    <language>{lang}</language>
    <lastBuildDate>{last}</lastBuildDate>
{items}
  </channel>
</rss>
"""


# ---------------------------------------------------------------- landing page: Journal card section
def render_home_block(posts):
    """The card section for the landing page (static HTML, no JS of its own), placed BELOW the signup section so it cannot pull
    visitors away from the Meta-ad -> email conversion. `posts` = published posts; newest HOME_CARDS shown.
    Each card: art tile (the landing's own .ph1-.ph3 gradients, picked by slug so a post keeps its colour), <time data-ipe-time>
    (localised by the ipe-localtime v2 script inlined in index.html), title link stretched over the whole card, 3-line summary.
    The grid modifier carries the card count (jgrid--1/2/3): one post = one wide horizontal card, two = two columns, three = three."""
    top = sorted(posts, key=lambda p: (p["_pub"], p["slug"]), reverse=True)[:HOME_CARDS]
    if not top:
        return ""
    cards = "\n".join(f"""      <li class="jcard">
        <div class="jart ph{1 + sum(p['slug'].encode()) % 3}" aria-hidden="true">🐾</div>
        <div class="jbody">
          <p class="jmeta"><time datetime="{stamp_str(p['_pub'])}" data-ipe-time>{fmt_date(p['_pub'])}</time></p>
          <h3><a class="jlink" href="{post_path(p)}">{esc(p['title'])}</a></h3>
          <p class="jex">{esc(p['description'])}</p>
          <span class="jmore" aria-hidden="true">Read the post →</span>
        </div>
      </li>""" for p in top)
    return f"""  <section class="jsec wrap" id="journal" aria-labelledby="jsec-h">
    <h2 id="jsec-h">From the Journal</h2>
    <p class="sub">Practical notes for independent pet sitters — while you wait for your invite.</p>
    <ol class="jgrid jgrid--{len(top)}">
{cards}
    </ol>
    <p class="jall"><a href="/journal/">All posts <span aria-hidden="true">→</span></a></p>
  </section>
"""


def merge_home(text, block):
    """Replace the block between the home markers (markers stay on their own lines). The markers MUST exist."""
    if HOME_START not in text or HOME_END not in text or text.index(HOME_START) > text.index(HOME_END):
        raise ValueError("index.html: markers %s ... %s not found (the landing card section cannot be updated)" % (HOME_START, HOME_END))
    s = text.index(HOME_START)
    s = text.find("\n", s) + 1
    e = text.index(HOME_END)
    e = text.rfind("\n", 0, e) + 1
    return text[:s] + block + text[e:]


def home_slugs(text):
    """slugs of the cards currently in index.html's home block, in page order"""
    s, e = text.index(HOME_START), text.index(HOME_END)
    return re.findall(r'<a class="jlink" href="/journal/en/([a-z0-9-]+)/"', text[s:e])


def check_home(root, posts_live):
    """-> list of error strings. index.html's card block must be exactly the newest HOME_CARDS published posts."""
    idx = Path(root) / "index.html"
    if not idx.exists():
        return []  # a site root without a landing page (tests / previews)
    text = idx.read_text(encoding="utf-8")
    try:
        want = merge_home(text, render_home_block(posts_live))
    except ValueError as ex:
        return [str(ex)]
    if want == text:
        return []
    top = [p["slug"] for p in sorted(posts_live, key=lambda p: (p["_pub"], p["slug"]), reverse=True)[:HOME_CARDS]]
    got = home_slugs(text)
    if got != top:
        return ["index.html: main-page cards are %s but the newest published posts are %s — run scripts/build_journal.py" % (got or "none", top or "none")]
    return ["index.html: the journal card block is out of date (same posts, different text) — run scripts/build_journal.py"]


# ---------------------------------------------------------------- sitemap / llms.txt
def render_sitemap_block(posts, views=None):
    """Journal <url> rows: the list pages (en, then every language with live posts), then each English post followed by its
    live translations. Every row lists all versions of its page as xhtml:link hreflang + x-default (= English)."""
    if not posts:
        return ""
    views = views or {}
    xl = lambda versions: ("".join('    <xhtml:link rel="alternate" hreflang="%s" href="%s"/>\n' % (LANGS.hreflang(L), abs_url(u)) for L, u in versions)
                           + '    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>\n' % abs_url(versions[0][1]))
    hubs = [("en", list_path())] + [(L, list_path(L)) for L in LANGS.SUPPORTED[1:] if views.get(L)]
    rows = ["  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <changefreq>daily</changefreq>\n    <priority>0.6</priority>\n%s  </url>"
            % (abs_url(u), newest_modified(views[L] if L != "en" else posts), xl(hubs)) for L, u in hubs]
    view_of = {(q["_lang"], q["slug"]): q for vs in views.values() for q in vs}
    for p in posts:
        versions = p.get("_versions") or [("en", post_path(p))]
        for L, u in versions:
            q = p if L == "en" else view_of[(L, p["slug"])]
            rows.append("  <url>\n    <loc>%s</loc>\n    <lastmod>%s</lastmod>\n    <priority>0.5</priority>\n%s"
                        "    <image:image>\n      <image:loc>%s</image:loc>\n    </image:image>\n  </url>"
                        % (abs_url(u), iso_sec(q["_updated"] or q["_pub"]), xl(versions), esc(hero(p))))
    return "\n".join(rows) + "\n"


def newest_modified(posts):
    return iso_sec(max(p["_updated"] or p["_pub"] for p in posts)) if posts else None


def root_hreflang_sitemap():
    u = SITE + "/"
    return ('    <xhtml:link rel="alternate" hreflang="en" href="%s"/>\n'
            '    <xhtml:link rel="alternate" hreflang="x-default" href="%s"/>\n' % (u, u))


def merge_sitemap(text, block, home_lastmod=None):
    """Replace the journal block; insert the markers before </urlset> on first run. Everything else is left byte-for-byte,
    except the landing page's <lastmod>, which follows the newest post (the home page shows the newest cards)."""
    new = "  %s\n%s  %s\n" % (SM_START, block, SM_END)
    if SM_START in text and SM_END in text:
        s = text.index(SM_START)
        e = text.index(SM_END) + len(SM_END)
        s = text.rfind("\n", 0, s) + 1  # start of the marker's line (keeps its indentation out of the replaced text)
        e = text.find("\n", e) + 1 if text.find("\n", e) != -1 else len(text)
        text = text[:s] + new + text[e:]
    else:
        if "</urlset>" not in text:
            raise ValueError("sitemap.xml has no </urlset>")
        text = text.replace("</urlset>", new + "</urlset>", 1)
    if home_lastmod:
        text = re.sub(r"(<loc>%s/</loc>\s*<lastmod>)[^<]*(</lastmod>)" % re.escape(SITE), lambda m: m.group(1) + home_lastmod + m.group(2), text, count=1)
    if block:  # the landing entry carries en + x-default like every journal entry (same URL as its <loc>; sitemap addresses unchanged)
        text = re.sub(r"(<loc>%s/</loc>(?:(?!</url>).)*?)(\n?[ \t]*</url>)" % re.escape(SITE),
                      lambda m: m.group(0) if "<xhtml:link" in m.group(1) else m.group(1).rstrip("\n") + "\n" + root_hreflang_sitemap() + m.group(2).lstrip("\n"),
                      text, count=1, flags=re.S)
    for prefix, ns in (("xhtml", XHTML_NS), ("image", IMG_NS)):
        if block and ("xmlns:%s=" % prefix) not in text:
            text = text.replace("<urlset ", '<urlset xmlns:%s="%s"\n        ' % (prefix, ns), 1)
    return text


def render_llms_block(posts, views=None):
    if not posts:
        return ""
    lines = ["## Journal",
             "Practical notes for independent pet sitters and dog walkers. Index: %s/journal/ · Feed: %s/journal/feed.xml" % (SITE, SITE), ""]
    langs = [L for L in LANGS.SUPPORTED[1:] if (views or {}).get(L)]
    if langs:
        lines.insert(2, "Translations: " + " · ".join("%s %s%s" % (LANGS.NAMES[L], SITE, list_path(L)) for L in langs))
    lines += ["- [%s](%s) — %s (%s)" % (p["title"], post_url(p), p["description"], ymd(p["_pub"])) for p in posts]
    return "\n".join(lines) + "\n"


def merge_llms(text, block):
    """Replace the journal block; first run inserts it before '## Usage' (else appends). The rest is untouched."""
    new = "%s\n%s%s\n" % (LLMS_START, block, LLMS_END)
    if LLMS_START in text and LLMS_END in text:
        s = text.index(LLMS_START)
        e = text.index(LLMS_END) + len(LLMS_END)
        e = text.find("\n", e) + 1 if text.find("\n", e) != -1 else len(text)
        return text[:s] + new + text[e:]
    m = re.search(r"^## Usage\b", text, re.M)
    if m:
        return text[:m.start()] + new + "\n" + text[m.start():]
    return text.rstrip("\n") + "\n\n" + new


# ---------------------------------------------------------------- build
def sweep_generated(root, written):
    """delete pages (and non-English feeds) this script generated earlier that are no longer due / were removed, and empty dirs."""
    gone = []
    for L in LANGS.SUPPORTED:
        base = root / "journal" / L
        if not base.is_dir():
            continue
        for idx in sorted(base.rglob("index.html")):
            if idx not in written and GEN_MARK in idx.read_text(encoding="utf-8"):
                idx.unlink()
                gone.append(idx)
        feed = base / "feed.xml"
        if L != "en" and feed.is_file() and feed not in written and "<rss" in feed.read_text(encoding="utf-8"):
            feed.unlink()
            gone.append(feed)
        for d in sorted((x for x in base.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
        if not any(base.iterdir()):
            base.rmdir()
    return gone


def tr_view(p, t):
    """The page of translation t of the live English post p. Inherited from English: image, publish_at. Not inherited (never an English
    fallback on a translated page): category, tags (the translation's own `tags:` or none)."""
    return {"slug": p["slug"], "_lang": t["_lang"], "title": t["title"], "description": t["description"],
            "image": p.get("image"), "image_alt": t.get("image_alt", ""), "_at": p["_at"], "_pub": t["_pub"], "_updated": t["_updated"],
            "_keywords": t["_keywords"] or [], "draft": False, "_body": t["_body"], "_src": t["_src"], "_en": p}


def attach_translations(due, now, ready):
    """-> {lang: translation views, newest first} of the translations that are live: stamped (published_at <= now), their English post
    is live and not a draft, and the language's UI strings are ready. Sets p["_versions"] = [(lang, path)] (en first, SUPPORTED order)
    on every live English post; its views share that list."""
    views = {}
    for p in due:
        p["_versions"] = [("en", post_path(p))]
        if p["draft"]:
            continue
        for L in LANGS.SUPPORTED[1:]:
            t = p.get("_tr", {}).get(L)
            if t and ready.get(L) and t["_pub"] and t["_pub"] <= now:
                q = tr_view(p, t)
                q["_versions"] = p["_versions"]
                views.setdefault(L, []).append(q)
                p["_versions"].append((L, post_path(q)))
    return {L: sorted(views[L], key=lambda q: (q["_pub"], q["slug"]), reverse=True) for L in LANGS.SUPPORTED if L in views}


def build(root, now, drafts_ok=False, check_only=False, queue_dir=None):
    """Build the journal into `root` as of `now` (aware datetime). Returns a dict report; raises JournalError on bad manuscripts
    or broken i18n files."""
    root = Path(root).resolve()
    now = now.astimezone(dt.timezone.utc)  # all comparisons are between UTC instants
    ui, ui_ready, ui_errors, ui_warnings = load_ui(root)
    posts, orphans, errors = load_all(root, queue_dir)
    if ui_errors + errors:
        raise JournalError(ui_errors + errors)
    due, waiting, ready = split_due(posts, now, drafts_ok)
    views = attach_translations(due, now, ui_ready)
    report = {"due": [p["slug"] for p in due], "_live": due, "_all": posts, "waiting": [(p["slug"], p["publish_at"]) for p in waiting],
              "ready": [p["slug"] for p in ready],
              "new": [p["slug"] for p in due if not (root / post_path(p).strip("/") / "index.html").exists()],
              "translations": {L: [q["slug"] for q in vs] for L, vs in views.items()},
              "_views": views, "_orphans": orphans, "_ui_warnings": ui_warnings, "_ui_ready": ui_ready, "_enabled": enabled_langs(root)}
    if check_only:
        return report
    v = asset_v(root)
    for q in due + [q for vs in views.values() for q in vs]:
        q["_html"] = markdown(drop_title_h1(q["_body"], q["title"]))
    written = set()

    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.add(path)

    hubs = [("en", list_path())] + [(L, list_path(L)) for L in views]
    for p in due:
        write(root / post_path(p).strip("/") / "index.html", render_post(p, v, due))
    write(root / "journal" / "index.html", render_list(due, v, versions=hubs))
    (root / "journal" / "feed.xml").write_text(render_feed(due, now), encoding="utf-8")
    for L, vs in views.items():
        for q in vs:
            write(root / post_path(q).strip("/") / "index.html", render_post(q, v, vs, ui[L]))
        write(root / "journal" / L / "index.html", render_list(vs, v, L, ui[L], hubs))
        write(root / "journal" / L / "feed.xml", render_feed(vs, now, L, ui[L]))
    sweep_generated(root, written)

    sm = root / "sitemap.xml"
    sm.write_text(merge_sitemap(sm.read_text(encoding="utf-8"), render_sitemap_block(due, views), newest_modified(due)), encoding="utf-8")
    llms = root / "llms.txt"
    llms.write_text(merge_llms(llms.read_text(encoding="utf-8"), render_llms_block(due, views)), encoding="utf-8")

    idx = root / "index.html"  # the landing page's card section (only this block changes)
    if idx.exists():
        idx.write_text(merge_home(idx.read_text(encoding="utf-8"), render_home_block(due)), encoding="utf-8")
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parent.parent), help="site root (default: this repo)")
    ap.add_argument("--now", help="clock as ISO 8601 with offset, e.g. 2026-10-25T07:13-04:00 (default: real clock)")
    ap.add_argument("--drafts", action="store_true", help="include draft posts (preview only — never commit the result)")
    ap.add_argument("--check", action="store_true", help="validate manuscripts only, write nothing")
    ap.add_argument("--check-queue", action="store_true", help="--check, and a NEW manuscript under %d words is an error (the pre-publish queue check; never used by the publisher)" % WORDS_MIN)
    ap.add_argument("--queue", default=str(default_queue_dir()), help="unpublished manuscripts (outside the repo); default ~/pawstcard-journal-queue or $%s" % QUEUE_ENV)
    a = ap.parse_args(argv)
    try:
        now = parse_now(a.now) if a.now else dt.datetime.now(dt.timezone.utc)
        a.check = a.check or a.check_queue
        rep = build(a.root, now, a.drafts, a.check, a.queue)
        problems, warnings = lint(rep["_all"], now.astimezone(dt.timezone.utc), Path(a.root).resolve(), a.check_queue)
        if a.check_queue:  # a queued translation that belongs nowhere is an error only in the queue check
            problems += rep["_orphans"]
        else:
            warnings = ["%s — ignored until it is fixed" % o for o in rep["_orphans"]] + warnings
        if problems:
            raise JournalError(problems)
        if a.check and not a.drafts:  # the landing page's card block must match the published posts
            problems = check_home(Path(a.root).resolve(), rep["_live"])
            if problems:
                raise JournalError(problems)
    except (JournalError, ValueError) as ex:
        print("journal: errors\n  " + "\n  ".join(getattr(ex, "errors", [str(ex)])), file=sys.stderr)
        return 1
    for w in rep["_ui_warnings"] + warnings:
        print("  " + (w if w.startswith("WARN:") else "warning: " + w))
    print("journal: %s — %d published, %d scheduled (now %s = %s)" % ("OK" if a.check else "built", len(rep["due"]), len(rep["waiting"]), stamp_str(now), et_stamp_str(now)))
    for slug, at in rep["waiting"]:
        print("  waiting: %s @ %s%s" % (slug, at, "  (due — run scripts/publish_journal.py to stamp it)" if slug in rep["ready"] else ""))
    enabled = rep["_enabled"]
    if len(enabled) > 1:  # the 12-language gate (publish_journal.py holds a new post until every language is there and reviewed)
        for p in rep["_all"]:
            if p["_pub"] is None and not p["draft"]:
                print("  langs: %s %s" % (p["slug"], lang_status(p, enabled, rep["_ui_ready"])[1]))
        if rep["translations"]:
            print("  translations live: " + ", ".join("%s %d" % (L, len(s)) for L, s in rep["translations"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
