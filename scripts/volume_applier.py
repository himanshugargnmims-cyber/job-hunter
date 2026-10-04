"""
High-Volume Autonomous LinkedIn Easy Apply Application Engine.

Designed for sustained, hands-free volume execution:
- Target: At least 100 job applications submitted autonomously.
- Cycles through multi-keyword, multi-city search matrix across target charters:
  - Program Management / TPM
  - Strategy & Operations / Chief of Staff
  - Revenue Operations / RevOps / GTM Operations
- Automatic pagination across LinkedIn results (start=0, 25, 50, 75...).
- Multi-variant resume routing (evaluates against 3 pre-made PDF variants).
- Complete form auto-filling (candidate details, notice period, 9 yrs exp, compensation, AI screening QA).
- Executes submission button and captures verification screenshots in logs/.
- Resilient error recovery: auto-discards stuck drafts and proceeds to the next job.
- Live progress persistence in data/tracker.csv and SQLite data/jobs.db.
"""

import os
import sys
import re
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from dotenv import load_dotenv

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# Path resolution
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

load_dotenv(BASE_DIR / ".env")
load_dotenv()

from resume_selector import ResumeSelector
from sheet_updater import SheetUpdater
from linkedin_applier import LinkedInApplier

# Prioritized search matrix: Remote (Global/India), Hyderabad, Bengaluru, Gurugram
SEARCH_MATRIX: List[Tuple[str, str]] = [
    # Tier 1: Completely Remote (Top Priority)
    ("Chief of Staff", "Remote"),
    ("Strategy and Operations", "Remote"),
    ("Revenue Operations", "Remote"),
    ("GTM Strategy", "Remote"),
    ("Technical Program Manager", "Remote"),
    ("Business Operations", "Remote"),
    ("Director of Operations", "Remote"),

    # Tier 2: Hyderabad (GCCs & Enterprise Hub)
    ("Program Manager", "Hyderabad"),
    ("Technical Program Manager", "Hyderabad"),
    ("Strategy and Operations", "Hyderabad"),
    ("Director of Operations", "Hyderabad"),
    ("Chief of Staff", "Hyderabad"),
    ("Business Operations", "Hyderabad"),

    # Tier 3: Bengaluru (HQ Tech & Unicorn Hub)
    ("Chief of Staff", "Bengaluru"),
    ("Strategy and Operations", "Bengaluru"),
    ("Revenue Operations", "Bengaluru"),
    ("GTM Strategy", "Bengaluru"),
    ("Technical Program Manager", "Bengaluru"),
    ("Head of Operations", "Bengaluru"),
    ("Business Operations", "Bengaluru"),

    # Tier 4: Gurugram / Delhi NCR (Corporate HQs & Consumer Tech)
    ("Chief of Staff", "Gurgaon"),
    ("Strategy and Operations", "Gurgaon"),
    ("Revenue Operations", "Gurgaon"),
    ("Director Program Management", "Gurgaon"),
    ("Business Operations", "Gurgaon"),
]


class VolumeApplier:
    def __init__(
        self,
        target_submissions: int = 100,
        min_score: float = 70.0,
        headless: bool = True,
        user_data_dir: Optional[str] = None
    ):
        self.target_submissions = target_submissions
        self.min_score = min_score
        self.headless = headless
        self.cookie_val = os.getenv("LINKEDIN_LI_AT")

        self.updater = SheetUpdater(
            csv_path=str(BASE_DIR / "data" / "tracker.csv"),
            db_path=str(BASE_DIR / "data" / "jobs.db")
        )
        self.applier = LinkedInApplier(
            user_data_dir=user_data_dir,
            headless=self.headless,
            min_score=self.min_score,
            auto_submit=True
        )

        # Count already submitted applications
        self.existing_urls = self.updater.get_existing_urls()
        self.submitted_count = self._count_submitted_in_db()

    def _count_submitted_in_db(self) -> int:
        """Counts how many applications have already been submitted."""
        try:
            import sqlite3
            db_file = BASE_DIR / "data" / "jobs.db"
            if db_file.exists():
                conn = sqlite3.connect(db_file)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM applications WHERE status = 'Submitted'")
                count = c.fetchone()[0]
                conn.close()
                return count
        except Exception:
            pass
        return 0

    def run_volume_pipeline(self):
        print("=" * 70)
        print("     HIGH-VOLUME AUTONOMOUS APPLICATION ENGINE (TARGET: 100)")
        print("=" * 70)
        print(f"Target Submissions:  {self.target_submissions}")
        print(f"Currently Submitted: {self.submitted_count}")
        print(f"Remaining To Goal:   {max(0, self.target_submissions - self.submitted_count)}")
        print(f"Min Fit Score:       {self.min_score}%")
        print(f"Headless Mode:       {self.headless}")
        print(f"Search Matrix Size:  {len(SEARCH_MATRIX)} query/city combinations")
        print("=" * 70)

        if not self.cookie_val:
            print("[Error] No LINKEDIN_LI_AT cookie found in job-hunter/.env!")
            return

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()

            # Inject session authentication cookies
            context.add_cookies([
                {
                    "name": "li_at",
                    "value": self.cookie_val.strip(),
                    "domain": ".linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                },
                {
                    "name": "li_at",
                    "value": self.cookie_val.strip(),
                    "domain": ".www.linkedin.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                    "sameSite": "None"
                }
            ])

            page = context.new_page()

            try:
                for q_idx, (keywords, location) in enumerate(SEARCH_MATRIX, 1):
                    if self.submitted_count >= self.target_submissions:
                        print(f"\n[GOAL ACHIEVED] Reached target of {self.target_submissions} submissions!")
                        break

                    print(f"\n" + "-" * 60)
                    print(f"[{q_idx}/{len(SEARCH_MATRIX)}] Query: '{keywords}' in '{location}'")
                    print(f"Progress: {self.submitted_count}/{self.target_submissions} submitted")
                    print("-" * 60)

                    # Paginate across search offsets
                    for page_num in range(4):  # 4 pages = 100 listings per query
                        if self.submitted_count >= self.target_submissions:
                            break

                        start_offset = page_num * 25
                        encoded_kw = quote_plus(keywords)
                        encoded_loc = quote_plus(location)
                        search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_kw}&location={encoded_loc}&f_AL=true&start={start_offset}"

                        print(f"\n  Loading page {page_num + 1} (offset {start_offset}): {search_url}")
                        try:
                            page.goto(search_url, wait_until="domcontentloaded")
                            time.sleep(3.5)
                        except Exception as e:
                            print(f"  Navigation error: {e}")
                            continue

                        # Check if authenticated or redirected
                        if "login" in page.url or "checkpoint" in page.url:
                            print("  [Warning] Session expired or checkpoint encountered.")
                            break

                        # Scroll down slightly to trigger loading of cards
                        try:
                            page.evaluate("window.scrollTo(0, 500)")
                            time.sleep(1.0)
                        except Exception:
                            pass

                        # Locate job cards prioritizing Easy Apply badges
                        ea_cards = page.locator('.job-card-container:has-text("Easy Apply"), li[data-occludable-job-id]:has-text("Easy Apply")')
                        if ea_cards.count() > 0:
                            job_cards = ea_cards
                        else:
                            job_cards = page.locator('div.job-card-container, li[data-occludable-job-id]')

                        card_count = job_cards.count()
                        print(f"  Found {card_count} candidate cards on page {page_num + 1}.")
                        if card_count == 0:
                            break

                        for c_i in range(card_count):
                            if self.submitted_count >= self.target_submissions:
                                break

                            try:
                                card = job_cards.nth(c_i)
                                if not card.is_visible():
                                    continue

                                res = self.applier.apply_to_job_listing(page, card)
                                if res and res.get("status") == "Submitted":
                                    self.submitted_count += 1
                                    self.existing_urls.add(res["url"])
                                    print(f"\n  >>> [SUBMITTED #{self.submitted_count}/{self.target_submissions}] {res['title']} @ {res['company']} (Fit: {res['score']}%) <<<")
                                    print(f"      Screenshot: {res.get('screenshot')}")

                                    # Pace submissions naturally
                                    time.sleep(2.5)

                            except Exception as card_err:
                                print(f"  Error on card {c_i}: {card_err}")
                                # Clean up any open dialog
                                try:
                                    close_btn = page.locator('button[aria-label="Dismiss"], button.artdeco-modal__dismiss').first
                                    if close_btn.is_visible():
                                        close_btn.click()
                                        time.sleep(0.5)
                                        discard = page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")').first
                                        if discard.is_visible():
                                            discard.click()
                                except Exception:
                                    pass

            finally:
                browser.close()

        print("\n" + "=" * 70)
        print("                 VOLUME EXECUTION COMPLETE")
        print("=" * 70)
        print(f"Total Applications Submitted: {self.submitted_count}")
        print(f"Tracker updated at:           {BASE_DIR / 'data' / 'tracker.csv'}")
        print(f"Database updated at:          {BASE_DIR / 'data' / 'jobs.db'}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="High-Volume Autonomous LinkedIn Application Engine")
    parser.add_argument("--target", type=int, default=100, help="Target total submitted applications (default: 100)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Minimum fit score threshold (default: 70.0)")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode instead of headless")

    args = parser.parse_args()

    engine = VolumeApplier(
        target_submissions=args.target,
        min_score=args.min_score,
        headless=not args.visible
    )
    engine.run_volume_pipeline()


if __name__ == "__main__":
    main()
