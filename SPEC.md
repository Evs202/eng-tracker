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

## Current Status (2026-07-01)

| Phase | Status | Notes |
|---|---|---|
| 1. Company list | Done | 238 companies in `scraper/output/companies.csv` |
| 2. Change detector | Done, partial | Working for 157 non-Workday companies. 81 Workday companies skipped — see Known Issues |
| 3. ATS parsers | Blocked | Workday parser built (`scraper/parsers/workday.py`) but can't run from the VPS — see Known Issues |
| 4. Notifications | Done | Email via Resend, not Gmail (see Known Issues) |
| 5. Sheet → Site pipeline | Done | GitHub Action every 6h, auto-deploys to Vercel |
| Frontend | Redesigned 2026-07-01 | Dense spreadsheet-style table, sector grouping, blue palette. See `styles.css`/`app.js` |

**Live data:** 20 verified listings in Sheet 2 / `data/deadlines.json`. Most
seed deadlines are stale (from last year's cycle) and need refreshing with
2026/2027 dates — this is the top priority before wider sharing.

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
- `.github/workflows/sync-sheet.yml` — Sheet 2 → site pipeline
- `index.html` / `styles.css` / `app.js` — the frontend
- `CLAUDE.md` — session gotchas and conventions (read this before making changes)

## Next priorities
1. Refresh Sheet 2 with current-cycle (2026/2027) deadlines — most existing rows show as closed
2. Decide on a Workday fix (proxy / home-machine cron / manual)
3. Expand company list toward 400-500
4. Real "Report a mistake" form (currently a placeholder Google Form link)
