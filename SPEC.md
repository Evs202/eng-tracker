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
| 2. Change detector | Done, partial | Working for non-Workday companies. Workday companies skipped — see Known Issues |
| 3. ATS parsers | Blocked | Workday parser built (`scraper/parsers/workday.py`) but its API endpoint shape was also found to be wrong (`/fs/searchPaginated` instead of the real `/wday/cxs/{tenant}/{site}/jobs`), independent of the VPS block — see Known Issues |
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

**Workday blocks the VPS entirely (81 of 238 companies affected).**
Hetzner's datacenter IP is blocked by Workday at the network level — both
`*.myworkday.com` (doesn't resolve via DNS) and the `*.myworkdayjobs.com`
REST API (resolves, but returns 404/422 without the exact per-company "job
site" slug, which can only be discovered by running JS in a real browser).
Current behavior: `detector.py` detects `ats_type == "Workday"` and skips
the company with a `WARN` log line rather than failing. Fix options not yet
implemented: residential proxy (~£20-50/mo), running Workday checks from a
home machine, or accepting manual quarterly checks for this subset.

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
- `scraper/parsers/workday.py` — Workday CXS parser (currently unusable from VPS, see Known Issues)
- `scraper/discover_workday_sites.py` — one-off Workday job-site-name discovery script (largely unsuccessful, see Known Issues)
- `scraper/validate_companies.py` — reusable, field-agnostic reachability + ATS-type validator (see discovery/validation pipeline note above); run with no args to re-check `companies.csv` in place
- `.github/workflows/sync-sheet.yml` — Sheet 2 → site pipeline
- `index.html` / `styles.css` / `app.js` — the frontend
- `CLAUDE.md` — session gotchas and conventions (read this before making changes)

## Next priorities
1. Refresh Sheet 2 with current-cycle (2026/2027) deadlines — most existing rows show as closed
2. Decide on a Workday fix (proxy / home-machine cron / manual) — note this now also needs a `workday.py` code fix (wrong API endpoint) independent of whichever network fix is chosen
3. Resolve the 26 remaining ambiguous companies from the 2026-07-02 re-validation with an isolated manual check (bulk automated re-checking proved unreliable for this bucket — see discovery/validation pipeline note above)
4. Keep expanding the company list toward 1000+ using the discovery/validation pipeline (needs a decision on paid search-API access to make the discovery half — not just validation — actually unattended/scriptable)
6. Real "Report a mistake" form (currently a placeholder Google Form link)
