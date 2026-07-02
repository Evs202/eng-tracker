# UK Engineering Tracker — Build Spec

## What this is
A self-updating UK engineering graduate scheme tracker. Shows employers,
schemes, deadlines, and locations grouped by sector. Data refreshes
automatically — no manual scraping once a company is onboarded.

Live: https://eng-tracker-tawny.vercel.app/
Repo: https://github.com/Evs202/eng-tracker

## Architecture

```
Sheet 1: Master company list (name + careers URL + ATS type)
        ↓ every 6 hours (cron on VPS)
Playwright scraper visits each URL (Workday companies skipped — see Known Issues)
        ↓
Change detector (MD5 hash comparison)
        ↓ if changed + grad-scheme keywords found
Flagged for manual review — email alert sent
        ↓
Human verifies and adds row to Sheet 2
        ↓
GitHub Action (every 6h): Sheet 2 CSV → deadlines.js → Vercel deploy
```

## Current Status (2026-07-02)

| Phase | Status | Notes |
|---|---|---|
| 1. Company list | Done, growing | 252 companies in `scraper/output/companies.csv` (237 original + 17 added 2026-07-02, minus 2 removed as invalid — see below). Full re-validation of the original 237 (2026-07-02) found: 117 alive, 75 blocked by the known systemic Workday issue (not a data problem), 34 confirmed genuinely dead (all now fixed with current URLs, or removed — see below), 26 unresolved/ambiguous (bot-protection made bulk automated re-checking unreliable even with delays; needs individual manual verification, not trusted either way). 2 rows removed: `hyder` (Hyder Consulting, fully absorbed into Arcadis in 2015, already a separate entry) and `nugen` (NuGeneration, wound up by Toshiba in 2019, company no longer exists). |
| 2. Change detector | Done, partial | Working for non-Workday companies. Workday companies skipped — see Known Issues. Actually run end-to-end for the first time 2026-07-02 (previously only code-reviewed, never executed) — found and fixed a real flagging bug, see Known Issues |
| 3. ATS parsers | Blocked on discovery, not the endpoint | Workday parser (`scraper/parsers/workday.py`) had a wrong API endpoint shape (`/fs/searchPaginated`); fixed 2026-07-02 to the real `/wday/cxs/{tenant}/{site}/jobs`, verified against a live tenant (a structured `HTTP_422` from Workday's own API, not a network block or shape error). Still can't get real results per-company without the `{site}` slug, which requires browser-based discovery (`discover_workday_sites.py`) — and that's still blocked by the same anti-bot wall as the VPS. See Known Issues. |
| 4. Notifications | Done | Email via Resend, not Gmail (see Known Issues) |
| 5. Sheet → Site pipeline | Done | GitHub Action every 6h, auto-deploys to Vercel |
| Frontend | Redesigned 2026-07-01 | Dense spreadsheet-style table, sector grouping, blue palette. See `styles.css`/`app.js` |

**Live data:** 20 verified listings in Sheet 2 / `data/deadlines.json`. Most
seed deadlines are stale (from last year's cycle) and need refreshing with
2026/2027 dates — this is the top priority before wider sharing.

**Discovery/validation pipeline (added 2026-07-02):** the long-term goal is
1000+ companies, and this repo is meant to become a reusable template for
other fields (medicine, psychology, sociology, etc. — see project macro-goals
discussion), so growing the company list is being done via a repeatable
process rather than one-off manual fixes: (1) source candidate company names
from general web search / knowledge — never by scraping a third-party
directory's compiled list (ToS/database-right risk), (2) find each
candidate's own official careers URL directly on their domain, (3) validate
reachability with a two-tier check — a fast raw HTTP request first, falling
back to a real Playwright browser fetch for anything that fails, since a
plain `requests` 403 is often just bot-protection rather than a real dead
link (this caught 3 false positives in the first 18-company test batch).
First run: 18 candidates found, 17 validated and added, 1 confirmed genuinely
dead. The mechanical half (reachability + ATS-type detection) is now a real
reusable script: `scraper/validate_companies.py` — field-agnostic (no
engineering-specific logic), takes any companies.csv-shaped file, two-tier
check (fast HTTP request, then a real Playwright browser fallback with a
retry, jittered delay, and periodic context refresh to reduce false
negatives from bot-protection). Discovery (finding candidate names + their
URLs) still requires a human or an LLM with search access — there's no
scriptable, unattended way to do that half without a paid search API, which
hasn't been set up yet. Important limitation found in practice: even the
improved validator could not reliably resolve genuinely ambiguous cases in
bulk (a site confirmed alive in isolation still failed inside a 30-company
batch, likely because Cloudflare/Akamai-style bot management aggregates
signals across many customer sites sharing the same infrastructure) — don't
trust bulk "dead" verdicts on ambiguous (403/timeout, non-404) results
without an isolated manual check.
Ran the full pipeline once at scale 2026-07-02: re-validated all 254
companies, found and fixed the 34 confirmed-dead original entries (32 got
corrected URLs, 2 were removed as invalid — see status table above).

## Known Issues

**Reachability-blocked companies: accepted as manual-only for now (decided 2026-07-02).**
Two groups can't be reached by an automated headless browser at all, regardless
of parsing approach — this is a network/anti-bot problem, not a data-quality
or extraction problem, and no amount of better parsing fixes it: (1) Workday
(75 of 252 companies) — blocked at the network level from every environment
tested this session, not just the VPS (`*.myworkday.com` doesn't resolve,
`*.myworkdayjobs.com` returns a generic "Workday is currently unavailable"
anti-bot wall); `detector.py` detects `ats_type == "Workday"` and skips with
a `WARN` log line. (2) A handful of Cloudflare-bot-challenge-protected
companies found during the 2026-07-02 ambiguous-bucket triage (MBDA,
National Grid, Spirent, BAE Systems Applied Intelligence — confirmed via a
literal Cloudflare `__cf_chl_rt_tk` JS-challenge token and "Just a
moment..." title, not a dead link). Decision: accept manual quarterly
checks for both groups while pre-revenue, rather than paying for a
residential proxy (~£20-50/mo) or running checks from a home machine. Their
`companies.csv` URLs are correct as-is — do not "fix" these, there's
nothing wrong with the URL, just the reachability.

**Raw page-hash comparison was too noisy to gate alerts on (fixed 2026-07-02).**
`detector.py` had never actually been run end-to-end before this date — it
had only been code-reviewed. Running it against 5 real companies surfaced a
real bug invisible from reading the code: `fetch_page()` hashes the whole
page's visible text, but that text isn't stable between two fetches of
genuinely-unchanged content — e.g. Kier's careers page (jobs.kier.co.uk)
returned a different hash twice in one minute because an accessibility
widget ("Skip to main content" / "Enable accessibility for low vision")
injects itself into the DOM asynchronously and isn't reliably present by
the time the fixed 2-second post-load wait fires. Gating alerts on "did the
raw hash change" produced two failure modes: (1) false positives — an
already-flagged company got re-flagged (and would have re-triggered an
email alert) purely from this kind of unrelated DOM noise, and (2) false
negatives — a company's *first-ever* check silently stored a baseline hash
and never flagged even when grad keywords were already present on the page,
so newly-added companies with an already-open scheme were silently missed.
Fixed by tracking keyword-match *state* (a new `keyword_flagged` column in
`page_hashes`) and gating alerts on a state *transition* (not-flagged →
flagged) instead of on the raw hash — verified live: a company with
already-open keywords now flags correctly on its first-ever check, and a
company whose hash changes from unrelated noise (keywords unchanged) no
longer re-flags. The raw hash is still tracked and logged for the "did the
page change at all" signal, just no longer used to gate alerting.

## Tech Stack
- Python 3.11+, Playwright (headless Chromium via `/snap/bin/chromium` on the VPS)
- SQLite (`scraper/db.sqlite`, gitignored) — page hash storage
- Google Sheets, published as CSV
- GitHub Actions — Sheet sync + notifier
- Vercel — static site hosting, auto-deploys from `main`
- Resend — transactional email (verified sender domain `automations-online.uk`)
- Hetzner CX23 VPS — cron runner

## Key Files
- `data/deadlines.js` / `data/deadlines.json` — site data, auto-generated, do not hand-edit
- `scraper/output/companies.csv` — master company list (Sheet 1 export)
- `scraper/detector.py` — change detection, run every 6h via VPS cron
- `scraper/notifier.py` — Resend email alerts on flagged changes
- `scraper/parsers/workday.py` — Workday CXS parser; endpoint shape fixed 2026-07-02, but still needs a discovered per-company `{site}` slug to return real results (see Known Issues)
- `scraper/discover_workday_sites.py` — one-off Workday job-site-name discovery script (largely unsuccessful, see Known Issues)
- `scraper/validate_companies.py` — reusable, field-agnostic reachability + ATS-type validator (see discovery/validation pipeline note above); run with no args to re-check `companies.csv` in place
- `.github/workflows/sync-sheet.yml` — Sheet 2 → site pipeline
- `index.html` / `styles.css` / `app.js` — the frontend
- `CLAUDE.md` — session gotchas and conventions (read this before making changes)

## Next priorities
1. Build and prove out an LLM (Claude) extraction prototype against already-flagged pages — this is the actual answer to cross-site parsing consistency, since 55% of companies (131/237 original) use a bespoke "Custom" career site with no shared ATS/API to hook into, so no CSS-selector or hash-diff approach generalizes across them. Test against 2-3 real flagged pages before committing further. This is the parked "Phase 3.5" idea, now with a concrete technical reason it's the only mechanism that works: an LLM reads for meaning regardless of page structure, and the extraction prompt (not the mechanism) is what changes per vertical for the reusable-template goal.
2. Research real current URLs for the 22 companies confirmed genuinely broken in the 2026-07-02 ambiguous-bucket triage (14 confirmed via DNS failure on two independent resolvers, 4 with SSL cert errors, 4 with other real errors — full list was in a since-cleaned-up scratch file, re-derivable by re-running `validate_companies.py` and cross-referencing against the Reachability-blocked note above to exclude the 4 Cloudflare-blocked-not-broken ones)
3. Refresh Sheet 2 with current-cycle (2026/2027) deadlines — most existing rows show as closed
4. Keep expanding the company list toward 1000+ using the discovery/validation pipeline (needs a decision on paid search-API access to make the discovery half — not just validation — actually unattended/scriptable)
6. Real "Report a mistake" form (currently a placeholder Google Form link)
