"""
Frontend tests using Playwright.

Run: pytest tests/test_site.py
Requires: pip install pytest playwright pytest-playwright && playwright install chromium

These tests start a local server automatically via the fixture below.
"""

import subprocess
import time
import socket
import pytest
from playwright.sync_api import Page, expect


def find_free_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    """Serve the project root on a free port for the duration of the test session."""
    import os
    root = os.path.join(os.path.dirname(__file__), "..")
    port = find_free_port()
    proc = subprocess.Popen(
        ["python", "-m", "http.server", str(port)],
        cwd=root,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)  # give the server a moment to start
    yield f"http://localhost:{port}"
    proc.terminate()


def test_table_loads(page: Page, server):
    """T1: Table loads with at least 1 deadline row."""
    page.goto(server)
    rows = page.locator("tbody tr").filter(has_not=page.locator(".loading"))
    expect(rows.first).to_be_visible(timeout=5000)
    assert rows.count() >= 1


def test_filter_by_category(page: Page, server):
    """T2: Filtering by a category pill narrows results; 'All Schemes' restores the full set."""
    page.goto(server)
    page.wait_for_selector("tbody tr", timeout=5000)
    all_count = page.locator("tbody tr").count()

    page.click('.pill[data-category="Graduate Scheme"]')
    page.wait_for_timeout(300)
    filtered_count = page.locator("tbody tr").count()
    assert filtered_count >= 1, "Expected at least 1 Graduate Scheme row"
    assert filtered_count <= all_count

    page.click('.pill[data-category="all"]')
    page.wait_for_timeout(300)
    assert page.locator("tbody tr").count() == all_count


def test_sort_by_deadline(page: Page, server):
    """T3: Sort ascending puts earliest deadline first; rolling/TBC dates last."""
    page.goto(server)
    page.wait_for_selector("tbody tr", timeout=5000)
    # Click sort header to ensure ascending
    sort_col = page.locator("#sort-deadline")
    if "▼" in sort_col.inner_text():
        sort_col.click()
        page.wait_for_timeout(300)

    deadline_cells = page.locator("tbody tr td:nth-child(5) span").all_inner_texts()
    # Rolling/TBC entries should be at the end (not at the top)
    rolling_indices = [i for i, d in enumerate(deadline_cells) if d in ("Rolling", "TBC")]
    date_indices = [i for i, d in enumerate(deadline_cells) if d not in ("Rolling", "TBC")]
    if rolling_indices and date_indices:
        assert min(rolling_indices) > max(date_indices), "Rolling entries should be after dated entries"


def test_status_persists_on_reload(page: Page, server):
    """T4: Setting status to Applied → reload → status is still Applied."""
    page.goto(server)
    # Wait for rows to render
    page.wait_for_selector("select.status-select", timeout=5000)

    first_select = page.locator("select.status-select").first
    employer_id = first_select.get_attribute("id").replace("status-", "")

    first_select.select_option("Applied")
    page.wait_for_timeout(300)

    # Reload and check
    page.reload()
    page.wait_for_selector("select.status-select", timeout=5000)
    reloaded_select = page.locator(f"#status-{employer_id}")
    expect(reloaded_select).to_have_value("Applied")


def test_mobile_no_horizontal_scroll(page: Page, server):
    """T5: At 375px viewport width, table doesn't cause horizontal scroll."""
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(server)
    page.wait_for_selector("tbody tr", timeout=5000)

    scroll_width = page.evaluate("document.body.scrollWidth")
    client_width = page.evaluate("document.body.clientWidth")
    assert scroll_width <= client_width + 5, (
        f"Horizontal overflow at 375px: scrollWidth={scroll_width}, clientWidth={client_width}"
    )
