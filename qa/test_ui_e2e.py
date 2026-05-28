"""Playwright-driven UI stress: keyboard nav, console errors, the
client-side image normalization across formats, log filtering."""
import os
import time
import uuid
from pathlib import Path
from io import BytesIO

import pytest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    pytest.skip("playwright not installed", allow_module_level=True)

from PIL import Image

BASE_URL = os.environ.get("BASE_URL", "http://localhost:15000")
FIX = Path(__file__).parent / "_fixtures"
FIX.mkdir(exist_ok=True)


def _png():
    p = FIX / "ui_ok.png"
    if not p.exists():
        Image.new("RGB", (96, 96), (110, 50, 200)).save(p, "PNG")
    return p


def _webp():
    p = FIX / "ui_ok.webp"
    if not p.exists():
        Image.new("RGB", (64, 64), "green").save(p, "WEBP")
    return p


def _gif():
    p = FIX / "ui_ok.gif"
    if not p.exists():
        Image.new("RGB", (64, 64), "orange").save(p, "GIF")
    return p


def _bmp():
    p = FIX / "ui_ok.bmp"
    if not p.exists():
        Image.new("RGB", (64, 64), "teal").save(p, "BMP")
    return p


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


def _open_logged_in(browser, viewport=(1280, 800)):
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(BASE_URL, wait_until="networkidle")
    u = f"e2e_{uuid.uuid4().hex[:8]}"
    page.locator('input[name="username"]').fill(u)
    page.locator('input[name="password"]').fill("pw")
    page.locator('#mode-toggle').click()
    page.locator('#auth-form button[type="submit"]').click()
    page.wait_for_function("document.documentElement.dataset.auth === 'in'", timeout=10000)
    time.sleep(0.4)
    return ctx, page, errors


def test_no_console_errors_on_initial_load(browser):
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.goto(BASE_URL, wait_until="networkidle"); time.sleep(0.5)
    assert not errors, f"console errors on load: {errors}"
    ctx.close()


def test_full_flow_no_console_errors(browser):
    ctx, page, errors = _open_logged_in(browser)
    page.set_input_files("#file", str(_png()))
    page.wait_for_function("!document.querySelector('#staged').hidden", timeout=5000)
    page.locator("#btn-classify").click()
    page.wait_for_selector("#results .row", timeout=60000)
    time.sleep(0.4)
    assert not errors, f"console errors during flow: {errors}"
    ctx.close()


def test_dropzone_hides_when_file_staged(browser):
    ctx, page, _ = _open_logged_in(browser)
    page.set_input_files("#file", str(_png()))
    page.wait_for_function("!document.querySelector('#staged').hidden", timeout=5000)
    dz_visible = page.locator("#dropzone").is_visible()
    assert not dz_visible, "dropzone should be hidden once a file is staged"
    ctx.close()


def test_dropzone_returns_when_file_removed(browser):
    ctx, page, _ = _open_logged_in(browser)
    page.set_input_files("#file", str(_png()))
    page.wait_for_function("!document.querySelector('#staged').hidden", timeout=5000)
    page.locator("#btn-remove-file").click()
    time.sleep(0.3)
    assert page.locator("#dropzone").is_visible()
    assert page.locator("#staged").is_visible() is False or page.locator("#staged").get_attribute("hidden") is not None
    ctx.close()


@pytest.mark.parametrize("fixture_fn,note_fragment", [
    (_png,  None),                      # native PNG, no note
    (_webp, "transcoded webp"),
    (_gif,  "transcoded gif"),
    (_bmp,  "transcoded bmp"),
])
def test_multi_format_normalization(browser, fixture_fn, note_fragment):
    ctx, page, _ = _open_logged_in(browser)
    page.set_input_files("#file", str(fixture_fn()))
    page.wait_for_function("!document.querySelector('#staged').hidden", timeout=5000)
    meta = page.locator("#preview-size").inner_text()
    name = page.locator("#preview-name").inner_text()
    if note_fragment:
        assert note_fragment in meta, f"expected note '{note_fragment}' in meta '{meta}'"
        assert name.endswith(".jpeg"), f"transcoded file should be .jpeg, got {name}"
    page.locator("#btn-classify").click()
    page.wait_for_selector("#results .row", timeout=60000)
    rows = page.locator("#results .row").count()
    assert rows > 0, f"no result rows after classify of {fixture_fn.__name__}"
    ctx.close()


def test_log_only_shows_meaningful_entries(browser):
    """The /status polls every 5s must be silent — only POST /register,
       /login, /logout, /classifier should appear in the log."""
    ctx, page, _ = _open_logged_in(browser)
    page.set_input_files("#file", str(_png()))
    page.locator("#btn-classify").click()
    page.wait_for_selector("#results .row", timeout=60000)
    # let two poll cycles pass (10s)
    time.sleep(11)
    entries = page.locator(".log-entry .row1 .who").all_inner_texts()
    # registration + login + classifier → 3 entries; /status polls should NOT be there
    assert len(entries) == 3, f"expected 3 meaningful entries, got {entries}"
    for e in entries:
        assert "/STATUS" not in e.upper(), f"silent /status leaked into log: {e}"
    ctx.close()


def test_status_strip_horizontal_scroll_on_mobile(browser):
    ctx = browser.new_context(viewport={"width": 360, "height": 700},
                              device_scale_factor=2)
    page = ctx.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    u = f"e2e_{uuid.uuid4().hex[:8]}"
    page.locator('input[name="username"]').fill(u)
    page.locator('input[name="password"]').fill("pw")
    page.locator('#mode-toggle').click()
    page.locator('#auth-form button[type="submit"]').click()
    page.wait_for_function("document.documentElement.dataset.auth === 'in'", timeout=10000)
    time.sleep(0.5)
    wraps = page.evaluate("""
        () => {
          const cells = [...document.querySelectorAll('.status-live .cell')];
          if (cells.length < 2) return null;
          const t0 = cells[0].offsetTop;
          return cells.some(c => c.offsetTop !== t0);
        }
    """)
    assert wraps is False, "status-live cells must NOT wrap to a 2nd row on mobile"
    overflowing = page.evaluate("""
        () => {
          const s = document.querySelector('.status-strip');
          return s.scrollWidth > s.clientWidth + 2;
        }
    """)
    assert overflowing, "expected horizontal overflow → scrollable on 360px width"
    ctx.close()


def test_logout_clears_localstorage_and_session(browser):
    ctx, page, _ = _open_logged_in(browser)
    has_token_before = page.evaluate("() => !!localStorage.getItem('ps_token')")
    assert has_token_before
    page.locator("#btn-logout").click()
    page.wait_for_function("document.documentElement.dataset.auth === 'out'", timeout=4000)
    has_token_after = page.evaluate("() => !!localStorage.getItem('ps_token')")
    assert not has_token_after, "localStorage token must be cleared on logout"
    ctx.close()
