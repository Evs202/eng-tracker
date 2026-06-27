"""
Phase 4 — Email notifications via Resend.
Called by detector.py after each run when flagged listings are found.

Environment variables required (set on VPS):
    RESEND_API_KEY   — from resend.com dashboard
    ALERT_EMAIL_TO   — recipient (e.g. grishkoevsey74@gmail.com)
    ALERT_EMAIL_FROM — sender (e.g. alerts@eng-tracker.com or onboarding@resend.dev for testing)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

RESEND_API_URL = "https://api.resend.com/emails"


def send_alert(flagged: list) -> bool:
    """
    Send an email listing all flagged companies.
    Returns True on success.
    """
    api_key  = os.environ.get("RESEND_API_KEY", "")
    to_email = os.environ.get("ALERT_EMAIL_TO", "grishkoevsey74@gmail.com")
    from_email = os.environ.get("ALERT_EMAIL_FROM", "onboarding@resend.dev")

    if not api_key:
        print("[notifier] RESEND_API_KEY not set — skipping email")
        return False

    if not flagged:
        return True

    now = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    count = len(flagged)
    subject = f"[Eng Tracker] {count} new grad scheme{'s' if count > 1 else ''} detected — {now}"

    # Build plain text body
    lines = [
        f"Eng Tracker detected {count} change{'s' if count > 1 else ''} that may indicate new grad scheme openings.",
        f"Checked at: {now}",
        "",
    ]
    for item in flagged:
        lines.append(f"  {item['employer']}")
        lines.append(f"  URL:      {item.get('final_url') or item['careers_url']}")
        lines.append(f"  ATS:      {item['ats_type']}")
        lines.append(f"  Keywords: {', '.join(item['keywords'])}")
        lines.append("")

    lines += [
        "---",
        "This is an automated alert from your UK Engineering Graduate Scheme Tracker.",
        "Go verify these listings and add confirmed ones to the Google Sheet.",
    ]

    text_body = "\n".join(lines)

    # Build HTML body
    rows_html = ""
    for item in flagged:
        url = item.get("final_url") or item["careers_url"]
        kws = ", ".join(item["keywords"])
        rows_html += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee;font-weight:600">{item['employer']}</td>
          <td style="padding:10px;border-bottom:1px solid #eee">{item['ats_type']}</td>
          <td style="padding:10px;border-bottom:1px solid #eee">
            <a href="{url}" style="color:#2563eb">{url}</a>
          </td>
          <td style="padding:10px;border-bottom:1px solid #eee;color:#666;font-size:13px">{kws}</td>
        </tr>"""

    html_body = f"""
    <div style="font-family:sans-serif;max-width:700px;margin:0 auto;padding:24px">
      <h2 style="color:#1e293b;margin-bottom:4px">
        {count} grad scheme change{'s' if count > 1 else ''} detected
      </h2>
      <p style="color:#64748b;margin-top:0">{now}</p>

      <table style="width:100%;border-collapse:collapse;margin-top:16px">
        <thead>
          <tr style="background:#f8fafc">
            <th style="padding:10px;text-align:left;color:#475569;font-size:13px">Employer</th>
            <th style="padding:10px;text-align:left;color:#475569;font-size:13px">ATS</th>
            <th style="padding:10px;text-align:left;color:#475569;font-size:13px">URL</th>
            <th style="padding:10px;text-align:left;color:#475569;font-size:13px">Keywords</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>

      <p style="margin-top:24px;color:#64748b;font-size:13px">
        Verify these listings and add confirmed ones to the
        <a href="https://docs.google.com/spreadsheets" style="color:#2563eb">Google Sheet</a>.
      </p>
      <p style="color:#94a3b8;font-size:12px">UK Engineering Graduate Scheme Tracker — automated alert</p>
    </div>"""

    payload = json.dumps({
        "from":    from_email,
        "to":      [to_email],
        "subject": subject,
        "text":    text_body,
        "html":    html_body,
    }).encode("utf-8")

    import subprocess
    try:
        result = subprocess.run([
            "curl", "-s", "-w", "\n%{http_code}",
            "-X", "POST",
            "-H", f"Authorization: Bearer {api_key}",
            "-H", "Content-Type: application/json",
            "-d", payload.decode("utf-8"),
            RESEND_API_URL,
        ], capture_output=True, text=True, timeout=20)
        lines = result.stdout.strip().split("\n")
        status = int(lines[-1]) if lines else 0
        body = "\n".join(lines[:-1])
        if status == 200:
            data = json.loads(body)
            print(f"[notifier] Email sent — id={data.get('id')}")
            return True
        else:
            print(f"[notifier] HTTP {status}: {body}")
            return False
    except Exception as e:
        print(f"[notifier] Error: {e}")
        return False


if __name__ == "__main__":
    # Quick test — sends a test email with dummy data
    test_flagged = [
        {
            "employer":    "Test Company",
            "careers_url": "https://example.com/careers",
            "final_url":   "https://example.com/careers/graduate",
            "ats_type":    "Custom",
            "keywords":    ["graduate scheme", "2027", "applications open"],
        }
    ]
    success = send_alert(test_flagged)
    print("Test result:", "OK" if success else "FAILED")
