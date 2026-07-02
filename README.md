# UK Engineering Tracker

A self-updating tracker for UK engineering graduate schemes — deadlines,
disciplines, and locations for 200+ employers, refreshed automatically.

**Live site:** https://eng-tracker-tawny.vercel.app/

## What it does

Most graduate scheme trackers rely on someone manually checking company
career pages and updating a spreadsheet. This one doesn't. A scraper on a
small VPS checks every employer's careers page every 6 hours, flags
anything that looks like a new grad scheme opening, and emails an alert
for a quick human check before it goes live. No manual scraping, no stale
data sitting for weeks.

## How it works

```
company careers pages
        ↓ Playwright scraper, every 6h
change detector (content hash + keyword match)
        ↓ on match
email alert → human verifies → adds row to Google Sheet
        ↓
GitHub Action, every 6h
        ↓
static site (Vercel)
```

See [`SPEC.md`](./SPEC.md) for full architecture, current status, and known
issues (notably: Workday-hosted career pages are currently blocked from the
scraper's VPS and are skipped — tracked in SPEC.md).

## Stack

Plain HTML/CSS/JS frontend (no build step), Python scraper (Playwright),
Google Sheets as the editorial layer, GitHub Actions for the sync pipeline,
Vercel for hosting, Resend for email alerts.

## Running the scraper locally

```bash
cd scraper
pip install -r requirements.txt
playwright install chromium
python detector.py            # single run
python detector.py --report   # print current tracked status
```

## Regenerating the site data

```bash
python scripts/sheet_to_js.py --local path/to/sheet-export.csv
```

## Status

Live and running. See [`SPEC.md`](./SPEC.md) for the current build phase and
priorities.
