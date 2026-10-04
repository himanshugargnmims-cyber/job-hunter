#!/usr/bin/env python3
"""
ats_applier.py - Autonomous Direct ATS Board Application Engine (Greenhouse, Lever, Ashby)

Zero User Intervention Required:
1. Scrapes target company career boards via API / web endpoints.
2. Evaluates fit scores using candidate resume variants.
3. Automatically maps all standard candidate inputs.
4. Resolves location autocomplete dropdowns.
5. Solves Cloudflare Turnstile / verification challenges automatically.
6. Drafts grounded 2-sentence answers for custom screening textareas.
7. Automatically clicks the Submit Application button (auto_submit=True, safe_mode=False).
8. Captures post-submit confirmation screenshots and logs directly to tracker.csv & jobs.db.
"""

import sys
import time
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from scripts.scraper import JobScraper, JobListing
from scripts.resume_selector import ResumeSelector
from scripts.sheet_updater import SheetUpdater
from scripts.applier import apply_to_job

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


class DirectATSApplier:
    def __init__(self, headless: bool = True, min_score: float = 70.0):
        self.headless = headless
        self.min_score = min_score
        self.scraper = JobScraper()
        self.selector = ResumeSelector()
        self.updater = SheetUpdater()
        self.existing_urls = self.updater.get_existing_urls()

    def run(self, max_submissions: int = 25):
        print("=" * 70)
        print("     AUTONOMOUS DIRECT ATS APPLICATION ENGINE (GREENHOUSE/LEVER/ASHBY)")
        print("=" * 70)
        print(f"Target Submissions:  {max_submissions}")
        print(f"Min Fit Score:       {self.min_score}%")
        print(f"Headless Mode:       {self.headless}")
        print("=" * 70)

        # 1. Scrape matching jobs from direct ATS boards
        print("\nScanning direct company ATS boards...")
        listings = self.scraper.scrape_all()
        print(f"Found {len(listings)} total candidate postings from direct ATS career boards.")

        submitted_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )

            for idx, job in enumerate(listings):
                if submitted_count >= max_submissions:
                    break

                if job.url in self.existing_urls:
                    continue

                # 2. Evaluate fit score
                selected_resume, fit_score, rationale = self.selector.select_best_resume(
                    title=job.title,
                    description=job.description,
                    location=job.location
                )

                if fit_score < self.min_score:
                    continue

                print(f"\n[{submitted_count + 1}/{max_submissions}] {job.title} @ {job.company} ({job.location})")
                print(f"      Fit Score: {fit_score}% -> Variant: {selected_resume}")
                print(f"      URL: {job.url}")

                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
                page = context.new_page()

                try:
                    resume_path = BASE_DIR / "resumes" / selected_resume

                    # Resolve Greenhouse embed, Lever apply, and Ashby URLs for maximum submission reliability
                    target_url = job.url
                    gh_token = None
                    m = re.search(r'(?:gh_jid=|/jobs/)(\d+)', job.url)
                    if m:
                        gh_token = m.group(1)
                    m_board = re.search(r'greenhouse\.io/(?:embed/job_app\?for=)?([^/?#]+)', job.url)
                    if m_board and m_board.group(1) not in ("jobs", "embed"):
                        comp_slug = m_board.group(1)
                    else:
                        comp_slug = job.company.lower().replace(" ", "").replace("-", "")
                    if gh_token and (job.board_type.lower() == "greenhouse" or "gh_jid=" in job.url or "greenhouse.io" in job.url):
                        target_url = f"https://job-boards.greenhouse.io/embed/job_app?for={comp_slug}&token={gh_token}"
                    elif "jobs.lever.co" in job.url and not job.url.endswith("/apply"):
                        target_url = job.url.rstrip("/") + "/apply"
                    elif "jobs.ashbyhq.com" in job.url and not job.url.endswith("/application"):
                        target_url = job.url.rstrip("/") + "/application"

                    result = apply_to_job(
                        page=page,
                        job_url=target_url,
                        resume_path=str(resume_path),
                        auto_submit=True,
                        safe_mode=False,
                        company_name=job.company
                    )

                    status = result.get("status", "Submitted")
                    screenshot_path = result.get("screenshot_path", "")

                    # 3. Log to tracker & database
                    self.updater.log_application(
                        company=job.company,
                        job_title=job.title,
                        location=job.location,
                        url=job.url,
                        selected_resume=selected_resume,
                        fit_score=fit_score,
                        rationale=rationale,
                        board_type=f"Direct Company Website ({job.company})",
                        description=job.description[:1000],
                        status=status,
                        notes=f"Direct company website application. Resume: {selected_resume}",
                        screenshot_path=screenshot_path
                    )
                    self.existing_urls.add(job.url)
                    submitted_count += 1
                    print(f"   >>> [{status.upper()} #{submitted_count}] Recorded with proof: {Path(screenshot_path).name} <<<\n")
                    time.sleep(2.5)

                except Exception as e:
                    print(f"   [Error] Failed to process application for {job.company}: {e}")
                finally:
                    context.close()

            browser.close()

        print("\n" + "=" * 70)
        print(f"DIRECT ATS APPLICATION RUN COMPLETE: {submitted_count} jobs submitted.")
        print(f"Tracker: {BASE_DIR / 'data' / 'tracker.csv'}")
        print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Direct ATS Board Applier")
    parser.add_argument("--target", type=int, default=25, help="Target application count (default: 25)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Minimum fit score (default: 70)")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    args = parser.parse_args()

    applier = DirectATSApplier(headless=not args.visible, min_score=args.min_score)
    applier.run(max_submissions=args.target)


if __name__ == "__main__":
    main()
