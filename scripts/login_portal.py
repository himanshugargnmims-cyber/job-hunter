#!/usr/bin/env python3
"""
login_portal.py - Interactive session capture tool for multi-portal applications.

Supports:
- Naukri.com
- IIMjobs.com
- Instahyre.com
- Indeed India
- Wellfound (AngelList)
- Cutshort

Saves authenticated Playwright storage_state (cookies + localStorage) to
`job-hunter/sessions/<portal>_state.json` so background engines can run
parallel autonomous applications without re-authenticating.
"""

import sys
import time
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
LOGS_DIR = BASE_DIR / "logs"

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

PORTAL_CONFIGS = {
    "naukri": {
        "name": "Naukri.com",
        "login_url": "https://www.naukri.com/nlogin/login",
        "home_url": "https://www.naukri.com/mnjuser/homepage",
        "check_selector": "a[href*='mnjuser/profile'], .nI-gNb-drawer__bars, .view-profile-wrapper, a[title='Search Jobs']",
        "session_file": SESSIONS_DIR / "naukri_state.json"
    },
    "iimjobs": {
        "name": "IIMjobs.com",
        "login_url": "https://www.iimjobs.com/login",
        "home_url": "https://www.iimjobs.com/",
        "check_selector": "a[href*='/candidate/'], .logged-in, a[href*='logout'], .user_name, .profile_pic",
        "session_file": SESSIONS_DIR / "iimjobs_state.json"
    },
    "instahyre": {
        "name": "Instahyre.com",
        "login_url": "https://www.instahyre.com/login/",
        "home_url": "https://www.instahyre.com/candidate/opportunities/",
        "check_selector": "a[href*='/candidate/opportunities/'], a[href*='/candidate/profile/'], .user-avatar, #navbar-opportunities",
        "session_file": SESSIONS_DIR / "instahyre_state.json"
    },
    "indeed": {
        "name": "Indeed India",
        "login_url": "https://secure.indeed.com/auth",
        "home_url": "https://in.indeed.com/",
        "check_selector": "a[data-gnav-element-name='Profile'], [aria-label*='profile'], #gnav-account-filter",
        "session_file": SESSIONS_DIR / "indeed_state.json"
    },
    "wellfound": {
        "name": "Wellfound (AngelList)",
        "login_url": "https://wellfound.com/login",
        "home_url": "https://wellfound.com/jobs",
        "check_selector": "a[href*='/profile'], [data-test='user-menu'], button[aria-label='User navigation menu']",
        "session_file": SESSIONS_DIR / "wellfound_state.json"
    },
    "cutshort": {
        "name": "Cutshort.io",
        "login_url": "https://cutshort.io/login",
        "home_url": "https://cutshort.io/profile",
        "check_selector": "a[href*='/profile'], .user-profile-icon, button:has-text('Matches')",
        "session_file": SESSIONS_DIR / "cutshort_state.json"
    }
}


def capture_portal_session(portal_key: str, wait_timeout: int = 300) -> bool:
    """Opens a visible browser for user to log into the specified portal, then saves session state."""
    config = PORTAL_CONFIGS.get(portal_key.lower())
    if not config:
        print(f"[Error] Unknown portal '{portal_key}'. Available: {list(PORTAL_CONFIGS.keys())}")
        return False

    portal_name = config["name"]
    login_url = config["login_url"]
    session_file = config["session_file"]
    check_selector = config["check_selector"]

    print("\n" + "=" * 75)
    print(f"       PORTAL LOGIN ASSISTANT: {portal_name.upper()}")
    print("=" * 75)
    print(f"Target URL:    {login_url}")
    print(f"Session Destination: {session_file}")
    print("-" * 75)
    print("INSTRUCTIONS:")
    print(" 1. A browser window will open to the login page.")
    print(" 2. Enter your credentials, Google sign-in, or OTP.")
    print(" 3. When you reach your dashboard/home screen:")
    print("    -> Either the system will auto-detect your login, OR")
    print("    -> You can press ENTER right here in the terminal to save.")
    print("=" * 75 + "\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print(f"Navigating to {login_url}...")
        try:
            page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            print(f"[Warning] Initial navigation notice: {e}")

        # Check loop / manual prompt
        start_time = time.time()
        logged_in = False

        # Clean up any stale confirm signal file
        confirm_trigger = SESSIONS_DIR / "confirm_login"
        if confirm_trigger.exists():
            confirm_trigger.unlink()

        import select
        while time.time() - start_time < wait_timeout:
            time.sleep(1.0)

            # 1. Check for confirm trigger file
            if confirm_trigger.exists():
                print("   [Signal detected] Confirmation signal file detected!")
                logged_in = True
                confirm_trigger.unlink(missing_ok=True)
                break

            # 2. Check if user pressed ENTER in interactive terminal
            try:
                if sys.stdin and sys.stdin.isatty():
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.2)
                    if rlist:
                        line = sys.stdin.readline()
                        if line:
                            print("   [Enter detected] User confirmed login completed!")
                            logged_in = True
                            break
            except Exception:
                pass

            # 3. Try auto-detecting login via selector
            try:
                elem = page.locator(check_selector).first
                if elem.is_visible(timeout=500):
                    print(f"\n   [Auto-detected] Successful login identified via selector '{check_selector}'!")
                    logged_in = True
                    break
            except Exception:
                pass

            # 4. Check if current URL moved away from login
            current_url = page.url.lower()
            if "login" not in current_url and "auth" not in current_url and "signin" not in current_url and "oauth" not in current_url:
                if any(k in current_url for k in ["dashboard", "homepage", "home", "opportunities", "profile", "jobs", "candidate"]):
                    print(f"\n   [Auto-detected] Page redirected to authenticated destination: {page.url}")
                    logged_in = True
                    break

        if not logged_in:
            print("[Timeout] Login was not confirmed within the timeout period.")
            browser.close()
            return False

        # Save session
        time.sleep(2.0)
        context.storage_state(path=str(session_file))
        screenshot_path = LOGS_DIR / f"session_{portal_key}_logged_in.png"
        try:
            page.screenshot(path=str(screenshot_path))
        except Exception:
            pass

        print("\n" + "=" * 75)
        print(f"[SUCCESS] {portal_name} session saved successfully!")
        print(f"Storage state written to: {session_file}")
        print(f"Verification screenshot:  {screenshot_path}")
        print("=" * 75 + "\n")

        browser.close()
        return True


def list_portal_statuses():
    """Prints the authentication status of all supported portals."""
    print("\n" + "=" * 65)
    print("             PORTAL AUTHENTICATION STATUS")
    print("=" * 65)
    print(f"{'Portal':<20} | {'Status':<15} | {'Session File'}")
    print("-" * 65)

    for key, cfg in PORTAL_CONFIGS.items():
        sess_file = cfg["session_file"]
        if sess_file.exists() and sess_file.stat().st_size > 50:
            status = "AUTHENTICATED"
        else:
            status = "NOT LOGGED IN"
        print(f"{cfg['name']:<20} | {status:<15} | {sess_file.name}")
    print("=" * 65 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Portal Interactive Login Tool")
    parser.add_argument("--portal", choices=list(PORTAL_CONFIGS.keys()), help="Target portal to log into")
    parser.add_argument("--status", action="store_true", help="Show authentication status of all portals")
    args = parser.parse_args()

    if args.status or not args.portal:
        list_portal_statuses()
        if not args.portal:
            print("To log into a portal, run:")
            print("  ./.venv/bin/python job-hunter/scripts/login_portal.py --portal <naukri|iimjobs|instahyre|indeed|wellfound>\n")
            return

    capture_portal_session(args.portal)


if __name__ == "__main__":
    main()
