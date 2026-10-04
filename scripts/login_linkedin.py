#!/usr/bin/env python3
"""
login_linkedin.py - Interactive visible Chrome session helper for LinkedIn.
Opens a visible Chrome window for the user to log into LinkedIn or complete 2FA.
Once logged in, it detects the session, saves it permanently to ~/.chrome_linkedin_profile
and exports storage_state to job-hunter/sessions/linkedin_state.json.
"""

import os
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = SESSIONS_DIR / "linkedin_state.json"
PROFILE_DIR = os.path.expanduser("~/.chrome_linkedin_profile")


def is_authenticated(page) -> bool:
    try:
        curr_url = page.url.lower()
        if any(k in curr_url for k in ["/uas/login", "/checkpoint", "/signup", "session_redirect"]):
            return False
        title_lower = page.title().lower()
        if any(k in title_lower for k in ["sign up", "sign in", "login", "log in", "join linkedin"]):
            return False
        has_nav = page.locator('#global-nav, nav.global-nav, .global-nav__me, button.global-nav__primary-link').count() > 0
        if has_nav or "feed" in curr_url or "jobs" in curr_url:
            return True
        return False
    except Exception:
        return False


def main():
    print("\n" + "=" * 70)
    print("         LINKEDIN INTERACTIVE LOGIN & SESSION VERIFIER")
    print("=" * 70)
    print("Opening a visible Chrome browser on your screen...")
    print("Please log into LinkedIn (or confirm your session / 2FA).")
    print("The system will automatically detect when you are logged in.")
    print("=" * 70 + "\n")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            channel="chrome",
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        li_at = os.getenv("LINKEDIN_LI_AT", "").strip()
        if li_at:
            try:
                context.add_cookies([{
                    "name": "li_at",
                    "value": li_at,
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True
                }])
            except Exception:
                pass
        page = context.new_page()
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        start_time = time.time()
        timeout_seconds = 600  # 10 minutes
        logged_in = False

        while time.time() - start_time < timeout_seconds:
            time.sleep(3)
            if is_authenticated(page):
                logged_in = True
                print("\n[SUCCESS] LinkedIn Login Detected and Confirmed!")
                time.sleep(2)
                context.storage_state(path=str(SESSION_FILE))
                print(f"[SUCCESS] Saved session state to {SESSION_FILE}")
                break

        if not logged_in:
            print("\n[TIMEOUT] Session wait timed out after 5 minutes.")
            context.close()
            sys.exit(1)

        print("[INFO] Session is now active. Closing helper window...")
        time.sleep(1)
        context.close()
        print("[SUCCESS] LinkedIn profile ready for autonomous application sweeps!\n")


if __name__ == "__main__":
    main()
