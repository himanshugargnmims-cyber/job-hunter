#!/usr/bin/env python3
"""
ashby_adapter.py - Modular Ashby ATS Application Engine

Handles:
1. Autocomplete location / country dropdowns
2. Dynamic label-based screening questions via FormFieldInterpreter
3. Detection and ledgering of Ashby 60-day re-application throttling
4. Post-submit confirmation screen verification and proof screenshots
"""

import sys
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.adapters.base_adapter import BaseATSAdapter
from scripts.application_models import (
    ApplicationResult,
    ApplicationStatus,
    FormField
)
from scripts.company_policy import CompanyPolicyManager


class AshbyAdapter(BaseATSAdapter):
    def __init__(self, profile=None):
        super().__init__(profile)
        self.policy_mgr = CompanyPolicyManager()

    def fill_and_submit(
        self,
        page: Page,
        resume_path: Path,
        company: str,
        job_id: Optional[int] = None
    ) -> ApplicationResult:
        """
        Executes end-to-end Ashby application process.
        """
        start_time = time.time()
        print(f"[AshbyAdapter] Starting application for {company} using {resume_path.name}")

        try:
            # 1. Check for immediate 60-day throttling message
            page_text = page.locator("body").inner_text().lower()
            if any(k in page_text for k in ["recently applied", "wait 60 days", "re-apply after 60 days", "application limit"]):
                print(f"[AshbyAdapter] Ashby 60-day application limit detected for {company}!")
                self.policy_mgr.record_cooloff(company, "Ashby", 60, "Ashby 60-day re-application limit")
                proof = self.capture_proof(page, company, job_id, stage="ashby_cooloff")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="ashby",
                    status=ApplicationStatus.SKIPPED_COOLOFF,
                    proof_path=proof,
                    error_message="Ashby 60-day cooloff limit active",
                    execution_time_seconds=time.time() - start_time
                )

            # 2. Upload Target Resume
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(str(resume_path))
                print(f"[AshbyAdapter] Uploaded resume: {resume_path.name}")
                time.sleep(1.5)

            # 3. Personal Details
            # Name
            name_input = page.locator("input[name*='name'], input[id*='name']").first
            if name_input.is_visible():
                self.smart_human_type(name_input, self.profile.identity.full_name, "Full Name")

            # Email
            email_input = page.locator("input[type='email'], input[name*='email']").first
            if email_input.is_visible():
                self.smart_human_type(email_input, self.profile.identity.email, "Email")

            # Phone
            phone_input = page.locator("input[type='tel'], input[name*='phone']").first
            if phone_input.is_visible():
                self.smart_human_type(phone_input, self.profile.identity.phone_digits, "Phone")

            # 4. Location Autocomplete
            loc_input = page.locator("input[placeholder*='Location'], input[name*='location']")
            if loc_input.count() > 0 and loc_input.first.is_visible():
                loc_input.first.click()
                loc_input.first.type("Bengaluru, India", delay=35)
                time.sleep(1.0)
                # Select dropdown suggestion
                sugg = page.locator("li:has-text('Bengaluru'), [role='option']:has-text('Bengaluru'), div:has-text('Bengaluru, Karnataka')")
                if sugg.count() > 0:
                    sugg.first.click()
                else:
                    page.keyboard.press("Enter")

            # 5. Dynamic Questions
            inputs = page.locator("input[type='text'], input[type='number'], textarea")
            inp_count = inputs.count()
            for i in range(inp_count):
                inp = inputs.nth(i)
                try:
                    if not inp.is_visible():
                        continue
                    curr_val = inp.input_value().strip()
                    if curr_val:
                        continue  # Already filled

                    ff = self.interpreter.extract_field_metadata(inp)
                    if ff.label:
                        ans = self.interpreter.resolve_answer_for_field(ff)
                        if ans.value:
                            self.smart_human_type(inp, str(ans.value), ff.label)
                except Exception:
                    continue

            # 6. Pre-Submit Validation Check
            val_err = self.detect_validation_errors(page)
            if val_err:
                print(f"[AshbyAdapter] Pre-submit warning: {val_err}")

            # 7. Submit Application
            submit_btn = page.locator("button[type='submit'], button:has-text('Submit Application')")
            if submit_btn.count() == 0 or not submit_btn.first.is_visible():
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="ashby",
                    status=ApplicationStatus.FAILED,
                    error_message="Submit button not found",
                    execution_time_seconds=time.time() - start_time
                )

            submit_btn.first.click()
            print(f"[AshbyAdapter] Clicked Submit button for {company}. Waiting for confirmation...")
            time.sleep(5)

            # 8. Post-Submit Verification
            curr_url = page.url.lower()
            body_text = page.locator("body").inner_text().lower()

            # Check if 60-day limit appeared post-click
            if "recently applied" in body_text or "wait 60 days" in body_text:
                self.policy_mgr.record_cooloff(company, "Ashby", 60, "Ashby 60-day limit triggered on submit")
                proof = self.capture_proof(page, company, job_id, stage="ashby_cooloff")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="ashby",
                    status=ApplicationStatus.SKIPPED_COOLOFF,
                    proof_path=proof,
                    error_message="Ashby 60-day cooloff limit triggered",
                    execution_time_seconds=time.time() - start_time
                )

            is_success = (
                "submitted" in curr_url or
                "thank you" in body_text or
                "application has been submitted" in body_text or
                "received your application" in body_text
            )

            if is_success:
                proof_path = self.capture_proof(page, company, job_id, stage="submitted_success")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="ashby",
                    status=ApplicationStatus.SUBMITTED,
                    proof_path=proof_path,
                    confirmation_text="Application confirmed on Ashby",
                    execution_time_seconds=time.time() - start_time
                )
            else:
                post_err = self.detect_validation_errors(page)
                proof_path = self.capture_proof(page, company, job_id, stage="pending_check")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="ashby",
                    status=ApplicationStatus.FAILED if post_err else ApplicationStatus.PENDING_VERIFICATION,
                    proof_path=proof_path,
                    error_message=post_err or "Submission not confirmed",
                    execution_time_seconds=time.time() - start_time
                )

        except Exception as e:
            proof_path = self.capture_proof(page, company, job_id, stage="exception")
            return ApplicationResult(
                job_id=job_id,
                company=company,
                title="",
                ats_platform="ashby",
                status=ApplicationStatus.FAILED,
                proof_path=proof_path,
                error_message=str(e),
                execution_time_seconds=time.time() - start_time
            )
