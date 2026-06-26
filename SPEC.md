# UK Engineering Tracker — Build Spec

## What we're building
A self-updating UK engineering graduate scheme tracker. The site shows 300+ employers,
disciplines, deadlines, locations. Data stays fresh automatically — within hours of a
company posting a new listing.

## Architecture

```
Sheet 1: Master company list (name + careers URL + ATS type)
        ↓ every 6 hours (cron on VPS)
Playwright scraper visits each URL
        ↓
Change detector (hash comparison)
        ↓ if changed
ATS parser (Workday / Taleo / SAP / manual fallback)
        ↓
Auto-extracts: scheme name, deadline, location, disciplines
        ↓
Notification sent (email/Slack) for manual verification
        ↓
Verified entry added to Sheet 2
        ↓
GitHub Action: Sheet 2 → deadlines.js → Vercel deploy
```

## Build Phases

### Phase 1 — Company list (CURRENT)
- [ ] Generate 300+ UK engineering employers with careers URLs
- [ ] Identify ATS type for each (Workday / Taleo / SAP / custom)
- [ ] Store in Google Sheet (Sheet 1)
- Columns: id | employer | careers_url | ats_type | disciplines | verified

### Phase 2 — Change detector
- [ ] Python + Playwright script
- [ ] Visits each careers URL every 6 hours
- [ ] Stores MD5 hash of page content in SQLite
- [ ] On change: searches for keywords (graduate, 2027, scheme, applications open)
- [ ] Flags matches for ATS parser
- File: scraper/detector.py

### Phase 3 — ATS parsers
- [ ] Workday parser — covers ~40% of targets
- [ ] Taleo parser
- [ ] SAP SuccessFactors parser
- [ ] Manual fallback for custom pages
- Extracts: scheme_name, deadline, opening_date, location, disciplines, url
- File: scraper/parsers/workday.py, taleo.py, sap.py

### Phase 4 — Notification system
- [ ] Email alert via Gmail SMTP (or Slack webhook)
- [ ] Alert includes: company, scheme name, detected deadline, confidence score
- [ ] You approve → entry moves to Sheet 2
- [ ] You reject → entry ignored until next change detected
- File: scraper/notify.py

### Phase 5 — Sheet → Site pipeline
- [ ] Google Sheet published as CSV (Sheet 2, verified=TRUE rows only)
- [ ] GitHub Action runs nightly: pulls CSV → generates deadlines.js → commits
- [ ] Vercel auto-deploys on commit
- File: .github/workflows/sync-sheet.yml

## Tech Stack
- Python 3.11+
- Playwright (headless Chromium)
- SQLite (page hash storage)
- Google Sheets API or publish-as-CSV
- GitHub Actions
- Vercel (existing)
- VPS: Hetzner CX11 (~£4/month) or DigitalOcean Droplet

## ATS Detection
- Workday: URL contains "myworkdayjobs.com" or "wd3.myworkday.com"
- Taleo: URL contains "taleo.net"
- SAP SuccessFactors: URL contains "successfactors.com"
- Greenhouse: URL contains "greenhouse.io"
- Custom: anything else → manual fallback

## Key Files
- /data/deadlines.js — live site data (auto-generated, do not edit manually)
- /data/deadlines.json — source of truth for site data
- /scraper/companies.csv — master company list (Sheet 1 export)
- /scraper/detector.py — change detection script
- /scraper/parsers/ — ATS-specific parsers
- /scraper/notify.py — notification system
- /scraper/db.sqlite — page hash storage (gitignored)
- /.github/workflows/sync-sheet.yml — Sheet → site pipeline
- /SPEC.md — this file

## Current Status
Phase 1 in progress. Company list being built.

## Start each session by reading this file.
