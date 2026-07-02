"""
Company URL validator — field-agnostic reachability + ATS-type check.

Takes any companies.csv-shaped file (id, employer, careers_url, ats_type,
disciplines) and checks whether each careers_url is actually alive. Two-tier
check: a fast concurrent HTTP request first, falling back to a real
Playwright browser fetch only for rows that failed — a plain HTTP 403 is
often bot-protection rather than a real dead link, and a full browser fetch
tells the two apart.

This has no field-specific logic (nothing here assumes "engineering") — it's
the reusable half of the discovery/validation pipeline. The other half
(finding candidate companies and their URLs in the first place) still needs
a human or an LLM with search access; this script only verifies.

Usage:
    python scraper/validate_companies.py
        # validates scraper/output/companies.csv in place, writes a report

    python scraper/validate_companies.py --input candidates.csv --output validated.csv
        # validates a candidate batch before merging into companies.csv

    python scraper/validate_companies.py --requests-only
        # skip the Playwright fallback (faster, but reports more false-dead)
"""

import argparse
import csv
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.stdout.reconfigure(line_buffering=True)  # so redirected/background runs show live progress

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scraper.detector import detect_ats_from_url  # noqa: E402

DEFAULT_INPUT = ROOT / "scraper" / "output" / "companies.csv"

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
REQUEST_TIMEOUT = 15
PLAYWRIGHT_TIMEOUT = 20000  # ms
REQUEST_WORKERS = 20
TIER2_DELAY_RANGE = (3.0, 6.0)  # seconds between Tier 2 checks, jittered
TIER2_FRESH_CONTEXT_EVERY = 15  # recreate the browser context periodically


def check_via_requests(url):
    """Fast path. Returns (status, final_url) or None on hard failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        return r.status_code, str(r.url)
    except Exception:
        return None


def check_via_playwright(page, url, retries=1):
    """
    Slow, accurate fallback for anything the fast path couldn't confirm alive.
    Retries once on a navigation exception (timeout, transient network blip) —
    a raised exception means we don't know the real status, unlike a clean
    4xx/5xx response, so treating it as "dead" on the first try produces false
    negatives on otherwise-working sites.
    """
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = page.goto(url, timeout=PLAYWRIGHT_TIMEOUT, wait_until="domcontentloaded")
            status = resp.status if resp else None
            page.wait_for_timeout(1500)
            return status, page.url
        except Exception as e:
            last_exc = e
    return None, url


def validate_batch(rows, requests_only=False):
    """
    Two-tier validation. Returns rows with added fields:
    check_status ('ok'/'dead'), resolved_url, check_method, detected_ats, ats_mismatch.
    """
    print(f"Tier 1: checking {len(rows)} URLs via concurrent HTTP requests...")
    tier1 = {}
    with ThreadPoolExecutor(max_workers=REQUEST_WORKERS) as ex:
        futures = {ex.submit(check_via_requests, r["careers_url"]): r["id"] for r in rows}
        for fut in as_completed(futures):
            tier1[futures[fut]] = fut.result()

    needs_tier2 = []
    for r in rows:
        result = tier1[r["id"]]
        if result and 200 <= result[0] < 400:
            r["check_status"] = "ok"
            r["resolved_url"] = result[1]
            r["check_method"] = "requests"
            r["check_detail"] = str(result[0])
        else:
            needs_tier2.append(r)

    print(f"Tier 1 result: {len(rows) - len(needs_tier2)} confirmed alive, "
          f"{len(needs_tier2)} need browser verification.")

    if needs_tier2 and not requests_only:
        print(f"Tier 2: re-checking {len(needs_tier2)} via real browser, "
              f"{TIER2_DELAY_RANGE[0]}-{TIER2_DELAY_RANGE[1]}s apart (bot-protection often "
              f"causes false negatives at tier 1 AND under sustained rapid-fire tier 2 — a prior "
              f"run flagged a site 'dead' that a slower manual check confirmed was fine)...")
        import random
        import time
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent=HEADERS["User-Agent"])
            page = context.new_page()
            for i, r in enumerate(needs_tier2):
                if i > 0 and i % TIER2_FRESH_CONTEXT_EVERY == 0:
                    context.close()
                    context = browser.new_context(user_agent=HEADERS["User-Agent"])
                    page = context.new_page()
                status, resolved_url = check_via_playwright(page, r["careers_url"])
                if status and 200 <= status < 400:
                    r["check_status"] = "ok"
                else:
                    r["check_status"] = "dead"
                r["resolved_url"] = resolved_url
                r["check_method"] = "playwright"
                r["check_detail"] = str(status)
                print(f"  [{i+1}/{len(needs_tier2)}] {r['employer']}: "
                      f"{r['check_status']} ({status})")
                if i < len(needs_tier2) - 1:
                    time.sleep(random.uniform(*TIER2_DELAY_RANGE))
            context.close()
            browser.close()
    elif needs_tier2:
        for r in needs_tier2:
            r["check_status"] = "dead"
            r["resolved_url"] = tier1[r["id"]][1] if tier1[r["id"]] else r["careers_url"]
            r["check_method"] = "requests"
            r["check_detail"] = str(tier1[r["id"]][0]) if tier1[r["id"]] else "error"

    for r in rows:
        # Run URL-pattern ATS detection regardless of alive/dead status — it's
        # pure string matching, and it's useful precisely for dead rows too:
        # the declared ats_type field itself is sometimes wrong (several rows
        # are declared non-Workday but their URL is plainly a
        # *.myworkdayjobs.com path), so triage that relies on the declared
        # field alone under/over-counts the systemic-Workday-block bucket.
        url_for_detection = r.get("resolved_url") or r["careers_url"]
        detected = detect_ats_from_url(url_for_detection) or "Custom"
        r["detected_ats"] = detected
        r["ats_mismatch"] = detected != r.get("ats_type", "")

    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Input CSV (companies.csv shape)")
    parser.add_argument("--output", default=None, help="Output CSV path (default: <input>_validated.csv)")
    parser.add_argument("--requests-only", action="store_true", help="Skip the Playwright fallback")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.with_name(
        input_path.stem + "_validated.csv"
    )

    with open(input_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    rows = validate_batch(rows, requests_only=args.requests_only)

    out_fieldnames = fieldnames + ["check_status", "resolved_url", "check_method",
                                    "check_detail", "detected_ats", "ats_mismatch"]
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=out_fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    dead = [r for r in rows if r["check_status"] == "dead"]
    mismatched = [r for r in rows if r["ats_mismatch"]]
    print(f"\nDone. {len(rows) - len(dead)}/{len(rows)} alive, {len(dead)} dead.")
    if mismatched:
        print(f"{len(mismatched)} rows have a declared ats_type that doesn't match "
              f"the URL's detected type (worth a manual look):")
        for r in mismatched[:20]:
            print(f"  {r['employer']}: declared={r['ats_type']} detected={r['detected_ats']}")
    print(f"Report written to: {output_path}")


if __name__ == "__main__":
    main()
