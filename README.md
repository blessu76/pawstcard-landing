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

### IndexNow

`deploy.yml` runs `scripts/indexnow.py --changed-since <before>` after the Pages deploy (any push to `main`, including the unattended publisher's): only the indexable pages
that changed in that push (landing, `/journal/`, `/journal/en/<slug>/`) are sent to IndexNow (Bing, Naver, Yandex; Google reads `sitemap.xml`). The step waits for the public
key file (`/<32 hex>.txt` in the repo root) to be live, never fails the deploy (`continue-on-error`), and sends nothing when no page changed. `--dry-run` prints the payload without the key.

### Unattended publishing (Mac mini, launchd — lives OUTSIDE this repo)

A launchd job on the Mac mini publishes the night editions. The plist and script are **not** in the repo (decision 2026-10-25); only this note is.

| piece | where |
|---|---|
| job | `~/Library/LaunchAgents/rest.ipe.pawstcard-publish.plist` (label `rest.ipe.pawstcard-publish`, every 300 s + at load) |
| script | `~/.ipe/bin/pawstcard_publish.sh` |
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
