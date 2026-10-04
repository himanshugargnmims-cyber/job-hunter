"""
Main Pipeline Orchestrator for Job Hunter.

Executes the automated pipeline:
1. Scrapes target ATS boards (Greenhouse, Lever, Ashby)
2. Filters by target location hubs (Remote, BLR, HYD, GGN) and role profiles
3. Evaluates and selects the best pre-made resume variant
4. Persists results to SQLite DB (jobs.db), CSV tracker (tracker.csv), and Google Sheets
5. Writes timestamped execution logs to job-hunter/logs/
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure scripts directory is on sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from scraper import JobScraper, JobListing
from resume_selector import ResumeSelector
from sheet_updater import SheetUpdater


def setup_logger(log_dir: Path) -> logging.Logger:
    """Configures console and file logging."""
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"run_{timestamp}.log"

    logger = logging.getLogger("JobHunter")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    # File handler
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    fh.setFormatter(fh_formatter)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch_formatter = logging.Formatter("%(message)s")
    ch.setFormatter(ch_formatter)
    logger.addHandler(ch)

    logger.info(f"Session started. Logging to {log_file}")
    return logger


def run_pipeline(
    batch_size: Optional[int] = None,
    company: Optional[str] = None,
    max_per_company: int = 5,
    min_score: Optional[float] = None,
    dry_run: bool = False,
    prefill: bool = False,
    auto_submit: bool = False,
    status: str = "Pending Approval"
):
    log_dir = BASE_DIR / "logs"
    logger = setup_logger(log_dir)

    # Initialize scraper to read preferences
    scraper = JobScraper(
        preferences_path=str(BASE_DIR / "context" / "preferences.json"),
        company_list_path=str(BASE_DIR / "context" / "company_list.txt")
    )

    if min_score is None:
        min_score = float(scraper.preferences.get("minimum_match_score", 75.0))

    logger.info("=" * 60)
    logger.info("           JOB HUNTER PIPELINE EXECUTION")
    logger.info("=" * 60)
    logger.info(f"Target Base Directory: {BASE_DIR}")
    logger.info(f"Min Fit Score Threshold: {min_score}%")
    if company:
        logger.info(f"Target Company Filter: {company}")
    if dry_run:
        logger.info("[MODE: DRY RUN - No updates will be saved to tracker/DB]")

    # 1. Initialize components
    selector = ResumeSelector(resumes_dir=str(BASE_DIR / "resumes"))
    updater = SheetUpdater(
        csv_path=str(BASE_DIR / "data" / "tracker.csv"),
        db_path=str(BASE_DIR / "data" / "jobs.db")
    )

    existing_urls = updater.get_existing_urls()
    logger.info(f"Currently tracked jobs in database: {len(existing_urls)}")

    # 2. Scrape jobs
    logger.info("\n>>> Starting Multi-ATS Scraper...")
    scraped_jobs = scraper.scrape_all(target_company=company, max_per_company=max_per_company)
    logger.info(f"Scraped {len(scraped_jobs)} raw candidate jobs matching location & role filters.")

    # 3. Process and match
    matched_and_logged = 0
    skipped_existing = 0
    below_threshold = 0

    logger.info("\n>>> Evaluating Resume Matches...")
    for job in scraped_jobs:
        if batch_size and matched_and_logged >= batch_size:
            logger.info(f"\nReached target batch size limit of {batch_size}. Stopping ingestion.")
            break

        if job.url in existing_urls:
            skipped_existing += 1
            continue

        # Evaluate fit against pre-made resume variants
        eval_result = selector.evaluate_fit(job.title, job.description)
        fit_score = eval_result["fit_score"]
        selected_resume = eval_result["selected_resume"]
        rationale = eval_result["rationale"]

        if fit_score < min_score:
            below_threshold += 1
            logger.info(f"[-] Below threshold ({fit_score}% < {min_score}%): [{job.company}] {job.title}")
            continue

        matched_and_logged += 1
        logger.info(f"\n[+] MATCH #{matched_and_logged} ({fit_score}%): {job.title} @ {job.company}")
        logger.info(f"    Location: {job.location} [{job.location_tag}]")
        logger.info(f"    Selected Resume: {selected_resume}")
        logger.info(f"    URL: {job.url}")
        logger.info(f"    Rationale: {rationale}")

        initial_status = status
        if not dry_run and (prefill or auto_submit):
            try:
                from applier import run_apply
                logger.info(f"    [Playwright] Launching application automation (auto_submit={auto_submit})...")
                resume_file = BASE_DIR / "resumes" / selected_resume
                app_status = run_apply(job.url, str(resume_file), auto_submit=auto_submit, headless=True)
                initial_status = app_status
                logger.info(f"    [Playwright] Form automation complete: Status set to '{initial_status}'")
            except Exception as e:
                logger.error(f"    [Playwright] Automation failed for {job.url}: {e}")

        if not dry_run:
            updater.log_application(
                company=job.company,
                job_title=job.title,
                location=f"{job.location} ({job.location_tag})",
                url=job.url,
                selected_resume=selected_resume,
                fit_score=fit_score,
                rationale=rationale,
                board_type=job.board_type,
                description=job.description[:1000],
                status=initial_status
            )
            existing_urls.add(job.url)

    # 4. Summary
    logger.info("\n" + "=" * 60)
    logger.info("                  EXECUTION SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total Scraped:        {len(scraped_jobs)}")
    logger.info(f"Already Tracked:      {skipped_existing}")
    logger.info(f"Below Min Score:      {below_threshold}")
    logger.info(f"New Applications:     {matched_and_logged}")
    if dry_run:
        logger.info("[Dry Run complete - 0 records persisted]")
    else:
        logger.info(f"Data saved to: {BASE_DIR / 'data' / 'tracker.csv'} and {BASE_DIR / 'data' / 'jobs.db'}")

    return matched_and_logged


def print_stats():
    updater = SheetUpdater(
        csv_path=str(BASE_DIR / "data" / "tracker.csv"),
        db_path=str(BASE_DIR / "data" / "jobs.db")
    )
    stats = updater.get_summary_stats()
    print("\n" + "=" * 50)
    print("           JOB TRACKER SUMMARY STATS")
    print("=" * 50)
    print(f"Total Tracked Applications: {stats['total_jobs']}")
    print(f"Average Match Fit Score:    {stats['avg_fit_score']}%")
    print("\nApplications by Status:")
    for status, count in stats["by_status"].items():
        print(f"  - {status:15}: {count}")
    print("\nApplications by Company:")
    for comp, count in stats["by_company"].items():
        print(f"  - {comp:15}: {count}")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Job Hunter Automated Pipeline")
    parser.add_argument("--batch-size", type=int, default=None, help="Maximum number of new applications to log")
    parser.add_argument("--company", type=str, default=None, help="Filter search to a specific company")
    parser.add_argument("--max-per-company", type=int, default=5, help="Maximum jobs to scrape per company board")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum fit score (defaults to preferences.json setting)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate run without writing to tracker or DB")
    parser.add_argument("--prefill", action="store_true", help="Automatically pre-fill application form using Playwright")
    parser.add_argument("--auto-submit", action="store_true", help="Automatically pre-fill and submit application using Playwright")
    parser.add_argument("--status", default="Pending Approval", help="Initial status for newly tracked applications (default: 'Pending Approval')")
    parser.add_argument("--stats", action="store_true", help="Display summary stats from database")
    parser.add_argument("--update-status", nargs=2, metavar=("URL", "STATUS"), help="Update status for a specific job URL")

    args = parser.parse_args()

    if args.stats:
        print_stats()
        return

    if args.update_status:
        url, status = args.update_status
        updater = SheetUpdater()
        try:
            ok = updater.update_status(url, status)
            if ok:
                print(f"[OK] Successfully updated {url} to status '{status}'")
            else:
                print(f"[ERROR] URL not found: {url}")
        except Exception as e:
            print(f"[ERROR] Failed to update status: {e}")
        return

    run_pipeline(
        batch_size=args.batch_size,
        company=args.company,
        max_per_company=args.max_per_company,
        min_score=args.min_score,
        dry_run=args.dry_run,
        prefill=args.prefill,
        auto_submit=args.auto_submit,
        status=args.status
    )


if __name__ == "__main__":
    main()
