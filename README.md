# Pawstcard — landing page

Landing page + email waitlist for **Pawstcard**, a pet-sitter visit report-card builder.
This is a **smoke test** page (F-016), not the product.

## What this is

Part of a 3-step validation, run as a **channel-discovery test**: which paid/organic
channel actually brings real pet sitters, measured by email sign-up conversion.
Meta ads drive traffic here; UTM tags split channels; GA4 measures conversion.

## Stack

- Static HTML landing (`index.html`, hand-written, no build step)
- Journal (`/journal/`): generated static pages — `scripts/build_journal.py` (stdlib Python)
- `vendor/ipe_web_kit/` — ipe web kit, a tag-pinned copy (see `KIT_VERSION`; never edit — re-`install` a new tag from the kit clone). Used for `esc`, hreflang links, `iso_kst`, the ipe-localtime script. `deploy.yml` removes `vendor/` before the Pages upload.
- [Web3Forms](https://web3forms.com) — email capture (free, unlimited; no backend)
- [GA4](https://analytics.google.com) — traffic + custom events (`cta_click`, `email_signup`)
- GitHub Pages — hosting

## Journal (/journal/)

**Unpublished manuscripts are NOT in this repo** (main is public and the whole repo root is served live). They live in `~/pawstcard-journal-queue/<slug>.md`
(`--queue DIR` or `$PAWSTCARD_JOURNAL_QUEUE` to change it). Publishing moves a manuscript into `journal/posts/<slug>.md` (stamped, committed, the build input).
`publish_at` is only a floor ("not before"); running
`scripts/publish_journal.py` is what publishes: it moves and stamps every due manuscript with `published_at` (the real run time in KST, `YYYY-MM-DDTHH:MM+09:00`; site-wide rule "registration = KST", static text reads e.g. `Oct 25, 2026, 20:13 KST`; a small inline script shows it in the reader's device time zone)
and builds `journal/en/<slug>/index.html`, the `/journal/` list, `journal/feed.xml`, and merges them into `sitemap.xml` and `llms.txt`
(the landing entry is untouched except its `lastmod`, which follows the newest post). Pages, sitemap lastmod, JSON-LD `datePublished` and the feed all carry the stamped time.
The same build also regenerates the **Journal card section on the landing page** (`index.html`, between `<!-- journal:home:start -->` and `<!-- journal:home:end -->`): the newest 3 published posts as static cards
(date via `<time data-ipe-time>`, title, 1–2 line summary; the whole card links to the post; 1 / 2 posts still lay out as a finished row). Never hand-edit between those markers; `build_journal.py --check` (part of `check.sh`) fails when the cards are not the newest published posts.
Full front-matter spec: docstring of `scripts/build_journal.py`.

```
---
slug: my-post                      # = file name
title: Post title
description: One sentence, <= 155 chars.
copy_review: iris                  # required before publishing (see "Copy-review gate")
copy_review_date: 2026-11-14       # YYYY-MM-DD
publish_at: 2026-10-25T07:13-04:00 # floor in America/New_York; offset must be the real EDT/EST one (-04:00 until 2026-11-01, then -05:00); compared as instants
tags: [pet sitting, visit reports]
---
Markdown body…
```

```bash
./scripts/check.sh                                   # green gate: unit tests + manuscript validation
python3 scripts/publish_journal.py --slug my-post    # publish one (refuses if publish_at is in the future); --dry-run, --now ISO available
git add journal sitemap.xml llms.txt index.html && git commit && git push
```

Not-yet-due or unstamped manuscripts are validated but never rendered, listed, or put in the sitemap/llms.txt/feed.
Note: Pages serves the whole repo root, so a manuscript committed to `main` is readable at its URL before it is published.

### Publish slot rules (1 post a day, KST 12:00-17:59)

`publish_at` is a floor; `scripts/publish_journal.py` adds gates (`scripts/slot_rules.py`) evaluated on the real KST clock: **(1)** only 12:00-17:59 KST, **(2)** at most 1 post per KST day (by `published_at` date; also 1 per run),
**(3)** the KST hour must differ from the previous published post's hour. A blocked run prints `held: <slug> (<reason>)` and exits 0 (`--slug` exits 3). No randomness at publish time: the writer randomizes when setting the floor.
Every run ends with `queue depth: N (min 3)` (a `WARN:` below 3) and `next eligible publish: <KST>`; `build_journal.py --check` warns about queued manuscripts whose `publish_at` falls outside the slot or shares a KST day.

**Writer: set `publish_at` with `python3 scripts/schedule_slot.py [--after YYYY-MM-DD] [--count N] [--seed S]`** — it prints the next valid random `publish_at` (ET offset, DST-correct; KST 12-17, the day after the last published/queued post, a different hour).
`pawstcard_publish.sh` needs no change: it parses only the `would publish:` line, which now lists at most one slug.

### Copy-review gate (`copy_review: iris`)

A post goes live only after the copy review (Iris). Front matter must carry both `copy_review: iris` and `copy_review_date: YYYY-MM-DD` (a real date).
`publish_journal.py` **holds** a not-yet-published post without them (`held: <slug> (copy review missing: …)`, exit 0; `--slug` → REFUSED, exit 3; not bypassed by `--no-slot-gates`)
and every run prints `unreviewed: N`. `check.sh` (`build_journal.py --check`) **fails** on such a post in the queue or a new one in `journal/posts/` (drafts are exempt).
**Grandfathering:** the check applies only to posts without `published_at`. Everything already published (stamped) is exempt automatically, so no per-post marker or list is needed;
a post's review stamp is only read until the moment it is published. `pawstcard_publish.sh` is unchanged (it parses only `would publish:`).

### 12 languages (`i18n/`, `<slug>.<lang>.md`)

Design, interface and the translator rulebook: `_ipe/foundry/F-016_pawstcard/web/JOURNAL_I18N.md`. Languages (fixed order, `scripts/languages.py`, same values as ipe_web_kit):
`en ko ja zh-Hant es pt-BR fr de id th vi tr` — never `zh`, `pt`, `zh-Hans`, `ru`, `ar`, `hi`. English URLs are unchanged (`/journal/`, `/journal/en/<slug>/`); a language lives at `/journal/<lang>/` and `/journal/<lang>/<slug>/`.
- **UI strings:** `i18n/<lang>.json`, exactly the keys of `i18n/en.json` (the source) plus `_meta` with `copy_review: iris` + `copy_review_date`. An empty string or a missing review = that language is **not ready**: a warning, no pages in it, new posts wait — never an English fallback.
- **Translations:** `<slug>.<lang>.md` next to the English manuscript (queue → `journal/posts/` on publishing) with `slug`, `lang`, `translation_of`, `title`, `description`, its own `copy_review`, optional `tags`/`image_alt`;
  `publish_at`, `image`, `draft`, `category` are inherited and not allowed. The heading structure must match the English post.
- **Gate:** `publish_journal.py` publishes a new post only together with a clean, reviewed translation for every enabled language and ready UI strings (`held: <slug> (langs 4/12 — missing: …)`); all files get the same `published_at`.
  Posts published before the gate are grandfathered: each translation goes out on its own when it arrives (`newly published: old-post.ko`); until then the post is only in the English list.
- **Pages:** each language has its posts, list, `feed.xml`; every page carries `<html lang>`, its own canonical, `hreflang` for each version + `x-default` (English), `og:locale`, JSON-LD `inLanguage`; `sitemap.xml` lists every version with `xhtml:link`.
  The header has an empty `<span data-ipe-lang-slot>` and a `<script id="ipe-langs">` JSON (current, label, options) that ipe_web_kit v0.7.2 turns into the language menu — this repo renders no control and no browser detection.
- **Tools:** `python3 scripts/journal_langs.py status` (✓/R/U/!/· per post and language) · `python3 scripts/journal_langs.py scaffold --lang ko --slug <slug> --out <drafts dir>` (never into the queue, never overwrites).

### Pre-publish checks (SEO guide v1)

`build_journal.py` (every run), `--check` (part of `check.sh`) and `publish_journal.py` run `lint()` over every manuscript, queue included.
**Fails** (nothing is stamped or built): placeholder text (`TODO`, `TBD`, `YYYY-MM-DD`, …) in title/description/body, a stamped `published_at`/`updated` in the future, a missing local `image`
— on top of the loader's own errors (required fields, bad dates, duplicate/reserved slug). **Warns only**: body < 400 words (target), `<title>` > 60 characters, description > 160, duplicate `<title>`.
Body length (P0-9; CJK counts 2 characters = 1 word, so 800 characters = 400 words): `python3 scripts/build_journal.py --check-queue` is the **pre-publish queue check** —
a NEW manuscript under 300 words is an error there (run it when a manuscript lands in the queue; the unattended publisher never runs it). In `check.sh` and in publishing, the same post is only a loud
`WARN:` line and **publishing goes ahead** (the unattended publisher must never silently drop a post); published posts under 300 words only warn.

### IndexNow

`deploy.yml` runs `scripts/indexnow.py --changed-since <before>` after the Pages deploy (any push to `main`, including the unattended publisher's): only the indexable pages
that changed in that push (landing, `/journal/`, `/journal/<lang>/`, `/journal/<lang>/<slug>/`) are sent to IndexNow (Bing, Naver, Yandex; Google reads `sitemap.xml`). The step waits for the public
key file (`/<32 hex>.txt` in the repo root) to be live, never fails the deploy (`continue-on-error`), and sends nothing when no page changed. `--dry-run` prints the payload without the key.

### Unattended publishing (Mac mini, launchd — lives OUTSIDE this repo)

A launchd job on the Mac mini publishes the night editions. The launchd plist is **not** in the repo (decision 2026-10-25). The script is tracked at `scripts/ops/pawstcard_publish.sh`; the host runs the identical copy at `~/.ipe/bin/pawstcard_publish.sh` (re-copy after any change here).

| piece | where |
|---|---|
| job | `~/Library/LaunchAgents/rest.ipe.pawstcard-publish.plist` (label `rest.ipe.pawstcard-publish`, every 300 s + at load) |
| script | repo: `scripts/ops/pawstcard_publish.sh` · host (launchd runs this): `~/.ipe/bin/pawstcard_publish.sh` |
| dedicated clone | `~/.ipe/pawstcard-publish/repo` (always reset to `origin/main`; never edit it) |
| manuscripts | `~/pawstcard-journal-queue/` (published ones are moved to `.published/`) |
| log · state | `~/.ipe/logs/pawstcard-publish.log` · `~/.ipe/pawstcard-publish/{FAILED,SOFT_ALERT,last_tick}` |

Each tick: fetch + reset to `origin/main` → nothing due? exit quietly → due: `publish_journal.py` (stamps the real KST time) → `scripts/check.sh` → commit → `git push origin HEAD:main`, back to back, so `published_at` ≈ go-live time.
It never pushes when `check.sh` is red, when anything would be deleted, or when staged paths fall outside `journal/ sitemap.xml llms.txt index.html`.
That is a *hard* failure: `FAILED` is written (and a macOS notification shown) and the job stands down until you read and delete `FAILED`. Network / rejected-push failures are *soft*: retried next tick, `SOFT_ALERT` after 3 in a row.
The job works on a staging copy of the queue, so a failed run never loses a manuscript.

```bash
~/.ipe/bin/pawstcard_publish.sh --dry-run                                  # everything but the real push; PAWSTCARD_NOW=2026-10-25T20:14+09:00 to fake the clock
launchctl bootout   gui/$(id -u)/rest.ipe.pawstcard-publish                # stop (kill switch)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/rest.ipe.pawstcard-publish.plist   # start
```

The job does nothing until `scripts/publish_journal.py` on `main` supports `--queue` (the queue-outside-the-repo commit). The Mac mini never sleeps (`pmset sleep 0` + `rest.ipe.prevent-sleep`); after any gap launchd fires on wake and the stamp is simply the actual time.

## Local preview

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy

Push to `main` → GitHub Pages deploys the repo root (`.github/workflows/deploy.yml`). Generated journal files are committed.

## Custom domain

`pawstcard.ipe.rest` (see `CNAME`). Requires a DNS `CNAME` record
`pawstcard → blessu76.github.io` on the ipe.rest DNS provider.

---

⚠️ **Source of truth** for the F-016 project (goals, validation plan, unit economics)
is `_ipe/foundry/F-016_tailnote/BRIEF.md` in the private ipe Studio repo, not this
public marketing repo. Deploy/ops notes: `_ipe/foundry/F-016_tailnote/DEPLOY.md`.
