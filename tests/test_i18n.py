"""The 12-language journal (design: _ipe/foundry/F-016_pawstcard/web/JOURNAL_I18N.md):  python3 -m unittest discover -s tests -v"""
import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_journal as bj  # noqa: E402
import journal_langs as jl  # noqa: E402
import languages as LANGS  # noqa: E402
import publish_journal as pj  # noqa: E402
from test_build_journal import Site  # noqa: E402

KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime(2026, 11, 14, 14, 30, tzinfo=KST)  # inside the slot window
DUE = "2026-11-13T07:00-05:00"
KO_UI = dict(bj.EN_UI, list_h1="저널", nav_journal="저널", blog_name="Pawstcard 저널", post_prev="← 이전 글")


def ui(s, lang, strings=None, review=True):
    """i18n/<lang>.json in the site root: ready by default (every string filled + copy_review)."""
    d = s.root / "i18n"
    d.mkdir(exist_ok=True)
    data = {"_meta": {"lang": lang, "copy_review": "iris" if review else "", "copy_review_date": "2026-11-10" if review else ""}}
    data.update(strings if strings is not None else (KO_UI if lang == "ko" else {k: "%s %s" % (lang, v) for k, v in bj.EN_UI.items()}))
    (d / (lang + ".json")).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def tr(s, slug, code, where="queue", body="# 제목\n\n번역된 본문입니다.\n", **extra):
    """<slug>.<lang>.md: reviewed, in the queue (where="queue") or published in journal/posts/ (where="posts", stamped)."""
    fm = {"slug": slug, "lang": code, "translation_of": slug, "title": "%s title (%s)" % (slug, code), "description": "%s about %s." % (code, slug),
          "copy_review": "iris", "copy_review_date": "2026-11-12"}
    if where == "posts":
        fm["published_at"] = "2026-11-13T21:00+09:00"
    fm.update(extra)
    d = s.root / "journal" / where
    d.mkdir(parents=True, exist_ok=True)
    text = "---\n" + "\n".join("%s: %s" % kv for kv in fm.items() if kv[1] is not None) + "\n---\n\n" + body
    (d / ("%s.%s.md" % (slug, code))).write_text(text, encoding="utf-8")
    return d / ("%s.%s.md" % (slug, code))


def publish(s, **kw):
    lines = []
    rc = pj.run(s.root, NOW, out=lines.append, slot_gates=kw.pop("slot_gates", True), **kw)
    return rc, "\n".join(lines)


class Languages(unittest.TestCase):
    def test_the_twelve_in_kit_order(self):  # ipe_web_kit v0.7.1 languages.py
        self.assertEqual(LANGS.SUPPORTED, ("en", "ko", "ja", "zh-Hant", "es", "pt-BR", "fr", "de", "id", "th", "vi", "tr"))
        self.assertEqual(LANGS.DEFAULT, "en")
        for gone in ("zh", "pt", "zh-Hans", "ru", "ar", "hi"):
            self.assertNotIn(gone, LANGS.SUPPORTED)
            with self.assertRaises(ValueError):
                LANGS.hreflang(gone)
        self.assertEqual(set(LANGS.NAMES), set(LANGS.SUPPORTED))
        self.assertEqual(set(LANGS.OG_LOCALE), set(LANGS.SUPPORTED))

    def test_resolve(self):
        for tag, want in (("ko-KR", "ko"), ("zh-TW", "zh-Hant"), ("zh-Hant-HK", "zh-Hant"), ("zh-CN", "en"), ("zh", "en"), ("pt-PT", "pt-BR"),
                          ("pt", "pt-BR"), ("in", "id"), ("ja_JP", "ja"), ("ru", "en"), ("", "en"), (None, "en"), ("DE-at", "de")):
            self.assertEqual(LANGS.resolve(tag), want, tag)


class RepoStrings(unittest.TestCase):
    def test_exactly_twelve_files_with_the_same_keys(self):
        files = sorted(p.name for p in (REPO / "i18n").glob("*"))
        self.assertEqual(files, sorted(L + ".json" for L in LANGS.SUPPORTED))
        for L in LANGS.SUPPORTED:
            data = json.loads((REPO / "i18n" / (L + ".json")).read_text(encoding="utf-8"))
            self.assertEqual(set(data) - {"_meta"}, set(bj.UI_KEYS), L)
            self.assertEqual(data["_meta"]["lang"], L)

    def test_repo_builds_with_one_grouped_warning_and_no_errors(self):
        _s, ready, errors, warnings = bj.load_ui(REPO)
        self.assertEqual(errors, [])
        not_ready = [L for L in LANGS.SUPPORTED if not ready.get(L)]
        if not_ready:  # untranslated files share one line, not eleven
            self.assertLessEqual(len(warnings), len(not_ready))
            self.assertTrue(all("new posts wait" in w for w in warnings))
        self.assertTrue(ready["en"])


class UiFiles(unittest.TestCase):
    def test_ready_and_empty(self):
        s = Site(self)
        ui(s, "ko")
        ui(s, "ja", {k: "" for k in bj.UI_KEYS}, review=False)
        strings, ready, errors, warnings = bj.load_ui(s.root)
        self.assertEqual(errors, [])
        self.assertTrue(ready["ko"])
        self.assertFalse(ready["ja"])
        self.assertEqual(strings["ko"]["list_h1"], "저널")
        self.assertEqual(len(warnings), 1)
        self.assertIn("i18n/ja.json: %d of %d strings empty" % (len(bj.UI_KEYS), len(bj.UI_KEYS)), warnings[0])
        self.assertEqual(bj.enabled_langs(s.root), ["en", "ko", "ja"])

    def test_two_languages_with_the_same_problem_are_one_line(self):
        s = Site(self)
        for L in ("ja", "fr"):
            ui(s, L, {k: "" for k in bj.UI_KEYS}, review=False)
        _s, _r, _e, warnings = bj.load_ui(s.root)
        self.assertEqual(len(warnings), 1)
        self.assertIn("i18n/{ja,fr}.json", warnings[0])

    def test_placeholder_or_no_review_is_not_ready(self):
        s = Site(self)
        ui(s, "ko", dict(KO_UI, list_h1="TODO"))
        ui(s, "de", review=False)
        _s, ready, errors, warnings = bj.load_ui(s.root)
        self.assertEqual(errors, [])
        self.assertFalse(ready["ko"])
        self.assertFalse(ready["de"])
        self.assertIn("placeholder text in list_h1", "\n".join(warnings))

    def test_errors(self):
        s = Site(self)
        (s.root / "i18n").mkdir()
        (s.root / "i18n" / "zh.json").write_text("{}", encoding="utf-8")
        ui(s, "ko", {k: v for k, v in KO_UI.items() if k != "nav_cta"})
        (s.root / "i18n" / "ja.json").write_text("{not json", encoding="utf-8")
        _s, _r, errors, _w = bj.load_ui(s.root)
        text = "\n".join(errors)
        self.assertIn("i18n/zh.json: not a site language", text)
        self.assertIn("i18n/ko.json: missing keys: nav_cta", text)
        self.assertIn("i18n/ja.json: not valid JSON", text)
        with self.assertRaises(bj.JournalError):
            bj.build(s.root, NOW)

    def test_en_json_must_match_the_source(self):
        s = Site(self)
        ui(s, "en", dict(bj.EN_UI, nav_cta="Changed"))
        _s, _r, errors, _w = bj.load_ui(s.root)
        self.assertIn("differs from the builder's source strings", "\n".join(errors))


class Translations(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        ui(self.s, "ko")
        self.s.post("a", DUE, pub=None)

    def tr_of(self, lang="ko"):
        posts, orphans, errors = bj.load_all(self.s.root)
        return next(p for p in posts if p["slug"] == "a")["_tr"].get(lang), orphans, errors

    def test_clean_reviewed(self):
        tr(self.s, "a", "ko")
        t, orphans, errors = self.tr_of()
        self.assertEqual((t["_problems"], orphans, errors), ([], [], []))
        self.assertEqual(t["title"], "a title (ko)")

    def test_unreviewed_and_format_problems(self):
        tr(self.s, "a", "ko", copy_review=None, copy_review_date=None, publish_at=DUE, image="/x.png")
        t, _o, errors = self.tr_of()
        self.assertEqual(errors, [])  # the queue never stops a build
        kinds = [k for k, _ in t["_problems"]]
        self.assertIn("review", kinds)
        self.assertIn("format", kinds)
        self.assertIn("not allowed in a translation: publish_at, image", "\n".join(m for _, m in t["_problems"]))

    def test_heading_structure_must_match(self):
        tr(self.s, "a", "ko", body="# 제목\n\n본문\n\n### 하위\n\n더\n")
        t, _o, _e = self.tr_of()
        self.assertEqual([k for k, _ in t["_problems"]], ["structure"])
        self.assertIn("English: h2, here: h2 h3", t["_problems"][0][1])

    def test_slug_and_lang_must_match_the_file_name(self):
        tr(self.s, "a", "ko", lang="ja", translation_of="b")
        t, _o, _e = self.tr_of()
        text = "\n".join(m for _, m in t["_problems"])
        self.assertIn("translation_of must be 'a'", text)
        self.assertIn("lang must be 'ko'", text)

    def test_orphans_in_the_queue(self):
        tr(self.s, "nope", "ko")
        tr(self.s, "a", "ja")      # ja is not enabled (no i18n/ja.json)
        tr(self.s, "a", "zh")      # ended code
        _t, orphans, errors = self.tr_of()
        self.assertEqual(errors, [])
        text = "\n".join(orphans)
        self.assertIn("nope.ko.md: no English post nope.md", text)
        self.assertIn("a.ja.md: i18n/ja.json does not exist", text)
        self.assertIn("a.zh.md: 'zh' is not a translation language", text)
        rc = bj.main(["--root", str(self.s.root), "--queue", str(self.s.root / "journal" / "queue"), "--check-queue", "--now", "2026-11-14T14:30+09:00"])
        self.assertEqual(rc, 1)

    def test_published_translation_problems_are_errors(self):
        self.s.post("live", DUE)
        tr(self.s, "live", "ko", where="posts", body="no headings\n")
        tr(self.s, "a", "ko", where="posts")  # its English post is not published
        _p, _o, errors = bj.load_all(self.s.root)
        text = "\n".join(errors)
        self.assertIn("live.ko.md: headings differ", text)
        self.assertIn("a.ko.md: its English post a.md is not published", text)


class PublishGate(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        ui(self.s, "ko")
        self.s.post("a", DUE, pub=None)

    def test_english_only_site_is_unchanged(self):
        s = Site(self)
        s.post("a", DUE, pub=None)
        rc, out = publish(s)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a\n", out + "\n")
        self.assertNotIn("languages:", out)

    def test_missing_translation_holds_the_post(self):
        rc, out = publish(self.s)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: —", out)
        self.assertIn("held:            a (langs 1/2 — missing: ko)", out)
        self.assertIn("languages: 2 enabled (en ko), ui ready: en ko", out)
        self.assertFalse(self.s.exists("journal/posts/a.md"))
        self.assertEqual(publish(self.s, slug="a")[0], 3)

    def test_unreviewed_translation_holds_the_post(self):
        tr(self.s, "a", "ko", copy_review=None, copy_review_date=None)
        rc, out = publish(self.s, slot_gates=False)
        self.assertIn("a (langs 1/2 — unreviewed: ko)", out)
        self.assertFalse(self.s.exists("journal/posts/a.md"))

    def test_ui_strings_not_ready_hold_the_post(self):
        ui(self.s, "ko", review=False)
        tr(self.s, "a", "ko")
        rc, out = publish(self.s)
        self.assertIn("a (langs 2/2 — ui strings: ko)", out)
        self.assertFalse(self.s.exists("journal/posts/a.md"))

    def test_complete_post_goes_out_with_its_translations(self):
        tr(self.s, "a", "ko")
        rc, out = publish(self.s, dry_run=True)
        self.assertIn("would publish: a (+1 langs)", out)
        self.assertFalse(self.s.exists("journal/posts/a.md"))
        rc, out = publish(self.s)
        self.assertEqual(rc, 0)
        self.assertIn("newly published: a (+1 langs)", out)
        en, ko = self.s.read("journal/posts/a.md"), self.s.read("journal/posts/a.ko.md")
        stamp = re.search(r"^published_at: (.+)$", en, re.M).group(1)
        self.assertEqual(stamp, "2026-11-14T14:30+09:00")
        self.assertIn("published_at: " + stamp, ko)
        self.assertFalse(self.s.exists("journal/queue/a.ko.md"))
        for rel in ("journal/en/a/index.html", "journal/ko/a/index.html", "journal/ko/index.html", "journal/ko/feed.xml"):
            self.assertTrue(self.s.exists(rel), rel)
        # the next build (the publisher's check) reads the moved files back without errors
        self.assertEqual(bj.build(self.s.root, NOW)["translations"], {"ko": ["a"]})

    def test_draft_and_unreviewed_english_are_not_lang_held(self):
        self.s.post("b", DUE, pub=None, copy_review=None, copy_review_date=None)
        rc, out = publish(self.s, slot_gates=False)
        self.assertIn("b (copy review missing", out)
        self.assertNotIn("b (langs", out)


class Backfill(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        ui(self.s, "ko")
        self.s.post("old", "2026-10-30T07:00-04:00")  # published before the gate, English only

    def test_grandfathered_post_is_english_only_until_its_translation_arrives(self):
        rep = bj.build(self.s.root, NOW)
        self.assertEqual(rep["translations"], {})
        self.assertIn("/journal/en/old/", self.s.read("journal/index.html"))
        self.assertFalse(self.s.exists("journal/ko/index.html"))
        rc, out = publish(self.s)
        self.assertNotIn("held:            old", out)

    def test_reviewed_translation_is_published_on_its_own(self):
        tr(self.s, "old", "ko")
        rc, out = publish(self.s)  # slot gates do not apply: not a new post
        self.assertEqual(rc, 0)
        self.assertIn("newly published: old.ko", out)
        self.assertIn("published_at: 2026-11-14T14:30+09:00", self.s.read("journal/posts/old.ko.md"))
        self.assertTrue(self.s.exists("journal/ko/old/index.html"))
        self.assertIn('hreflang="ko"', self.s.read("journal/en/old/index.html"))

    def test_backfill_held_reasons(self):
        tr(self.s, "old", "ko", copy_review=None, copy_review_date=None)
        rc, out = publish(self.s)
        self.assertIn("held:            old.ko (copy review missing: no copy_review)", out)
        tr(self.s, "old", "ko", body="TODO\n")
        rc, out = publish(self.s)
        self.assertIn("held:            old.ko (fix it first: placeholder, structure)", out)
        tr(self.s, "old", "ko")
        ui(self.s, "ko", review=False)
        rc, out = publish(self.s)
        self.assertIn("held:            old.ko (ui strings for ko are not ready (i18n/ko.json))", out)
        self.assertFalse(self.s.exists("journal/posts/old.ko.md"))

    def test_stamp_published_on_a_translation(self):
        f = tr(self.s, "old", "ko")
        self.assertTrue(bj.stamp_published(f, "2026-11-14T14:30+09:00"))
        fm = f.read_text(encoding="utf-8").split("\n---", 1)[0]
        self.assertEqual(fm.splitlines()[-1], "published_at: 2026-11-14T14:30+09:00")
        self.assertFalse(bj.stamp_published(f, "2026-11-14T15:30+09:00"))


class Rendering(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        ui(self.s, "ko")
        self.s.post("a", "2026-10-30T07:00-04:00")
        self.s.post("b", "2026-11-02T07:00-05:00")  # English only
        tr(self.s, "a", "ko", where="posts", tags="반려동물, 산책")
        self.rep = bj.build(self.s.root, NOW)

    def test_report(self):
        self.assertEqual(self.rep["translations"], {"ko": ["a"]})
        self.assertEqual(self.rep["_enabled"], ["en", "ko"])

    def test_translated_page(self):
        h = self.s.read("journal/ko/a/index.html")
        self.assertIn('<html lang="ko">', h)
        self.assertIn('<link rel="canonical" href="https://pawstcard.ipe.rest/journal/ko/a/">', h)
        self.assertIn('<link rel="alternate" hreflang="en" href="https://pawstcard.ipe.rest/journal/en/a/">', h)
        self.assertIn('<link rel="alternate" hreflang="ko" href="https://pawstcard.ipe.rest/journal/ko/a/">', h)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://pawstcard.ipe.rest/journal/en/a/">', h)
        self.assertIn('<meta property="og:locale" content="ko_KR">', h)
        self.assertIn('<meta property="og:locale:alternate" content="en_US">', h)
        self.assertIn('"inLanguage": "ko"', h)
        self.assertIn('"translationOfWork"', h)
        self.assertIn("/journal/ko/feed.xml", h)
        self.assertIn(">저널<", h)
        self.assertIn("a title (ko)", h)
        self.assertNotIn("Title of b", h)  # the related list holds ko pages only
        data = json.loads(re.search(r'<script type="application/json" id="ipe-langs">(.*?)</script>', h).group(1))
        self.assertEqual(data["current"], "ko")
        self.assertEqual([o["lang"] for o in data["options"]], ["en", "ko"])
        self.assertEqual(data["options"][1], {"lang": "ko", "name": "한국어", "href": "/journal/ko/a/"})
        self.assertIn('data-ipe-lang-slot', h)

    def test_english_pages(self):
        a, b = self.s.read("journal/en/a/index.html"), self.s.read("journal/en/b/index.html")
        self.assertIn('<html lang="en">', a)
        self.assertIn('hreflang="ko"', a)
        self.assertIn('"workTranslation"', a)
        self.assertNotIn('hreflang="ko"', b)
        self.assertIn('<link rel="alternate" hreflang="x-default" href="https://pawstcard.ipe.rest/journal/en/b/">', b)
        lst = self.s.read("journal/index.html")
        self.assertIn('hreflang="ko" href="https://pawstcard.ipe.rest/journal/ko/"', lst)

    def test_language_list_and_feed(self):
        lst = self.s.read("journal/ko/index.html")
        self.assertIn('<html lang="ko">', lst)
        self.assertIn("/journal/ko/a/", lst)
        self.assertNotIn("/journal/en/b/", lst)  # b has no ko version: not in the ko list
        feed = self.s.read("journal/ko/feed.xml")
        self.assertIn("<language>ko</language>", feed)
        self.assertIn("https://pawstcard.ipe.rest/journal/ko/a/", feed)
        self.assertNotIn("/b/", feed)
        self.assertNotIn("/ko/", self.s.read("journal/feed.xml"))

    def test_sitemap_and_llms(self):
        sm = self.s.read("sitemap.xml")
        self.assertIn("<loc>https://pawstcard.ipe.rest/journal/ko/a/</loc>", sm)
        self.assertIn("<loc>https://pawstcard.ipe.rest/journal/ko/</loc>", sm)
        row = re.search(r"<url>\s*<loc>https://pawstcard.ipe.rest/journal/en/a/</loc>.*?</url>", sm, re.S).group(0)
        self.assertIn('<xhtml:link rel="alternate" hreflang="ko" href="https://pawstcard.ipe.rest/journal/ko/a/"/>', row)
        self.assertIn('<xhtml:link rel="alternate" hreflang="x-default" href="https://pawstcard.ipe.rest/journal/en/a/"/>', row)
        self.assertIn("Translations: 한국어 https://pawstcard.ipe.rest/journal/ko/", self.s.read("llms.txt"))

    def test_translation_tags_are_its_own(self):
        h = self.s.read("journal/ko/a/index.html")
        self.assertIn("반려동물", h)

    def test_not_ready_ui_builds_no_pages_and_sweeps_old_ones(self):
        ui(self.s, "ko", review=False)
        rep = bj.build(self.s.root, NOW)
        self.assertEqual(rep["translations"], {})
        self.assertFalse(self.s.exists("journal/ko"))
        self.assertNotIn("/journal/ko/", self.s.read("sitemap.xml"))
        self.assertNotIn('hreflang="ko"', self.s.read("journal/en/a/index.html"))

    def test_sweep_keeps_files_it_did_not_generate(self):
        (self.s.root / "journal" / "ko" / "keep.txt").write_text("hand-made", encoding="utf-8")
        (self.s.root / "journal" / "posts" / "a.ko.md").unlink()
        bj.build(self.s.root, NOW)
        self.assertFalse(self.s.exists("journal/ko/a/index.html"))
        self.assertFalse(self.s.exists("journal/ko/feed.xml"))
        self.assertTrue(self.s.exists("journal/ko/keep.txt"))


class LangsTool(unittest.TestCase):
    def setUp(self):
        self.s = Site(self)
        ui(self.s, "ko")
        ui(self.s, "ja", {k: "" for k in bj.UI_KEYS}, review=False)
        self.s.post("a", DUE, pub=None)
        self.q = self.s.root / "journal" / "queue"

    def test_status(self):
        tr(self.s, "a", "ko")
        lines = []
        self.assertEqual(jl.status(self.s.root, self.q, out=lines.append), 0)
        text = "\n".join(lines)
        self.assertRegex(text, r"\nui\s+✓\s+·")
        self.assertRegex(text, r"\na\s+R\s+·\s+queued\s+langs 2/3 — missing: ja · ui strings: ja")

    def test_scaffold(self):
        out_dir = self.s.root / "drafts"
        lines = []
        self.assertEqual(jl.scaffold(self.s.root, self.q, "ko", "a", out_dir, out=lines.append), 0)
        f = out_dir / "a.ko.md"
        t = bj.parse_translation(f, published=False)
        kinds = {k for k, _ in t["_problems"]}
        self.assertEqual(kinds, {"format", "placeholder", "review"})  # nothing passes until it is translated and reviewed
        self.assertEqual(jl.scaffold(self.s.root, self.q, "ko", "a", out_dir, out=lines.append), 1)  # never overwrites
        self.assertEqual(jl.scaffold(self.s.root, self.q, "ko", "a", self.q, out=lines.append), 1)   # never into the queue
        self.assertFalse((self.q / "a.ko.md").exists())
        self.assertEqual(jl.scaffold(self.s.root, self.q, "zh", "a", out_dir, out=lines.append), 1)
        self.assertEqual(jl.scaffold(self.s.root, self.q, "ja", "nope", out_dir, out=lines.append), 1)


if __name__ == "__main__":
    unittest.main()
