#!/usr/bin/env python3
"""
Job Hunter — Master Application Entrypoint & CLI Orchestrator

Commands:
  python run.py --setup      Run interactive terminal onboarding wizard
  python run.py --ui         Launch local Web UI dashboard (http://localhost:8080)
  python run.py --scrape     Ingest matching jobs from target ATS boards
  python run.py --match      Score candidate resume(s) against scraped jobs
  python run.py --apply      Automate ATS form submissions via Playwright
  python run.py --all        Execute end-to-end pipeline (Scrape -> Match -> Apply)
  python run.py --stats      View application statistics and pipeline metrics
  python run.py --export     Generate formatted Excel application tracker
"""

import sys
import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


def main():
    parser = argparse.ArgumentParser(
        description="Job Hunter — Automated Job Search & Application Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py --setup             Configure your candidate profile & resume
  python run.py --ui                Start browser web interface
  python run.py --all               Run end-to-end job discovery and application
  python run.py --scrape --company gitlab   Scrape jobs specifically from GitLab
  python run.py --apply --dry-run   Simulate applications without final submit
  python run.py --stats             View application pipeline statistics
        """
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--setup", action="store_true", help="Run interactive profile onboarding wizard")
    mode_group.add_argument("--ui", action="store_true", help="Start local Web UI dashboard at http://localhost:8080")
    mode_group.add_argument("--scrape", action="store_true", help="Scrape live job listings from ATS platforms")
    mode_group.add_argument("--match", action="store_true", help="Evaluate resume fit against discovered jobs")
    mode_group.add_argument("--apply", action="store_true", help="Submit applications for high-matching jobs")
    mode_group.add_argument("--all", action="store_true", help="Run complete pipeline: Scrape -> Match -> Apply")
    mode_group.add_argument("--stats", action="store_true", help="Display application tracker metrics")
    mode_group.add_argument("--export", action="store_true", help="Export tracker to styled Excel workbook")

    # Pipeline parameter options
    parser.add_argument("--company", type=str, default=None, help="Filter search to a specific company slug")
    parser.add_argument("--batch-size", type=int, default=10, help="Maximum number of jobs to process per run")
    parser.add_argument("--min-score", type=float, default=None, help="Override minimum fit score (0-100)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate execution without submitting or persisting")
    parser.add_argument("--auto", action="store_true", help="Fully automated submission mode (skips manual review)")
    parser.add_argument("--port", type=int, default=8080, help="Port for the Web UI server (default: 8080)")

    args = parser.parse_args()

    # 1. SETUP WIZARD
    if args.setup:
        from setup_profile import main as setup_main
        setup_main()
        return

    # 2. WEB UI
    if args.ui:
        from web_ui import start_server
        start_server(port=args.port)
        return

    # 3. STATS
    if args.stats:
        from sheet_updater import SheetUpdater
        updater = SheetUpdater(
            csv_path=str(BASE_DIR / "data" / "tracker.csv"),
            db_path=str(BASE_DIR / "data" / "jobs.db")
        )
        updater.print_stats()
        return

    # 4. EXCEL EXPORT
    if args.export:
        from export_excel import export_tracker_to_excel
        export_tracker_to_excel()
        return

    # Check if profile is configured
    qa_file = BASE_DIR / "context" / "screening_qa.json"
    qa_example = BASE_DIR / "context" / "screening_qa.example.json"
    if not qa_file.exists() and not qa_example.exists():
        print("\n[Notice] No candidate profile found. Launching configuration wizard first...\n")
        from setup_profile import main as setup_main
        setup_main()

    # 5. EXECUTION PIPELINES
    from runner import run_pipeline

    if args.scrape:
        print("[Mode: Scrape Only] Ingesting jobs from ATS boards...")
        run_pipeline(
            batch_size=args.batch_size,
            company=args.company,
            min_score=args.min_score,
            dry_run=args.dry_run,
            prefill=False,
            auto_submit=False
        )

    elif args.match:
        print("[Mode: Match Only] Evaluating resume variants against job descriptions...")
        run_pipeline(
            batch_size=args.batch_size,
            company=args.company,
            min_score=args.min_score,
            dry_run=args.dry_run,
            prefill=False,
            auto_submit=False
        )

    elif args.apply:
        print("[Mode: Apply] Pre-filling and submitting applications...")
        run_pipeline(
            batch_size=args.batch_size,
            company=args.company,
            min_score=args.min_score,
            dry_run=args.dry_run,
            prefill=not args.auto,
            auto_submit=args.auto
        )

    elif args.all or len(sys.argv) == 1:
        print("[Mode: Full Pipeline] Executing end-to-end automated job hunter...")
        run_pipeline(
            batch_size=args.batch_size,
            company=args.company,
            min_score=args.min_score,
            dry_run=args.dry_run,
            prefill=True,
            auto_submit=args.auto
        )


if __name__ == "__main__":
    main()
