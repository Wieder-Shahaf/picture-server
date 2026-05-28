"""End-to-end UI test driving the PictureServer browser app.

Not part of the graded test suite — kept here for local verification.
Run with:  python tests/e2e_playwright.py
"""
import os
import sys
import time
import uuid
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://localhost:15000")
FIXTURE_PNG = Path(__file__).parent / "fixtures" / "tiny.png"
SCREENSHOT_DIR = Path(__file__).parent / "_e2e_screens"
SCREENSHOT_DIR.mkdir(exist_ok=True)


def step(name):
    print(f"\n▶ {name}")


def run():
    user = f"e2e_{uuid.uuid4().hex[:8]}"
    password = "Password!123"
    failures = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        # log console errors as test signal
        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        # 1) Load home
        step("loading /")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        page.screenshot(path=SCREENSHOT_DIR / "01_home.png", full_page=True)

        try:
            expect(page.locator(".brand-mark")).to_contain_text("Picture")
            expect(page.locator(".gh")).to_contain_text("VIEW ON GITHUB")
            assert "Wieder-Shahaf" in page.locator(".gh").get_attribute("href")
            print("  ✓ brand and GitHub link present, points at Wieder-Shahaf")
        except Exception as e:
            failures.append(f"home layout: {e}")

        # 2) Switch to register tab and create a new account
        step("registering a new user")
        page.locator('button.mtab[data-mtab="register"]').click()
        page.locator('input[name="username"]').fill(user)
        page.locator('input[name="password"]').fill(password)
        page.locator('#auth-form button[type="submit"]').click()
        try:
            expect(page.locator("#card-session")).to_be_visible(timeout=10000)
            expect(page.locator("#who")).to_have_text(user)
            print(f"  ✓ session card visible as {user}")
        except Exception as e:
            failures.append(f"register/login: {e}")
        page.screenshot(path=SCREENSHOT_DIR / "02_logged_in.png", full_page=True)

        # 3) Live ticker populates from /status
        step("checking live ticker metrics")
        page.wait_for_function("document.querySelector('#m-api').textContent.includes('v1')", timeout=10000)
        try:
            health_text = page.locator("#m-health").text_content().strip()
            api_text = page.locator("#m-api").text_content().strip()
            success_text = page.locator("#m-success").text_content().strip()
            assert health_text in ("ok", "error"), f"unexpected health: {health_text!r}"
            assert api_text == "v1", f"unexpected api: {api_text!r}"
            assert success_text.isdigit(), f"success not numeric: {success_text!r}"
            print(f"  ✓ ticker: health={health_text} api={api_text} success={success_text}")
        except Exception as e:
            failures.append(f"ticker: {e}")

        # 4) Upload a real PNG via file input
        step("uploading PNG via /classifier")
        page.locator("#file").set_input_files(str(FIXTURE_PNG))
        page.wait_for_selector("#preview-img[src^='data:image']", timeout=3000)
        page.locator("#btn-classify").click()
        page.wait_for_selector("#results .row", timeout=60000)
        try:
            rows = page.locator("#results .row").all()
            assert rows, "no result rows"
            for r in rows:
                score_text = r.locator(".score").text_content().rstrip("%")
                score = float(score_text)
                assert 0 < score <= 100, f"bad score: {score_text}"
            print(f"  ✓ {len(rows)} match rows rendered, all scores in (0, 100]")
        except Exception as e:
            failures.append(f"classifier result render: {e}")
        page.screenshot(path=SCREENSHOT_DIR / "03_classify.png", full_page=True)

        # 5) HTTP log sidebar shows entries
        step("checking HTTP log sidebar")
        try:
            entries = page.locator(".log-entry").all()
            assert len(entries) >= 3, f"expected at least 3 log entries, got {len(entries)}"
            ok_entries = page.locator(".log-entry.ok").all()
            assert ok_entries, "no successful (.log-entry.ok) entries logged"
            print(f"  ✓ {len(entries)} log entries, {len(ok_entries)} successful")
        except Exception as e:
            failures.append(f"http log: {e}")

        # 6) Status updates after classify (success counter should be >= 1)
        step("verifying success counter updated")
        time.sleep(1)
        try:
            page.wait_for_function("parseInt(document.querySelector('#m-success').textContent) >= 1", timeout=8000)
            print(f"  ✓ success counter advanced to {page.locator('#m-success').text_content()}")
        except Exception as e:
            failures.append(f"success counter: {e}")

        # 7) Logout and verify session is gone
        step("logging out")
        page.locator("#btn-logout").click()
        try:
            expect(page.locator("#card-auth")).to_be_visible(timeout=3000)
            expect(page.locator("#card-session")).to_be_hidden()
            print("  ✓ auth form back; session card hidden")
        except Exception as e:
            failures.append(f"logout: {e}")
        page.screenshot(path=SCREENSHOT_DIR / "04_logged_out.png", full_page=True)

        # 8) Console hygiene
        step("checking console errors")
        if console_errors:
            failures.append(f"console errors: {console_errors}")
        else:
            print("  ✓ no console errors")

        # 9) Tab navigation works
        step("clicking tab strip → /classify tab should scroll the section into view")
        page.locator('.tabs .tab[data-tab="classify"]').click()
        time.sleep(0.6)
        try:
            box = page.locator("#classify").bounding_box()
            assert box and box["y"] < 600, f"#classify not scrolled into view (y={box and box['y']})"
            print(f"  ✓ #classify scrolled to y={box['y']:.0f}")
        except Exception as e:
            failures.append(f"tab scroll: {e}")

        ctx.close()
        browser.close()

    print("\n" + "=" * 60)
    if failures:
        print(f"❌ {len(failures)} failure(s):")
        for f in failures:
            print(f"   - {f}")
        sys.exit(1)
    print("✅ all 9 UI checks passed")
    print(f"   screenshots → {SCREENSHOT_DIR}")


if __name__ == "__main__":
    run()
