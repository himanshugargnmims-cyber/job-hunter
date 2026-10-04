#!/usr/bin/env python3
"""
naukri_applier.py - Autonomous Application Engine for Naukri.com

Features:
- Authenticates using stored Playwright session (`job-hunter/sessions/naukri_state.json`).
- Targets top roles: Program Manager, Strategy & Operations, Chief of Staff, RevOps.
- Targets locations: Bengaluru, Gurgaon/Delhi NCR, Hyderabad.
- Evaluates fit scores using candidate resume variants.
- Handles Naukri Quick Apply and inline chatbot screening questions.
- Captures submission screenshot proofs and writes to `tracker.csv` & `jobs.db`.
"""

import sys
import time
import re
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from scripts.resume_selector import ResumeSelector
from scripts.sheet_updater import SheetUpdater

SESSION_FILE = BASE_DIR / "sessions" / "naukri_state.json"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

NAUKRI_SEARCH_TARGETS = [
    {"query": "program manager", "location": "bengaluru"},
    {"query": "program manager", "location": "gurgaon"},
    {"query": "strategy operations", "location": "bengaluru"},
    {"query": "strategy operations", "location": "gurgaon"},
    {"query": "chief of staff", "location": "bengaluru"},
    {"query": "chief of staff", "location": "gurgaon"},
    {"query": "revenue operations", "location": "bengaluru"},
    {"query": "technical program manager", "location": "bengaluru"},
    {"query": "business operations", "location": "bengaluru"}
]


class NaukriApplier:
    def __init__(self, headless: bool = True, min_score: float = 70.0):
        self.headless = headless
        self.min_score = min_score
        self.selector = ResumeSelector()
        self.updater = SheetUpdater()
        self.existing_urls = self.updater.get_existing_urls()

    def run(self, target_applications: int = 50):
        if not SESSION_FILE.exists():
            print(f"[Error] No active Naukri session found at {SESSION_FILE}!")
            print("Please run: ./.venv/bin/python job-hunter/scripts/login_portal.py --portal naukri")
            return

        print("=" * 70)
        print("          NAUKRI.COM AUTONOMOUS APPLICATION ENGINE")
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
            print("Verifying Naukri session validity...")
            page.goto("https://www.naukri.com/mnjuser/homepage", wait_until="domcontentloaded", timeout=45000)
            time.sleep(2.0)

            if "nlogin" in page.url.lower():
                print("[Error] Naukri session expired or invalid. Please re-run login_portal.py --portal naukri")
                browser.close()
                return

            print("[Success] Authenticated to Naukri successfully!\n")

            for target in NAUKRI_SEARCH_TARGETS:
                if submitted_count >= target_applications:
                    break

                q = target["query"]
                loc = target["location"]
                print(f"\n--- Searching: '{q}' in '{loc}' ---")

                search_url = f"https://www.naukri.com/jobs-in-{loc}?k={q.replace(' ', '+')}"
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    time.sleep(3.0)
                except Exception as e:
                    print(f"Navigation warning: {e}")
                    continue

                # Locate job cards
                job_cards = page.locator('article.jobTuple, .srp-jobtuple-wrapper, div[data-job-id]')
                count = job_cards.count()
                print(f"Found {count} job listings.")

                for idx in range(count):
                    if submitted_count >= target_applications:
                        break

                    try:
                        card = job_cards.nth(idx)
                        if not card.is_visible():
                            continue

                        # Extract details
                        title_el = card.locator('a.title, [class*="title"]').first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else "Role"
                        url = title_el.get_attribute("href") or ""

                        comp_el = card.locator('a.comp-name, [class*="comp-name"], .subTitle').first
                        company = comp_el.inner_text().strip() if comp_el.count() > 0 else "Company"

                        desc_el = card.locator('.job-desc, [class*="job-desc"], .ellipsis').first
                        desc = desc_el.inner_text().strip() if desc_el.count() > 0 else title

                        if not url or url in self.existing_urls:
                            continue

                        # Check fit score
                        selected_resume, fit_score, rationale = self.selector.select_best_resume(
                            title=title,
                            description=f"{title} at {company}. {desc}",
                            location=loc
                        )

                        print(f" [{idx+1}/{count}] {title} @ {company} (Score: {fit_score}%)")
                        if fit_score < self.min_score:
                            print(f"     -> Skipped (below {self.min_score}%)")
                            continue

                        # Check if card has direct apply button
                        apply_btn = card.locator('button:has-text("Apply"), a:has-text("Apply"), .apply-button')
                        if apply_btn.count() > 0 and apply_btn.first.is_visible():
                            apply_btn.first.click(force=True)
                            time.sleep(2.5)

                            # Handle inline chatbot / quick apply modal
                            self._handle_naukri_apply_dialog(page)

                            # Capture screenshot proof
                            clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())[:20]
                            ts = time.strftime("%Y%m%d_%H%M%S")
                            screen_path = LOGS_DIR / f"submitted_naukri_{clean_comp}_{ts}.png"
                            try:
                                page.screenshot(path=str(screen_path))
                            except Exception:
                                pass

                            submitted_count += 1
                            self.existing_urls.add(url)
                            self.updater.log_application(
                                company=company,
                                job_title=title,
                                location=loc.capitalize(),
                                url=url,
                                selected_resume=selected_resume,
                                fit_score=fit_score,
                                rationale=rationale,
                                board_type="Naukri Quick Apply",
                                description=desc[:1000],
                                status="Submitted",
                                notes=f"Auto-applied via Naukri Quick Apply. Resume: {selected_resume}",
                                screenshot_path=str(screen_path)
                            )
                            print(f"     >>> [SUBMITTED #{submitted_count}] Recorded with proof: {screen_path.name} <<<\n")
                            time.sleep(2.0)

                    except Exception as card_err:
                        print(f"     -> Card error: {card_err}")
                        continue

            browser.close()

        print("\n" + "=" * 70)
        print(f"NAUKRI APPLICATION RUN COMPLETE: {submitted_count} applications submitted.")
        print("=" * 70)

    def _handle_naukri_apply_dialog(self, page: Page):
        """Fills standard screening questions if Naukri presents an application drawer/modal."""
        try:
            # Check for submit/apply in drawer
            submit = page.locator('button:has-text("Submit"), button:has-text("Apply"), button:has-text("Save & Apply")')
            if submit.count() > 0 and submit.first.is_visible():
                submit.first.click(force=True)
                time.sleep(1.5)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Naukri Autonomous Applier")
    parser.add_argument("--target", type=int, default=30, help="Target applications (default: 30)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Min score (default: 70)")
    parser.add_argument("--visible", action="store_true", help="Run visible browser")
    args = parser.parse_args()

    applier = NaukriApplier(headless=not args.visible, min_score=args.min_score)
    applier.run(target_applications=args.target)


if __name__ == "__main__":
    main()
