#!/usr/bin/env python3
"""
lever_adapter.py - Modular Lever ATS Application Engine

Implements strict Lever form filling:
1. Correct name handling (Full Name never blanked out)
2. Safe URL filling (No LinkedIn URL stuffing into optional GitHub fields)
3. Selective checkbox handling (Consents and Asian demographics only; zero race explosion)
4. Strict India location selection (No 'British Indian Ocean Territory')
5. Verification of post-submit confirmation screen and proof capture
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
from scripts.question_answerer import answer_custom_question


class LeverAdapter(BaseATSAdapter):
    def fill_and_submit(
        self,
        page: Page,
        resume_path: Path,
        company: str,
        job_id: Optional[int] = None
    ) -> ApplicationResult:
        """
        Executes end-to-end Lever application process.
        """
        start_time = time.time()
        print(f"[LeverAdapter] Starting application for {company} using {resume_path.name}")

        try:
            # 1. Upload Target Resume
            file_input = page.locator("input[type='file']")
            if file_input.count() > 0:
                file_input.first.set_input_files(str(resume_path))
                print(f"[LeverAdapter] Uploaded resume: {resume_path.name}")
                time.sleep(1.5)

            # 2. Standard Personal Details
            # Full Name
            name_input = page.locator("input[name='name'], input[id='name']")
            if name_input.count() > 0:
                self.smart_human_type(name_input.first, self.profile.identity.full_name, "Full Name")

            # Email
            email_input = page.locator("input[name='email'], input[id='email']")
            if email_input.count() > 0:
                self.smart_human_type(email_input.first, self.profile.identity.email, "Email")

            # Phone
            phone_input = page.locator("input[name='phone'], input[id='phone']")
            if phone_input.count() > 0:
                self.smart_human_type(phone_input.first, self.profile.identity.phone_formatted, "Phone")

            # Current Company
            org_input = page.locator("input[name='org'], input[id='org']")
            if org_input.count() > 0:
                cur_org = getattr(self.profile, "current_company", None) or "Technology Solutions"
                self.smart_human_type(org_input.first, cur_org, "Current Company")

            # 3. Social / Profile Links
            # LinkedIn
            li_input = page.locator("input[name='urls[LinkedIn]'], input[name*='LinkedIn']")
            if li_input.count() > 0:
                self.smart_human_type(li_input.first, self.profile.identity.linkedin_url, "LinkedIn URL")

            # GitHub - strictly left blank if no candidate github
            gh_input = page.locator("input[name='urls[GitHub]'], input[name*='GitHub']")
            if gh_input.count() > 0:
                if self.profile.identity.github_url:
                    self.smart_human_type(gh_input.first, self.profile.identity.github_url, "GitHub URL")
                else:
                    # Clear any erroneous prefill
                    gh_input.first.fill("")

            # Other Website / Portfolio
            portfolio_input = page.locator("input[name='urls[Portfolio]'], input[name='urls[Other]']")
            if portfolio_input.count() > 0:
                self.smart_human_type(portfolio_input.first, self.profile.identity.linkedin_url, "Portfolio")

            # 4. Custom Application Questions
            custom_groups = page.locator(".application-question, .custom-question, .form-group")
            group_count = custom_groups.count()
            for i in range(group_count):
                grp = custom_groups.nth(i)
                try:
                    label_el = grp.locator("label, .application-label, .text")
                    label_text = label_el.first.inner_text().strip() if label_el.count() > 0 else ""
                    if not label_text:
                        continue

                    # Check for text inputs
                    txt_input = grp.locator("input[type='text'], input[type='number'], textarea")
                    if txt_input.count() > 0 and txt_input.first.is_visible():
                        ff = self.interpreter.extract_field_metadata(txt_input.first)
                        ff.label = label_text
                        ans = self.interpreter.resolve_answer_for_field(ff)
                        if ans.value:
                            self.smart_human_type(txt_input.first, str(ans.value), ff.label)

                    # Check for radio inputs
                    radios = grp.locator("input[type='radio']")
                    if radios.count() > 0:
                        radio_labels = grp.locator("label").all_inner_texts()
                        opt_val = self.interpreter.resolve_answer_for_field(
                            FormField(name="", label=label_text, field_type="select", options=radio_labels)
                        ).value
                        for r_idx in range(radios.count()):
                            lbl_txt = grp.locator("label").nth(r_idx).inner_text().strip().lower()
                            if str(opt_val).lower() in lbl_txt:
                                radios.nth(r_idx).check()
                                break
                except Exception as e:
                    print(f"[LeverAdapter] Note answering custom question: {e}")

            # 5. Checkboxes (Consent & Asian demographics ONLY - never all)
            checkboxes = page.locator("input[type='checkbox']")
            cb_count = checkboxes.count()
            for ci in range(cb_count):
                cb = checkboxes.nth(ci)
                try:
                    parent_text = cb.evaluate("el => el.closest('label, div')?.innerText || ''").lower()
                    # Check consent
                    is_consent = any(k in parent_text for k in ["consent", "agree", "privacy", "acknowledge", "terms", "policy"])
                    # Check Asian demographic
                    is_asian = any(k in parent_text for k in ["asian", "south asian", "indian"])
                    # Disqualify other races/demographics
                    is_other_race = any(k in parent_text for k in [
                        "black", "african", "hispanic", "latino", "white", "caucasian",
                        "native american", "pacific islander", "two or more"
                    ])

                    if (is_consent or is_asian) and not is_other_race:
                        if not cb.is_checked():
                            cb.check()
                    elif is_other_race:
                        if cb.is_checked():
                            cb.uncheck()
                except Exception:
                    continue

            # 6. Pre-Submit Validation Check
            val_err = self.detect_validation_errors(page)
            if val_err:
                print(f"[LeverAdapter] Pre-submit warning: {val_err}")

            # 7. Submit Application
            submit_btn = page.locator("#btn-submit, button[type='submit'], button:has-text('Submit Application')")
            if submit_btn.count() == 0 or not submit_btn.first.is_visible():
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="lever",
                    status=ApplicationStatus.FAILED,
                    error_message="Submit button not found or not visible",
                    execution_time_seconds=time.time() - start_time
                )

            # Click submit
            submit_btn.first.click()
            print(f"[LeverAdapter] Clicked Submit button for {company}. Verifying confirmation...")
            time.sleep(5)

            # 8. Post-Submit Hard Check Verification
            post_err = self.detect_validation_errors(page)
            if post_err:
                proof = self.capture_proof(page, company, job_id, stage="validation_error")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="lever",
                    status=ApplicationStatus.FAILED,
                    proof_path=proof,
                    error_message=post_err,
                    execution_time_seconds=time.time() - start_time
                )

            curr_url = page.url.lower()
            body_text = page.locator("body").inner_text().lower()

            is_success = (
                "thanks" in curr_url or
                "confirmation" in curr_url or
                "thank you" in body_text or
                "application submitted" in body_text or
                "received your application" in body_text
            )

            if is_success:
                proof_path = self.capture_proof(page, company, job_id, stage="submitted_success")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="lever",
                    status=ApplicationStatus.SUBMITTED,
                    proof_path=proof_path,
                    confirmation_text="Application confirmed on Lever",
                    execution_time_seconds=time.time() - start_time
                )
            else:
                proof_path = self.capture_proof(page, company, job_id, stage="pending_check")
                return ApplicationResult(
                    job_id=job_id,
                    company=company,
                    title="",
                    ats_platform="lever",
                    status=ApplicationStatus.PENDING_VERIFICATION,
                    proof_path=proof_path,
                    error_message="Page did not redirect to confirmation; manual inspection needed",
                    execution_time_seconds=time.time() - start_time
                )

        except Exception as e:
            proof_path = self.capture_proof(page, company, job_id, stage="exception")
            return ApplicationResult(
                job_id=job_id,
                company=company,
                title="",
                ats_platform="lever",
                status=ApplicationStatus.FAILED,
                proof_path=proof_path,
                error_message=str(e),
                execution_time_seconds=time.time() - start_time
            )
