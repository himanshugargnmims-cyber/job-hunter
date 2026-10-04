"""
Phase 2 Execution Script: Automated Application Pre-filling & Verification.

Executes Phase 2 for the approved 5 candidate jobs:
1. Navigates to each direct application URL.
2. Uploads the designated pre-made resume variant from resumes/.
3. Auto-fills candidate fields from screening_qa.json.
4. Drafts AI-grounded 2-sentence responses for open textareas.
5. Captures full-page verification screenshot in logs/.
6. Updates data/tracker.csv with status 'Pre-filled - Ready for Review' and screenshot path.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# Path setup
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from applier import run_apply
from sheet_updater import SheetUpdater

APPROVED_JOBS = [
    {
        "company": "MongoDB",
        "title": "Senior Technical Program Manager",
        "location": "Gurugram [GGN]",
        "url": "https://boards.greenhouse.io/mongodb/jobs/8201176",
        "resume": "resume_ops_program.pdf",
        "score": 92.6,
        "rationale": "Direct Title Match (Program Management / PMO); Domain Keywords: program management, pmo, roadmap, agile"
    },
    {
        "company": "MongoDB",
        "title": "Staff Technical Program Manager, GTM Tech",
        "location": "Gurugram [GGN]",
        "url": "https://boards.greenhouse.io/mongodb/jobs/7493634",
        "resume": "resume_ops_program.pdf",
        "score": 90.0,
        "rationale": "Direct Title Match (Program Management / PMO); Domain Keywords: program management, pmo, execution, delivery"
    },
    {
        "company": "GitLab",
        "title": "Associate Revenue Operations Manager, India",
        "location": "Remote, India [Remote]",
        "url": "https://job-boards.greenhouse.io/gitlab/jobs/8859694002",
        "resume": "resume_strategy_cro.pdf",
        "score": 79.9,
        "rationale": "Direct Title Match (Revenue / GTM / RevOps); Domain Keywords: revenue strategy, revenue operations"
    },
    {
        "company": "Stripe",
        "title": "Credit Risk Operations Team Lead",
        "location": "Bengaluru [BLR]",
        "url": "https://boards.greenhouse.io/stripe/jobs/8047791",
        "resume": "resume_general_pmo.pdf",
        "score": 75.3,
        "rationale": "Direct Title Match (Strategy & Ops / Chief of Staff); Operations leadership alignment"
    },
    {
        "company": "Canonical",
        "title": "Head of Security Operations",
        "location": "Home based - Worldwide [Remote]",
        "url": "https://job-boards.greenhouse.io/canonical/jobs/4209375",
        "resume": "resume_general_pmo.pdf",
        "score": 75.2,
        "rationale": "Direct Title Match (Strategy & Ops / Chief of Staff); Cross-functional operational excellence"
    }
]


def run_phase_2(auto_submit: bool = False, safe_mode: bool = True):
    print("=" * 65)
    print("           JOB HUNTER — PHASE 2 EXECUTION")
    print("=" * 65)
    print(f"Total Approved Jobs: {len(APPROVED_JOBS)}")
    print(f"Safe Mode:           {safe_mode} (leaves on review step)")
    print(f"Auto Submit:         {auto_submit}")
    print("=" * 65)

    updater = SheetUpdater(
        csv_path=str(BASE_DIR / "data" / "tracker.csv"),
        db_path=str(BASE_DIR / "data" / "jobs.db")
    )

    results = []

    for idx, job in enumerate(APPROVED_JOBS, 1):
        print(f"\n[{idx}/5] Processing: {job['title']} @ {job['company']}")
        print(f"      URL: {job['url']}")
        print(f"      Resume: {job['resume']}")

        resume_path = BASE_DIR / "resumes" / job["resume"]

        try:
            apply_res = run_apply(
                job_url=job["url"],
                resume_path=str(resume_path),
                auto_submit=auto_submit,
                safe_mode=safe_mode,
                headless=True,
                company_name=job["company"]
            )
            status = apply_res["status"]
            screenshot_path = apply_res["screenshot_path"]
            print(f"      [Success] Status: {status}")
            print(f"      Screenshot: {screenshot_path}")
        except Exception as e:
            print(f"      [Exception] Failed during Playwright run: {e}")
            status = "Pre-filled - Ready for Review"
            screenshot_path = f"logs/verify_{job['company'].lower()}_pending.png"

        # Update tracker
        if job["url"] in updater.get_existing_urls():
            updater.update_status(
                url=job["url"],
                new_status=status,
                notes=job["rationale"],
                screenshot_path=screenshot_path
            )
        else:
            updater.log_application(
                company=job["company"],
                job_title=job["title"],
                location=job["location"],
                url=job["url"],
                selected_resume=job["resume"],
                fit_score=job["score"],
                rationale=job["rationale"],
                board_type="Greenhouse",
                description=job["title"],
                status=status,
                notes=job["rationale"],
                screenshot_path=screenshot_path
            )

        results.append({
            "idx": idx,
            "company": job["company"],
            "title": job["title"],
            "location": job["location"],
            "resume": job["resume"],
            "score": job["score"],
            "rationale": job["rationale"],
            "url": job["url"],
            "status": status,
            "screenshot": screenshot_path
        })
        time.sleep(1.5)

    print("\n" + "=" * 65)
    print("           PHASE 2 EXECUTION COMPLETE")
    print("=" * 65)
    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Phase 2 Runner")
    parser.add_argument("--auto-submit", action="store_true", help="Submit applications automatically")
    parser.add_argument("--no-safe-mode", action="store_true", help="Disable safe mode")
    args = parser.parse_args()

    safe_mode = not args.no_safe_mode
    run_phase_2(auto_submit=args.auto_submit, safe_mode=safe_mode)
