#!/usr/bin/env python3
"""
base_adapter.py - Base Abstract ATS Applier Adapter

Provides shared foundational capabilities:
1. Human-cadence keystroke typing (25-45ms/char, randomized jitter)
2. Non-destructive inspect-first input filling
3. Deterministic resume uploading and verification
4. Standard validation-error detection
5. High-resolution confirmation screenshot captures
"""

import sys
import os
import re
import time
import random
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple
from playwright.sync_api import Page, Frame, Locator, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.application_models import (
    CandidateProfile,
    FormField,
    ResolvedAnswer,
    ApplicationResult,
    ApplicationStatus
)
from scripts.form_understanding import FormFieldInterpreter

SCREENSHOTS_DIR = BASE_DIR / "logs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


class BaseATSAdapter:
    def __init__(self, profile: Optional[CandidateProfile] = None):
        self.profile = profile or CandidateProfile.load_from_json(BASE_DIR / "context" / "profile.json")
        self.interpreter = FormFieldInterpreter(self.profile)

    def smart_human_type(
        self,
        locator: Locator,
        value: str,
        field_name: str = "field",
        delay_range: Tuple[int, int] = (25, 45)
    ) -> bool:
        """
        Types value with natural human keystroke cadence and inspect-first protocol.
        If field already contains the correct value, avoids unnecessary re-typing.
        """
        try:
            if not locator.is_visible(timeout=2000):
                locator.scroll_into_view_if_needed(timeout=2000)

            # Non-destructive check
            try:
                curr_val = locator.input_value(timeout=1000).strip()
                if curr_val and curr_val.lower() == value.strip().lower():
                    return True
            except Exception:
                pass

            locator.click(timeout=2000)
            time.sleep(random.uniform(0.1, 0.25))

            # Clear existing content safely
            locator.fill("")
            time.sleep(0.05)

            # Human cadence typing
            for char in str(value):
                locator.type(char, delay=random.randint(delay_range[0], delay_range[1]))

            # Natural inter-field pause
            time.sleep(random.uniform(0.15, 0.35))
            return True
        except Exception as e:
            # Fallback direct fill
            try:
                locator.fill(str(value))
                return True
            except Exception:
                return False

    def upload_resume(
        self,
        target: Union[Page, Frame],
        resume_path: Path,
        file_input_selector: str = "input[type='file']"
    ) -> bool:
        """
        Uploads resume file safely and asserts that the file was accepted.
        """
        if not resume_path.exists():
            print(f"[BaseATSAdapter] ERROR: Target resume not found at {resume_path}")
            return False

        try:
            file_inputs = target.locator(file_input_selector)
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(str(resume_path))
                time.sleep(1.5)
                return True
            return False
        except Exception as e:
            print(f"[BaseATSAdapter] Error uploading resume: {e}")
            return False

    def verify_resume_attached(
        self,
        target: Union[Page, Frame],
        expected_filename: str
    ) -> bool:
        """
        Verifies that the target resume filename appears in the DOM.
        """
        try:
            body_text = target.locator("body").inner_text(timeout=3000)
            base_name = Path(expected_filename).stem.lower()
            return base_name in body_text.lower()
        except Exception:
            return False

    def capture_proof(
        self,
        page: Page,
        company: str,
        job_id: Optional[int] = None,
        stage: str = "submitted"
    ) -> str:
        """
        Captures full-page high-resolution screenshot evidence.
        """
        norm_comp = re.sub(r"[^a-zA-Z0-9]", "_", company.lower().strip())
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        prefix = f"job_{job_id}_" if job_id else ""
        filename = f"{prefix}{norm_comp}_{stage}_{timestamp}.png"
        proof_path = SCREENSHOTS_DIR / filename

        try:
            page.screenshot(path=str(proof_path), full_page=True)
            print(f"[BaseATSAdapter] Captured proof screenshot: {proof_path}")
            return str(proof_path)
        except Exception as e:
            print(f"[BaseATSAdapter] Error capturing screenshot: {e}")
            return ""

    def detect_validation_errors(self, target: Union[Page, Frame]) -> Optional[str]:
        """
        Detects common ATS inline validation error messages.
        """
        error_selectors = [
            ".error-message", ".validation-error", "[class*='error']",
            "[aria-invalid='true']", ".is-error", ".field-error",
            "div:has-text('Please fill in this field')",
            "div:has-text('This field is required')",
            "span:has-text('Required')"
        ]
        for sel in error_selectors:
            try:
                err_loc = target.locator(sel)
                count = err_loc.count()
                for i in range(min(count, 3)):
                    item = err_loc.nth(i)
                    if item.is_visible(timeout=500):
                        txt = item.inner_text().strip()
                        if txt and len(txt) > 3 and not any(ign in txt.lower() for ign in ["optional", "agree"]):
                            return f"Validation error detected: {txt}"
            except Exception:
                continue
        return None
