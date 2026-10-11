#!/usr/bin/env python3
"""
workday_adapter.py - Modular Workday Enterprise ATS Application Engine

Integrates Workday automation:
1. Automated tenant account creation and login
2. Multi-step stepper navigation (Steps 1 to 5)
3. Non-destructive inspect-first field typing
4. Spinbutton date calculation (Today + 30 days)
5. Review screen proof capture and submission
"""

import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.adapters.base_adapter import BaseATSAdapter
from scripts.application_models import (
    ApplicationResult,
    ApplicationStatus
)

try:
    from scripts.workday_applier import apply_workday_job
except Exception:
    apply_workday_job = None


class WorkdayAdapter(BaseATSAdapter):
    def apply_job(
        self,
        job_id: int,
        company: str,
        title: str,
        resume_path: Path,
        submit: bool = True
    ) -> ApplicationResult:
        """
        Executes complete Workday workflow for an existing job record in jobs.db.
        """
        start_time = time.time()
        print(f"[WorkdayAdapter] Processing Workday job #{job_id} ({company} - {title})")

        if not apply_workday_job:
            return ApplicationResult(
                job_id=job_id,
                company=company,
                title=title,
                ats_platform="workday",
                status=ApplicationStatus.FAILED,
                error_message="workday_applier module not importable",
                execution_time_seconds=time.time() - start_time
            )

        res = apply_workday_job(job_id=job_id, headless=True, submit=submit)

        status_str = res.get("status", "Failed")
        app_status = ApplicationStatus.SUBMITTED if status_str == "Submitted" else (
            ApplicationStatus.PENDING_VERIFICATION if status_str == "Review Captured" else ApplicationStatus.FAILED
        )

        return ApplicationResult(
            job_id=job_id,
            company=company,
            title=title,
            ats_platform="workday",
            status=app_status,
            proof_path=res.get("screenshot"),
            confirmation_text=res.get("notes"),
            error_message=res.get("error"),
            execution_time_seconds=time.time() - start_time
        )
