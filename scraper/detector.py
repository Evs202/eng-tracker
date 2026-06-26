"""
Phase 2 — Change Detector
Visits every careers URL in companies.csv every 6 hours.
Stores a content hash in SQLite. On change, checks for grad scheme keywords
and flags matches for the ATS parser + notification system.

Usage:
    pip install playwright
    playwright install chromium
    python scraper/detector.py              # run once
    python scraper/detector.py --report     # print current status table

Run on a schedule (VPS cron):
    0 */6 * * * cd /path/to/eng-tracker && python scraper/detector.py
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

ROOT         = Path(__file__).parent.parent
COMPANIES_CSV = ROOT / "scraper" / "output" / "companies.csv"
DB_PATH      = ROOT / "scraper" / "db.sqlite"
LOG_PATH     = ROOT / "scraper" / "output" / "detector.log"
FLAGGED_PATH = ROOT / "scraper" / "output" / "flagged.json"

GRAD_KEYWORDS = [
    "graduate scheme", "graduate programme", "graduate program",
    "grad scheme", "grad programme",
    "2027", "applications open", "apply now",
    "industrial placement", "summer internship", "spring week",
    "entry level", "early careers", "school leaver",
]

# Page must contain at least this many keywords to be flagged
KEYWORD_THRESHOLD = 2

PAGE_TIMEOUT = 30000   # ms
DELAY_BETWEEN = 2.0    # seconds between requests — be polite

# ── Logging ───────────────────────────────────────────────────────────────────

os.makedirs(LOG_PATH.parent, exist_ok=True)

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True, end="\n")
    try:
        sys.stdout.flush()
    except Exception:
        pass
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ── Database ──────────────────────────────────────────────────────────────────

def init_db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS page_hashes (
            id            TEXT PRIMARY KEY,
            employer      TEXT,
            careers_url   TEXT,
            ats_type      TEXT,
            content_hash  TEXT,
            http_status   INTEGER,
            last_checked  TEXT,
            last_changed  TEXT,
            check_count   INTEGER DEFAULT 0,
            error         TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS change_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id  TEXT,
            employer    TEXT,
            careers_url TEXT,
            ats_type    TEXT,
            detected_at TEXT,
            keywords_found TEXT,
            keyword_count  INTEGER,
            flagged     INTEGER DEFAULT 0
        )
    """)
    con.commit()
    return con

def upsert_hash(con, row):
    con.execute("""
        INSERT INTO page_hashes
            (id, employer, careers_url, ats_type, content_hash, http_status,
             last_checked, last_changed, check_count, error)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            content_hash = excluded.content_hash,
            http_status  = excluded.http_status,
            last_checked = excluded.last_checked,
            last_changed = CASE
                WHEN content_hash != excluded.content_hash THEN excluded.last_changed
                ELSE last_changed
            END,
            check_count  = check_count + 1,
            error        = excluded.error
    """, (
        row["id"], row["employer"], row["careers_url"], row["ats_type"],
        row["content_hash"], row["http_status"],
        row["last_checked"], row["last_changed"],
        0, row["error"]
    ))
    con.commit()

def get_previous_hash(con, company_id):
    cur = con.execute(
        "SELECT content_hash FROM page_hashes WHERE id = ?", (company_id,)
    )
    result = cur.fetchone()
    return result[0] if result else None

def log_change(con, company, keywords_found):
    con.execute("""
        INSERT INTO change_log
            (company_id, employer, careers_url, ats_type, detected_at,
             keywords_found, keyword_count, flagged)
        VALUES (?,?,?,?,?,?,?,?)
    """, (
        company["id"], company["employer"], company["careers_url"],
        company["ats_type"],
        datetime.now(timezone.utc).isoformat(),
        json.dumps(keywords_found),
        len(keywords_found),
        1 if len(keywords_found) >= KEYWORD_THRESHOLD else 0
    ))
    con.commit()

# ── ATS detection ─────────────────────────────────────────────────────────────

def detect_ats_from_url(url):
    url = url.lower()
    if "myworkdayjobs.com" in url or "wd3.myworkday.com" in url or "myworkday.com" in url:
        return "Workday"
    if "taleo.net" in url:
        return "Taleo"
    if "successfactors.com" in url or "sap.com" in url:
        return "SAP"
    if "greenhouse.io" in url:
        return "Greenhouse"
    if "smartrecruiters.com" in url:
        return "SmartRecruiters"
    if "lever.co" in url:
        return "Lever"
    if "bamboohr.com" in url:
        return "BambooHR"
    return None  # unknown — keep existing

# ── Page fetching ─────────────────────────────────────────────────────────────

def fetch_page(page, url):
    """
    Returns (text_content, final_url, http_status).
    text_content is lowercased page text for keyword matching.
    """
    try:
        response = page.goto(url, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
        status = response.status if response else 0

        # Wait a moment for JS to render
        page.wait_for_timeout(2000)

        # Extract visible text
        text = page.evaluate("() => document.body ? document.body.innerText : ''")
        final_url = page.url

        # Detect ATS from final URL (after redirects)
        return text, final_url, status

    except Exception as e:
        return None, url, 0

def hash_content(text):
    if not text:
        return "EMPTY"
    # Normalise whitespace before hashing to reduce noise
    normalised = re.sub(r"\s+", " ", text.strip())
    return hashlib.md5(normalised.encode("utf-8")).hexdigest()

def find_keywords(text):
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in GRAD_KEYWORDS if kw in text_lower]

# ── Main ──────────────────────────────────────────────────────────────────────

def load_companies():
    if not COMPANIES_CSV.exists():
        log(f"companies.csv not found at {COMPANIES_CSV}", "ERROR")
        sys.exit(1)
    companies = []
    with open(COMPANIES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            companies.append(row)
    return companies

def run_detector():
    from playwright.sync_api import sync_playwright

    companies = load_companies()
    log(f"Loaded {len(companies)} companies from {COMPANIES_CSV}")

    con = init_db()
    flagged = []
    errors = []
    changed = []

    now = datetime.now(timezone.utc).isoformat()

    chromium_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    launch_kwargs = {"headless": True}
    if chromium_path:
        launch_kwargs["executable_path"] = chromium_path

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        for i, company in enumerate(companies):
            cid  = company["id"]
            name = company["employer"]
            url  = company["careers_url"]
            ats  = company["ats_type"]

            log(f"[{i+1}/{len(companies)}] {name} — {url}")

            prev_hash = get_previous_hash(con, cid)

            text, final_url, status = fetch_page(page, url)

            # Detect ATS from final URL if redirected to known ATS
            detected_ats = detect_ats_from_url(final_url)
            if detected_ats and detected_ats != ats:
                log(f"  ATS detected from redirect: {ats} → {detected_ats}")
                ats = detected_ats

            current_hash = hash_content(text)
            error_msg = "" if status else "fetch_failed"

            if status == 0:
                log(f"  ERROR: could not fetch (status={status})", "WARN")
                errors.append({"id": cid, "employer": name, "url": url})
            elif status >= 400:
                log(f"  HTTP {status}", "WARN")
                errors.append({"id": cid, "employer": name, "url": url, "status": status})

            # Compare hashes
            hash_changed = prev_hash is not None and current_hash != prev_hash
            is_new       = prev_hash is None

            if hash_changed:
                log(f"  CHANGED (prev={prev_hash[:8]}… now={current_hash[:8]}…)")
                keywords = find_keywords(text)
                log(f"  Keywords found: {keywords}")
                log_change(con, {**company, "ats_type": ats}, keywords)

                if len(keywords) >= KEYWORD_THRESHOLD:
                    log(f"  *** FLAGGED — {len(keywords)} keywords, ATS={ats} ***")
                    flagged.append({
                        "id":            cid,
                        "employer":      name,
                        "careers_url":   url,
                        "final_url":     final_url,
                        "ats_type":      ats,
                        "keywords":      keywords,
                        "keyword_count": len(keywords),
                        "detected_at":   now,
                    })
                changed.append(name)

            elif is_new:
                log(f"  NEW — first visit, storing hash")
                keywords = find_keywords(text)
                if keywords:
                    log(f"  Keywords on first visit: {keywords}")

            else:
                log(f"  No change")

            upsert_hash(con, {
                "id":           cid,
                "employer":     name,
                "careers_url":  url,
                "ats_type":     ats,
                "content_hash": current_hash,
                "http_status":  status,
                "last_checked": now,
                "last_changed": now if hash_changed else None,
                "error":        error_msg,
            })

            time.sleep(DELAY_BETWEEN)

        context.close()
        browser.close()

    # Write flagged entries for notification system (Phase 4)
    with open(FLAGGED_PATH, "w", encoding="utf-8") as f:
        json.dump(flagged, f, indent=2)

    # Summary
    log("-" * 60)
    log(f"Run complete.")
    log(f"  Total companies checked: {len(companies)}")
    log(f"  Pages changed:           {len(changed)}")
    log(f"  Flagged (grad keywords): {len(flagged)}")
    log(f"  Errors (bad URL/fetch):  {len(errors)}")
    log(f"  Flagged saved to:        {FLAGGED_PATH}")

    if errors:
        log("-" * 60)
        log("URLs to fix:")
        for e in errors:
            log(f"  {e['employer']} — {e['url']}")

    con.close()
    return flagged, errors

def print_report():
    if not DB_PATH.exists():
        print("No database yet. Run detector.py first.")
        return

    con = sqlite3.connect(DB_PATH)
    rows = con.execute("""
        SELECT employer, http_status, last_checked, last_changed, check_count, error
        FROM page_hashes
        ORDER BY employer
    """).fetchall()

    print(f"\n{'Employer':<35} {'Status':>6}  {'Last checked':<22}  {'Last changed':<22}  Checks  Error")
    print("─" * 120)
    for r in rows:
        employer, status, checked, changed, count, error = r
        changed_str = changed[:19] if changed else "—"
        checked_str = checked[:19] if checked else "—"
        error_str   = error or ""
        print(f"{employer:<35} {status or 0:>6}  {checked_str:<22}  {changed_str:<22}  {count or 0:>5}  {error_str}")

    flagged = con.execute(
        "SELECT COUNT(*) FROM change_log WHERE flagged = 1"
    ).fetchone()[0]
    print(f"\nTotal flagged changes: {flagged}")
    con.close()

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true", help="Print status report")
    args = parser.parse_args()

    if args.report:
        print_report()
    else:
        run_detector()
