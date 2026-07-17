# Pawstcard — landing page

Landing page + email waitlist for **Pawstcard**, a pet-sitter visit report-card builder.
This is a **smoke test** page (F-016), not the product.

## What this is

Part of a 3-step validation, run as a **channel-discovery test**: which paid/organic
channel actually brings real pet sitters, measured by email sign-up conversion.
Meta ads drive traffic here; UTM tags split channels; GA4 measures conversion.

## Stack

- Static HTML (single `index.html`, no build step)
- [Web3Forms](https://web3forms.com) — email capture (free, unlimited; no backend)
- [GA4](https://analytics.google.com) — traffic + custom events (`cta_click`, `email_signup`)
- GitHub Pages — hosting

## Local preview

```bash
python3 -m http.server 8000
# open http://localhost:8000
```

## Deploy

Push to `main` → GitHub Pages rebuilds automatically. No CI config needed
(Pages serves the repo root).

## Custom domain

`pawstcard.ipe.rest` (see `CNAME`). Requires a DNS `CNAME` record
`pawstcard → blessu76.github.io` on the ipe.rest DNS provider.

---

⚠️ **Source of truth** for the F-016 project (goals, validation plan, unit economics)
is `_ipe/foundry/F-016_tailnote/BRIEF.md` in the private ipe Studio repo, not this
public marketing repo. Deploy/ops notes: `_ipe/foundry/F-016_tailnote/DEPLOY.md`.
