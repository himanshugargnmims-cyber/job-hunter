#!/usr/bin/env python3
"""
instahyre_applier.py - Autonomous Application Engine for Instahyre.com

Features:
- Authenticates using stored Playwright session (`job-hunter/sessions/instahyre_state.json`).
- Directly scans curated high-growth tech & startup opportunities feed.
- Evaluates fit scores using candidate resume variants.
- Executes 1-click apply on matching leadership, strategy, and ops opportunities.
- Captures submission screenshot proofs and writes to `tracker.csv` & `jobs.db`.
"""

import sys
import time
import re
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from scripts.resume_selector import ResumeSelector
from scripts.sheet_updater import SheetUpdater

SESSION_FILE = BASE_DIR / "sessions" / "instahyre_state.json"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class InstahyreApplier:
    def __init__(self, headless: bool = True, min_score: float = 70.0):
        self.headless = headless
        self.min_score = min_score
        self.selector = ResumeSelector()
        self.updater = SheetUpdater()
        self.existing_urls = self.updater.get_existing_urls()

    def run(self, target_applications: int = 50):
        if not SESSION_FILE.exists():
            print(f"[Error] No active Instahyre session found at {SESSION_FILE}!")
            print("Please run: ./.venv/bin/python job-hunter/scripts/login_portal.py --portal instahyre")
            return

        print("=" * 70)
        print("          INSTAHYRE.COM AUTONOMOUS APPLICATION ENGINE")
        print("=" * 70)
        print(f"Target Submissions:  {target_applications}")
        print(f"Min Fit Score:       {self.min_score}%")
        print(f"Session File:        {SESSION_FILE}")
        print("=" * 70)

        submitted_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Verify session is valid
            print("Verifying Instahyre session validity...")
            page.goto("https://www.instahyre.com/candidate/opportunities/", wait_until="domcontentloaded", timeout=45000)
            time.sleep(3.0)

            if "login" in page.url.lower():
                print("[Error] Instahyre session expired or invalid. Please re-run login_portal.py --portal instahyre")
                browser.close()
                return

            print("[Success] Authenticated to Instahyre successfully!\n")

            # Scan opportunities list
            opp_cards = page.locator('.opportunity-card, .job-item, div[ng-repeat*="opportunity"], .employer-details')
            count = opp_cards.count()
            print(f"Found {count} candidate opportunities on Instahyre.")

            for idx in range(count):
                if submitted_count >= target_applications:
                    break

                try:
                    card = opp_cards.nth(idx)
                    if not card.is_visible():
                        continue

                    card_text = card.inner_text()
                    lines = [l.strip() for l in card_text.split("\n") if l.strip()]
                    title = lines[0] if lines else "Role"
                    company = lines[1] if len(lines) > 1 else "Tech Startup"

                    job_url = page.url + f"#opp-{idx}"

                    # Evaluate score
                    selected_resume, fit_score, rationale = self.selector.select_best_resume(
                        title=title,
                        description=card_text,
                        location="India"
                    )

                    print(f" [{idx+1}/{count}] {title} @ {company} (Score: {fit_score}%)")
                    if fit_score < self.min_score:
                        print(f"     -> Skipped (below {self.min_score}%)")
                        continue

                    # Look for Apply button
                    apply_btn = card.locator('button:has-text("Apply"), a:has-text("Apply"), .btn-apply')
                    if apply_btn.count() > 0 and apply_btn.first.is_visible():
                        apply_btn.first.click(force=True)
                        time.sleep(2.0)

                        # Handle possible confirmation modal
                        confirm_btn = page.locator('button:has-text("Confirm"), button:has-text("Submit"), button.modal-apply')
                        if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                            confirm_btn.first.click(force=True)
                            time.sleep(2.0)

                        # Screenshot proof
                        clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())[:20]
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        screen_path = LOGS_DIR / f"submitted_instahyre_{clean_comp}_{ts}.png"
                        try:
                            page.screenshot(path=str(screen_path))
                        except Exception:
                            pass

                        submitted_count += 1
                        self.updater.log_application(
                            company=company,
                            job_title=title,
                            location="India",
                            url=job_url,
                            selected_resume=selected_resume,
                            fit_score=fit_score,
                            rationale=rationale,
                            board_type="Instahyre 1-Click",
                            description=card_text[:1000],
                            status="Submitted",
                            notes=f"Auto-applied via Instahyre. Resume: {selected_resume}",
                            screenshot_path=str(screen_path)
                        )
                        print(f"     >>> [SUBMITTED #{submitted_count}] Recorded with proof: {screen_path.name} <<<\n")
                        time.sleep(1.5)

                except Exception as e:
                    print(f"     -> Card error: {e}")
                    continue

            browser.close()

        print("\n" + "=" * 70)
        print(f"INSTAHYRE APPLICATION RUN COMPLETE: {submitted_count} applications submitted.")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Instahyre Autonomous Applier")
    parser.add_argument("--target", type=int, default=30, help="Target applications (default: 30)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Min score (default: 70)")
    parser.add_argument("--visible", action="store_true", help="Run visible browser")
    args = parser.parse_args()

    applier = InstahyreApplier(headless=not args.visible, min_score=args.min_score)
    applier.run(target_applications=args.target)


if __name__ == "__main__":
    main()
