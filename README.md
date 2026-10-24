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

Manuscripts live in `journal/queue/<slug>.md`; the build turns the ones whose `publish_at` has passed into
`journal/en/<slug>/index.html`, the `/journal/` list, `journal/feed.xml`, and merges them into `sitemap.xml` and `llms.txt`
(the landing entries are never touched). Full front-matter spec: docstring of `scripts/build_journal.py`.

```
---
slug: my-post                      # = file name
title: Post title
description: One sentence for meta/cards/RSS.
publish_at: 2026-10-25T14:00+09:00 # KST, this exact format
---
Markdown body…
```

```bash
./scripts/check.sh                                   # green gate: unit tests + manuscript validation
python3 scripts/publish_journal.py                   # publish everything that is due (--dry-run, --slug X, --now ISO available)
git add journal/en journal/index.html journal/feed.xml journal/queue/<due-slug>.md sitemap.xml llms.txt && git commit && git push
```

Future-dated manuscripts are validated but never rendered, listed, or put in the sitemap/llms.txt/feed.
Note: Pages serves the whole repo root, so a manuscript committed to `main` is readable at its URL before it is due.

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
