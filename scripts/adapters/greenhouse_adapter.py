#!/usr/bin/env python3
"""
greenhouse_adapter.py - Modular Greenhouse ATS Application Engine

Handles:
1. Standard boards and embedded iframes (e.g. MongoDB, HighRadius, Zenoti)
2. React-Select controls (.select__control)
3. Canonical fields (Full Name / First / Last, Email, Phone, Resume)
4. Custom screening questions grounded in profile
5. Automated Greenhouse Security Code / OTP resolver via Gmail IMAP
6. Hard-check post-submit verification with proof screenshots
"""

import sys
import os
import re
import time
from pathlib import Path
from typing import Dict, Any, Optional, Union
from playwright.sync_api import Page, Frame, Locator, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.adapters.base_adapter import BaseATSAdapter
from scripts.application_models import (
    ApplicationResult,
    ApplicationStatus,
    FormField
)
from scripts.question_answerer import answer_custom_question

try:
    from scripts.hard_check_applier import fetch_latest_security_code
except Exception:
    def fetch_latest_security_code(wait_seconds: int = 50) -> Optional[str]:
        return None


class GreenhouseAdapter(BaseATSAdapter):
    def fill_and_submit(
        self,
        page: Page,
        resume_path: Path,
        company: str,
        job_id: Optional[int] = None
    ) -> ApplicationResult:
        """
        Executes end-to-end Greenhouse application process.
        """
        start_time = time.time()
        print(f"[GreenhouseAdapter] Starting application for {company} using {resume_path.name}")

        try:
            # 1. Determine Target (Page vs Embedded Iframe)
            target: Union[Page, Frame] = page
            iframes = page.frames
            for f in iframes:
                try:
                    if f.locator("#first_name, #email, #submit_app").count() > 0:
                        target = f
                        print(f"[GreenhouseAdapter] Detected Greenhouse form inside iframe: {f.name or f.url}")
                        break
                except Exception:
                    pass

            # 2. Upload Resume
            file_input = target.locator("#resume, input[type='file'][name*='resume'], input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(str(resume_path))
                print(f"[GreenhouseAdapter] Uploaded resume: {resume_path.name}")
                time.sleep(1.5)

            # 3. Standard Personal Details
            first_name_input = target.locator("#first_name, input[name='first_name']")
            if first_name_input.count() > 0:
                self.smart_human_type(first_name_input.first, self.profile.identity.first_name, "First Name")

            last_name_input = target.locator("#last_name, input[name='last_name']")
            if last_name_input.count() > 0:
                self.smart_human_type(last_name_input.first, self.profile.identity.last_name, "Last Name")

            email_input = target.locator("#email, input[name='email']")
            if email_input.count() > 0:
                self.smart_human_type(email_input.first, self.profile.identity.email, "Email")

            phone_input = target.locator("#phone, input[name='phone']")
            if phone_input.count() > 0:
                self.smart_human_type(phone_input.first, self.profile.identity.phone_formatted, "Phone")

            # 4. Handle React-Select Controls (.select__control)
            react_selects = target.locator(".select__control")
            r_count = react_selects.count()
            for r_i in range(r_count):
                try:
                    rs = react_selects.nth(r_i)
                    parent_text = rs.evaluate("el => el.closest('.field')?.innerText || ''").lower()
                    if not parent_text:
                        continue

                    # Country dropdown
                    if "country" in parent_text:
                        rs.click()
                        time.sleep(0.3)
                        input_loc = rs.locator("input")
                        if input_loc.count() > 0:
                            input_loc.first.type("India", delay=30)
                            time.sleep(0.5)
                            target.keyboard.press("Enter")
                    # Work authorization / sponsorship dropdown
                    elif "sponsorship" in parent_text or "authorized" in parent_text:
                        rs.click()
                        time.sleep(0.3)
                        target_choice = "No" if "sponsorship" in parent_text else "Yes"
                        input_loc = rs.locator("input")
                        if input_loc.count() > 0:
                            input_loc.first.type(target_choice, delay=30)
                            time.sleep(0.5)
                            target.keyboard.press("Enter")
                except Exception:
                    continue

            # 5. Custom Questions
            field_divs = target.locator(".field, .application-field")
            f_count = field_divs.count()
            for fi in range(f_count):
                f_el = field_divs.nth(fi)
                try:
                    label_el = f_el.locator("label")
                    label_text = label_el.first.inner_text().strip() if label_el.count() > 0 else ""
                    if not label_text:
                        continue

                    # Text inputs
                    inp = f_el.locator("input[type='text'], input[type='number'], textarea")
                    if inp.count() > 0 and inp.first.is_visible():
                        ff = self.interpreter.extract_field_metadata(inp.first)
                        ff.label = label_text
                        ans = self.interpreter.resolve_answer_for_field(ff)
                        if ans.value:
                            self.smart_human_type(inp.first, str(ans.value), label_text)

                    # Standard Select Dropdowns
                    sel = f_el.locator("select")
                    if sel.count() > 0 and sel.first.is_visible():
                        opts = sel.first.locator("option").all_inner_texts()
                        ff = FormField(name="", label=label_text, field_type="select", options=opts)
                        ans = self.interpreter.resolve_answer_for_field(ff)
                        if ans.value:
                            try:
                                sel.first.select_option(label=str(ans.value))
                            except Exception:
                                pass
                except Exception:
                    continue

            # 6. Pre-Submit Error Check
            val_err = self.detect_validation_errors(target)
            if val_err:
                print(f"[GreenhouseAdapter] Pre-submit warning: {val_err}")

            # 7. Submit Application
            submit_btn = target.locator("#submit_app, input[type='submit'], button[type='submit']:has-text('Submit Application')")
            if submit_btn.count() == 0 or not submit_btn.first.is_visible():
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="greenhouse",
                    status=ApplicationStatus.FAILED,
                    error_message="Submit button not found",
                    execution_time_seconds=time.time() - start_time
                )

            submit_btn.first.click()
            print(f"[GreenhouseAdapter] Clicked Submit button for {company}. Waiting for response...")
            time.sleep(5)

            # 8. Check for OTP / Security Code Challenge
            otp_input = target.locator("input[name*='security_code'], input[name*='verification_code'], input[id*='code']")
            if otp_input.count() > 0 and otp_input.first.is_visible():
                print(f"[GreenhouseAdapter] OTP Security Code challenge detected! Fetching code from Gmail...")
                code = fetch_latest_security_code(wait_seconds=50)
                if code:
                    print(f"[GreenhouseAdapter] Security code retrieved. Typing code...")
                    self.smart_human_type(otp_input.first, code, "Security Code")
                    time.sleep(1)
                    target.locator("button:has-text('Verify'), input[type='submit']").first.click()
                    time.sleep(5)
                else:
                    print(f"[GreenhouseAdapter] OTP code could not be retrieved within timeout.")

            # 9. Post-Submit Hard Check Verification
            curr_url = page.url.lower()
            body_text = page.locator("body").inner_text().lower()

            is_success = (
                "confirmation" in curr_url or
                "application_submitted" in curr_url or
                "thank you" in body_text or
                "we have received your application" in body_text or
                "your application was submitted" in body_text
            )

            if is_success:
                proof_path = self.capture_proof(page, company, job_id, stage="submitted_success")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="greenhouse",
                    status=ApplicationStatus.SUBMITTED,
                    proof_path=proof_path,
                    confirmation_text="Application confirmed on Greenhouse",
                    execution_time_seconds=time.time() - start_time
                )
            else:
                post_err = self.detect_validation_errors(target)
                stage = "validation_error" if post_err else "pending_check"
                proof_path = self.capture_proof(page, company, job_id, stage=stage)
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="greenhouse",
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
                ats_platform="greenhouse",
                status=ApplicationStatus.FAILED,
                proof_path=proof_path,
                error_message=str(e),
                execution_time_seconds=time.time() - start_time
            )
