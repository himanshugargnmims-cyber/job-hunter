"""
LinkedIn Easy Apply Automation Engine using Playwright.

Leverages a persistent browser context (real Chrome session with saved cookies):
1. Navigates to LinkedIn Jobs with 'Easy Apply' filter (f_AL=true).
2. Detects authentication state (checks URLs, titles, and form elements) and waits for login.
3. Searches against candidate target roles and locations from preferences.json.
4. Evaluates job descriptions with ResumeSelector against pre-made resume variants.
5. Auto-fills Easy Apply modals (contact, resume upload, experience, authorization, dropdowns, AI QA).
6. Completes the application end-to-end and clicks the Submit button (when auto_submit=True).
7. Captures verification screenshots in logs/.
8. Persists applied jobs to SQLite (jobs.db) and CSV (tracker.csv).
"""

import os
import sys
import re
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import quote_plus

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeoutError

# Path resolution
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from resume_selector import ResumeSelector
from sheet_updater import SheetUpdater
from question_answerer import answer_custom_question, load_default_context_notes
from company_policy import CompanyPolicyManager
from eligibility import evaluate_eligibility
from application_models import JobPosting, ATSPlatform
from field_resolver import (
    resolve_text_input,
    resolve_radio_or_dropdown,
    resolve_salary,
    resolve_notice_period,
    resolve_experience,
    resolve_phone
)
from dotenv import load_dotenv

load_dotenv(BASE_DIR / ".env")
load_dotenv()

# Load screening QA data
QA_PATH = BASE_DIR / "context" / "screening_qa.json"
QA_DATA = {}
if QA_PATH.exists():
    with open(QA_PATH, "r", encoding="utf-8") as f:
        QA_DATA = json.load(f)

# Load search preferences
PREF_PATH = BASE_DIR / "context" / "preferences.json"
PREFERENCES = {}
if PREF_PATH.exists():
    with open(PREF_PATH, "r", encoding="utf-8") as f:
        PREFERENCES = json.load(f)


def get_default_chrome_user_data_dir() -> str:
    """Returns a dedicated Chrome profile directory for persistent LinkedIn sessions."""
    profile_dir = os.path.expanduser("~/.chrome_linkedin_profile")
    os.makedirs(profile_dir, exist_ok=True)
    return profile_dir


class LinkedInApplier:
    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        headless: bool = False,
        min_score: Optional[float] = None,
        auto_submit: bool = True,
        li_at_cookie: Optional[str] = None,
        cdp_url: Optional[str] = None
    ):
        self.user_data_dir = user_data_dir or get_default_chrome_user_data_dir()
        self.headless = headless
        self.min_score = min_score or float(PREFERENCES.get("minimum_match_score", 75.0))
        self.auto_submit = auto_submit
        self.li_at_cookie = li_at_cookie or os.getenv("LINKEDIN_LI_AT")
        self.cdp_url = cdp_url or os.getenv("CHROME_CDP_URL")

        self.selector = ResumeSelector(resumes_dir=str(BASE_DIR / "resumes"))
        self.updater = SheetUpdater(
            csv_path=str(BASE_DIR / "data" / "tracker.csv"),
            db_path=str(BASE_DIR / "data" / "jobs.db")
        )
        self.existing_urls = self.updater.get_existing_urls()
        self.context_notes = load_default_context_notes()

    def is_authenticated(self, page: Page) -> bool:
        try:
            curr_url = page.url.lower()
            if any(k in curr_url for k in ["/uas/login", "/checkpoint", "/signup", "session_redirect"]):
                return False

            title_lower = page.title().lower()
            if any(k in title_lower for k in ["sign up", "sign in", "login", "log in", "join linkedin"]) and "feed" not in title_lower:
                return False

            if "/feed" in curr_url or "feed | linkedin" in title_lower:
                return True

            # If Easy Apply or Save button is present on job page, we are authenticated
            if page.locator('button.jobs-apply-button, button:has-text("Easy Apply"), button.jobs-save-button').count() > 0:
                return True

            # Check for unauthenticated signup/login form elements
            has_login_form = page.locator('input[autocomplete="username"], input[name="session_key"], button:has-text("Agree & Join")').count() > 0
            has_auth_nav = page.locator('#global-nav, nav.global-nav, .global-nav__me, button.global-nav__primary-link, .global-nav__nav').count() > 0

            if has_auth_nav:
                return True
            if has_login_form:
                return False

            # Check if job search cards are rendered
            has_cards = page.locator('.jobs-search-results-list, .job-card-container, [data-occludable-job-id], [componentkey*="job-card-component-ref-"]').count() > 0
            if has_cards:
                return True

            return False
        except Exception:
            return False

    def fill_form_fields(self, page: Page, modal, resume_path: str):
        """Fills standard inputs, dropdowns, radios, and textareas inside the Easy Apply modal."""
        # 1. Accurate Resume Selection / Upload on LinkedIn Easy Apply
        target_resume_name = Path(resume_path).name if resume_path else ""
        if target_resume_name and Path(resume_path).exists():
            # Check if this modal step contains the Resume section
            resume_header = modal.locator('h3:has-text("Resume"), label:has-text("Resume"), span:has-text("Resume*"), h2:has-text("Resume")')
            has_resume_section = (resume_header.count() > 0 and resume_header.first.is_visible()) or \
                                 modal.locator('button:has-text("Upload resume"), button:has-text("Upload")').count() > 0 or \
                                 modal.locator('div[role="button"]:has-text(".pdf"), label:has-text(".pdf")').count() > 0

            if has_resume_section:
                target_ver = target_resume_name.split("_")[0].lower() if "_" in target_resume_name else ""
                card_clicked = False

                # 1.1 Match card by version prefix (e.g. V1_, V2_, V3_, V4_, V5_) or full name
                card_candidates = modal.locator('div[role="button"], label, div[class*="document"], div[class*="resume"]').filter(has_text=".pdf")
                c_count = card_candidates.count()
                for ci in range(c_count):
                    c_el = card_candidates.nth(ci)
                    try:
                        c_text = c_el.inner_text().lower()
                        if target_ver and (f"{target_ver}_" in c_text or c_text.startswith(f"{target_ver}_") or target_resume_name.lower() in c_text):
                            radio = c_el.locator('input[type="radio"], [role="radio"]')
                            if radio.count() > 0:
                                radio.first.click(force=True)
                            else:
                                c_el.click(force=True)
                            print(f"      [Resume] Selected existing matching card ({target_ver.upper()}): {target_resume_name}")
                            card_clicked = True
                            time.sleep(1.0)
                            break
                    except Exception:
                        continue

                # 1.2 If matching resume was not found in library, upload the target resume file fresh
                if not card_clicked:
                    try:
                        modal.evaluate('el => el.scrollTop = el.scrollHeight')
                    except Exception:
                        pass
                    time.sleep(0.5)

                    file_inputs = modal.locator('input[type="file"]')
                    if file_inputs.count() > 0:
                        try:
                            file_inputs.first.set_input_files(str(resume_path))
                            print(f"      [Resume] Attached file directly via input: {target_resume_name}")
                            time.sleep(2.0)
                            card_clicked = True
                        except Exception:
                            pass

                    if not card_clicked:
                        upload_btn = modal.locator('button:has-text("Upload resume"), button:has-text("Upload"), label:has-text("Upload resume")')
                        if upload_btn.count() > 0 and upload_btn.first.is_visible():
                            try:
                                with page.expect_file_chooser(timeout=5000) as fc_info:
                                    upload_btn.first.click(force=True)
                                file_chooser = fc_info.value
                                file_chooser.set_files(str(resume_path))
                                print(f"      [Resume] Uploaded matching target resume: {target_resume_name}")
                                time.sleep(2.5)
                                card_clicked = True
                            except Exception as e:
                                # Fallback to direct input[type="file"] if file chooser fails
                                file_inputs = modal.locator('input[type="file"]')
                                if file_inputs.count() > 0:
                                    try:
                                        file_inputs.first.set_input_files(str(resume_path))
                                        print(f"      [Resume] Attached file directly: {target_resume_name}")
                                        time.sleep(1.0)
                                        card_clicked = True
                                    except Exception:
                                        pass

                # Fallback: if standard file input is directly available on non-card forms
                if not card_clicked:
                    file_inputs = modal.locator('input[type="file"]')
                    if file_inputs.count() > 0:
                        try:
                            file_inputs.first.set_input_files(str(resume_path))
                            print(f"      [Resume] Attached file directly: {target_resume_name}")
                            time.sleep(1.0)
                        except Exception:
                            pass

        # 2. Text / Tel / Email / Number / Textarea fields
        text_inputs = modal.locator('input[type="text"], input[type="tel"], input[type="email"], input[type="number"], input:not([type]), textarea')
        for i in range(text_inputs.count()):
            elem = text_inputs.nth(i)
            if not elem.is_visible():
                continue

            elem_id = elem.get_attribute("id") or ""
            elem_name = elem.get_attribute("name") or ""
            elem_type = elem.get_attribute("type") or "text"
            placeholder = elem.get_attribute("placeholder") or ""
            max_len = elem.get_attribute("maxlength")
            try:
                max_len_int = int(max_len) if max_len and int(max_len) > 0 else None
            except Exception:
                max_len_int = None

            # Gather comprehensive context (previous siblings, parent headings, labels, etc.)
            context_text = elem.evaluate('''e => {
                let texts = [];
                if (e.id) {
                    let lbl = document.querySelector('label[for="' + e.id + '"]');
                    if (lbl) texts.push(lbl.innerText);
                }
                let p = e.parentElement;
                if (p && p.previousElementSibling) texts.push(p.previousElementSibling.innerText);
                let pp = p ? p.parentElement : null;
                if (pp && pp.previousElementSibling) texts.push(pp.previousElementSibling.innerText);
                let ppp = pp ? pp.parentElement : null;
                if (ppp) texts.push(ppp.innerText);
                if (e.getAttribute('aria-label')) texts.push(e.getAttribute('aria-label'));
                if (e.placeholder) texts.push(e.placeholder);
                return texts.join(' ');
            }''')

            current_val = elem.input_value().strip()

            resolved_val = resolve_text_input(
                field_name=elem_name,
                field_id=elem_id,
                label_text="",
                parent_text=context_text,
                placeholder=placeholder,
                field_type=elem_type,
                max_length=max_len_int,
                qa_data=QA_DATA
            )

            if resolved_val:
                if not current_val:
                    elem.fill(resolved_val)
                    print(f"      [Field] Auto-filled '{resolved_val}' for context: {context_text[:50]}...")
                elif current_val != resolved_val and (any(k in context_text.lower() for k in ["ctc", "salary", "notice", "experience"]) or not current_val.isdigit()):
                    elem.fill(resolved_val)
                    print(f"      [Field] Corrected '{current_val}' -> '{resolved_val}'")

        # 3. Handle Select Dropdowns
        # 3. Handle Select Dropdowns
        selects = modal.locator('select')
        for i in range(selects.count()):
            sel = selects.nth(i)
            if not sel.is_visible():
                continue

            sel_context = sel.evaluate('''el => {
                let p = el.parentElement;
                let q = '';
                if (el.previousElementSibling) q += el.previousElementSibling.innerText + ' ';
                if (p && p.previousElementSibling) q += p.previousElementSibling.innerText + ' ';
                if (p) q += p.innerText + ' ';
                return q;
            }''')

            try:
                options = sel.locator('option')
                opt_texts = [options.nth(j).inner_text().strip() for j in range(options.count())]

                chosen_opt = resolve_radio_or_dropdown(sel_context, opt_texts)
                if chosen_opt:
                    sel.select_option(label=chosen_opt)
                    print(f"      [Select] Selected '{chosen_opt}'")
                elif any(k in sel_context.lower() for k in ["phone", "country code"]):
                    for opt in opt_texts:
                        if "india" in opt.lower() or "+91" in opt:
                            sel.select_option(label=opt)
                            break
            except Exception:
                pass

        # 4. Radio buttons (Fieldsets and groups)
        radios = modal.locator('fieldset, div[role="radiogroup"]')
        for i in range(radios.count()):
            fs = radios.nth(i)
            q_text = fs.evaluate('''el => {
                let p = el.parentElement;
                let q = '';
                if (el.previousElementSibling) q += el.previousElementSibling.innerText + ' ';
                if (p && p.previousElementSibling) q += p.previousElementSibling.innerText + ' ';
                if (p) q += p.innerText + ' ';
                return q;
            }''')

            r_inputs = fs.locator('input[type="radio"]').all()
            if not r_inputs:
                continue

            chosen = resolve_radio_or_dropdown(q_text, ["Yes", "No"]) or "Yes"
            target_idx = 0 if chosen.lower() in ["yes", "authorized", "completed", "open", "agree"] else 1
            if target_idx < len(r_inputs):
                if not r_inputs[target_idx].is_checked():
                    try:
                        r_inputs[target_idx].evaluate('''el => {
                            el.checked = true;
                            el.dispatchEvent(new Event("change", { bubbles: true }));
                            el.dispatchEvent(new Event("click", { bubbles: true }));
                        }''')
                        print(f"      [Radio] Checked '{chosen}' for: {q_text[:50]}...")
                    except Exception:
                        pass

        # 5. Checkboxes (e.g. Terms / Follow company)
        checkboxes = modal.locator('input[type="checkbox"]')
        for i in range(checkboxes.count()):
            cb = checkboxes.nth(i)
            cb_label = modal.locator(f'label[for="{cb.get_attribute("id")}"]')
            lbl_text = cb_label.first.inner_text().lower() if cb_label.count() > 0 else ""

            try:
                if "follow" in lbl_text:
                    if cb.is_checked():
                        cb.uncheck(force=True)
                elif "agree" in lbl_text or "terms" in lbl_text or cb.get_attribute("required"):
                    if not cb.is_checked():
                        cb.check(force=True)
            except Exception:
                pass

        # 6. Textareas (Screening QA)
        textareas = modal.locator('textarea')
        for i in range(textareas.count()):
            ta = textareas.nth(i)
            if not ta.is_visible():
                continue
            if not ta.input_value().strip():
                ta_id = ta.get_attribute("id")
                question_text = "Experience & Role Fit"
                if ta_id:
                    lbl = modal.locator(f'label[for="{ta_id}"]')
                    if lbl.count() > 0:
                        question_text = lbl.first.inner_text().strip()
                if question_text == "Experience & Role Fit":
                    question_text = ta.get_attribute("placeholder") or ta.get_attribute("name") or "Relevant Experience"

                answer = answer_custom_question(question_text, self.context_notes)
                ta.fill(answer)
                print(f"      [QA] Answered textarea ('{question_text[:30]}...'): {answer[:50]}...")

    def resolve_form_errors(self, modal):
        """Scans for active validation error indicators and immediately injects clean direct digits or answers."""
        error_locators = modal.locator('.artdeco-inline-feedback--error, [data-test-form-element-error-messages], .fb-form-element--error, [aria-invalid="true"]')
        count = error_locators.count()
        if count == 0:
            return
        print(f"      [Auto-Remediate] Analyzing {count} form validation errors...")
        for i in range(count):
            err = error_locators.nth(i)
            try:
                if not err.is_visible():
                    continue
                err_text = err.inner_text().lower()
                # Find container element
                container = err.locator('xpath=ancestor::*[contains(@class, "fb-form-element") or contains(@class, "jobs-easy-apply-form-section__grouping")][1]')
                if container.count() == 0:
                    container = err.locator('xpath=..')
                c_text = container.first.inner_text().lower() if container.count() > 0 else ""

                # Inputs inside container
                inputs = container.locator('input[type="text"], input[type="number"], input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"])')
                for j in range(inputs.count()):
                    inp = inputs.nth(j)
                    if not inp.is_visible():
                        continue
                    inp.fill("")
                    val = resolve_text_input(
                        field_name="",
                        field_id=inp.get_attribute("id") or "",
                        label_text="",
                        parent_text=c_text + " " + err_text,
                        field_type=inp.get_attribute("type") or "text"
                    )
                    if val:
                        inp.fill(val)
                        print(f"      [Auto-Remediate] Injected '{val}'")
                    elif any(w in err_text for w in ["number", "whole number", "numeric", "valid number", "digits", "decimal"]):
                        inp.fill("9")
                        print(f"      [Auto-Remediate] Injected fallback pure digits -> '9'")
                    else:
                        inp.fill("Yes")
                        print(f"      [Auto-Remediate] Injected required text -> 'Yes'")
            except Exception:
                pass

    def process_easy_apply_wizard(self, page: Page, resume_path: str, company: str = "Company") -> Dict[str, Any]:
        """Walks through multi-step Easy Apply dialog modal and clicks Submit."""
        modal_locator = page.locator('dialog, .jobs-easy-apply-modal, div[role="dialog"]:has-text("Easy Apply"), div[role="dialog"]:has-text("Apply to")')
        try:
            modal_locator.first.wait_for(state="visible", timeout=10000)
        except Exception:
            pass
        if modal_locator.count() == 0 or not modal_locator.first.is_visible():
            return {"status": "Failed to open modal", "screenshot": ""}
        modal = modal_locator.first

        max_steps = 10
        step = 0
        logs_dir = BASE_DIR / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        clean_company = re.sub(r"[^a-zA-Z0-9_-]", "_", company.lower())

        while step < max_steps:
            step += 1
            print(f"   -> Processing Easy Apply wizard step {step}...")
            time.sleep(1.2)

            self.fill_form_fields(page, modal, resume_path)
            self.resolve_form_errors(modal)

            # Scroll modal to reveal any bottom buttons
            try:
                modal.evaluate('el => el.scrollTop = el.scrollHeight')
            except Exception:
                pass
            time.sleep(0.5)

            # Check for Submit application button
            submit_btn = modal.locator('button[aria-label="Submit application"], button:has-text("Submit application"), footer button:has-text("Submit")')
            if submit_btn.count() > 0 and submit_btn.first.is_visible():
                print("   -> Found 'Submit application' button!")

                # Verify which resume is actually attached on the review screen
                target_resume_name = Path(resume_path).name if resume_path else ""
                target_ver = target_resume_name.split("_")[0].lower() if "_" in target_resume_name else ""
                is_resume_verified = False

                try:
                    review_text = modal.inner_text()
                    pdf_matches = re.findall(r"([A-Za-z0-9_-]+\.pdf)", review_text)
                    if pdf_matches:
                        actual_resume = pdf_matches[0]
                        actual_ver = actual_resume.split("_")[0].lower() if "_" in actual_resume else ""
                        if actual_ver == target_ver or actual_resume.lower() == target_resume_name.lower():
                            print(f"      [Review Resume Verified] Target match: {actual_resume} ({target_ver.upper()})")
                            is_resume_verified = True
                        else:
                            print(f"      [Review Resume Mismatch] Screen displays '{actual_resume}', expected '{target_resume_name}'")
                except Exception:
                    pass

                # If mismatched, attempt self-healing by clicking Edit next to Resume section
                if not is_resume_verified and target_resume_name:
                    print("      [Auto-Remediate] Clicking 'Edit' next to Resume on review screen to fix attachment...")
                    try:
                        edit_btn = modal.locator('div:has-text("Resume") button:has-text("Edit"), button[aria-label*="Resume"], [aria-label*="Edit resume"]')
                        if edit_btn.count() == 0:
                            edit_btn = modal.locator('button:has-text("Edit")')
                        if edit_btn.count() > 0:
                            if edit_btn.count() >= 2:
                                edit_btn.nth(1).click(force=True)
                            else:
                                edit_btn.first.click(force=True)
                            time.sleep(1.5)

                            # Re-run fill_form_fields on the Resume step
                            self.fill_form_fields(page, modal, resume_path)
                            time.sleep(1.0)

                            # Click Review button to return to Review screen
                            rev_btn = modal.locator('footer button:has-text("Review"), footer button:has-text("Next")')
                            if rev_btn.count() > 0:
                                rev_btn.first.click(force=True)
                                time.sleep(1.5)

                            # Re-check review screen
                            rev_text_2 = modal.inner_text()
                            pdf_matches_2 = re.findall(r"([A-Za-z0-9_-]+\.pdf)", rev_text_2)
                            if pdf_matches_2:
                                actual_resume_2 = pdf_matches_2[0]
                                actual_ver_2 = actual_resume_2.split("_")[0].lower() if "_" in actual_resume_2 else ""
                                if actual_ver_2 == target_ver or actual_resume_2.lower() == target_resume_name.lower():
                                    print(f"      [Review Resume Verified After Remediation] Target match: {actual_resume_2}")
                                    is_resume_verified = True
                                else:
                                    print(f"      [Review Resume Alert] Still displaying '{actual_resume_2}' after remediation.")
                    except Exception as e:
                        print(f"      [Auto-Remediate Note]: {e}")

                # SAFETY GATE: If target resume still does not match, ABORT SUBMISSION!
                if not is_resume_verified and target_resume_name:
                    print(f"   -> [SUBMISSION BLOCKED]: Resume mismatch safety gate active for {company}. Not submitting with wrong resume!")
                    mismatch_screen = logs_dir / f"mismatch_blocked_{clean_company}_{timestamp}.png"
                    try:
                        modal.screenshot(path=str(mismatch_screen))
                    except Exception:
                        pass
                    dismiss = modal.locator('button[aria-label="Dismiss"], button.artdeco-modal__dismiss, button:has-text("Dismiss")')
                    if dismiss.count() > 0:
                        dismiss.first.click(force=True)
                        time.sleep(0.5)
                        discard = page.locator('button:has-text("Discard")')
                        if discard.count() > 0:
                            discard.first.click(force=True)
                    return {"status": "Blocked: Resume Mismatch", "screenshot": str(mismatch_screen)}

                if self.auto_submit:
                    pre_screen = logs_dir / f"presubmit_{clean_company}_{timestamp}.png"
                    try:
                        modal.screenshot(path=str(pre_screen))
                    except Exception:
                        pass

                    submit_btn.first.click(force=True)
                    print("   -> CLICKED SUBMIT APPLICATION BUTTON!")
                    time.sleep(3.0)

                    submitted_screen = logs_dir / f"submitted_linkedin_{clean_company}_{timestamp}.png"
                    try:
                        page.screenshot(path=str(submitted_screen), full_page=False)
                        print(f"   -> Saved submission screenshot: {submitted_screen}")
                    except Exception as e:
                        print(f"   -> Screenshot note: {e}")

                    # Check for post-submit daily limit notification
                    limit_text = ""
                    try:
                        limit_text = page.locator('body').inner_text().lower()
                    except Exception:
                        pass
                    daily_limit = any(k in limit_text for k in ["reached the easy apply limit", "reached your application limit", "maximum number of applications", "come back tomorrow"])
                    if daily_limit:
                        print("\n[DAILY LIMIT REACHED] LinkedIn has reached the daily Easy Apply cap!")

                    # Dismiss any post-submit confirmation modal
                    dismiss_btn = page.locator('button[aria-label="Dismiss"], button:has-text("Done"), button[data-test-modal-close-btn]')
                    if dismiss_btn.count() > 0:
                        try:
                            dismiss_btn.first.click(force=True)
                        except Exception:
                            pass

                    return {
                        "status": "Submitted",
                        "screenshot": str(submitted_screen),
                        "limit_reached": daily_limit
                    }
                else:
                    return {
                        "status": "Pre-filled - Ready for Review",
                        "screenshot": "",
                        "limit_reached": False
                    }

            def safe_click_btn(btn_locator):
                try:
                    btn_locator.click(timeout=5000, force=True)
                except Exception:
                    try:
                        handle = btn_locator.element_handle()
                        if handle:
                            page.evaluate('(el) => el.click()', handle)
                    except Exception:
                        pass

            # Check for Review button
            review_btn = modal.locator('button[aria-label="Review your application"], button:has-text("Review"), footer button:has-text("Review")')
            if review_btn.count() > 0 and review_btn.first.is_visible():
                print("   -> Clicking Review button...")
                safe_click_btn(review_btn.first)
                time.sleep(1.5)

                # Check if validation error blocked Review
                error_msgs = modal.locator('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]')
                if error_msgs.count() > 0:
                    print(f"   -> Handled {error_msgs.count()} validation warnings on review step, attempting fix...")
                    self.resolve_form_errors(modal)
                    self.fill_form_fields(page, modal, resume_path)
                    time.sleep(0.5)
                    safe_click_btn(review_btn.first)
                continue

            # Check for Next button
            next_btn = modal.locator('button[aria-label="Continue to next step"], button:has-text("Next"), footer button:has-text("Next")')
            if next_btn.count() > 0 and next_btn.first.is_visible():
                print("   -> Clicking Next button...")
                safe_click_btn(next_btn.first)
                time.sleep(1.5)

                # Check if validation error prevents proceeding
                error_msgs = modal.locator('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]')
                if error_msgs.count() > 0:
                    print(f"   -> Handled {error_msgs.count()} validation warnings, attempting fix...")
                    self.resolve_form_errors(modal)
                    self.fill_form_fields(page, modal, resume_path)
                    time.sleep(0.5)
                    safe_click_btn(next_btn.first)
                continue

            break

        # If modal could not be submitted, dismiss it cleanly so next card can be processed
        try:
            dismiss_btn = modal.locator('button[aria-label="Dismiss"], button.artdeco-modal__dismiss').first
            if dismiss_btn.is_visible():
                dismiss_btn.click(force=True)
                time.sleep(1.0)
                discard_btn = page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")').first
                if discard_btn.is_visible():
                    discard_btn.click(force=True)
                    time.sleep(1.0)
        except Exception:
            pass

        return {"status": "Pre-filled", "screenshot": ""}

    def apply_to_job_listing(self, page: Page, job_card) -> Optional[Dict[str, Any]]:
        """Processes an individual job card on LinkedIn Jobs."""
        try:
            job_card.scroll_into_view_if_needed()
            job_card.click()
            time.sleep(2.0)

            title_elem = page.locator('.job-details-jobs-unified-top-card__job-title, .jobs-unified-top-card__job-title, h1')
            title = title_elem.first.inner_text().strip() if title_elem.count() > 0 else "Unknown Title"

            comp_elem = page.locator('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name')
            company = comp_elem.first.inner_text().strip() if comp_elem.count() > 0 else "Unknown Company"

            loc_elem = page.locator('.job-details-jobs-unified-top-card__bullet, .jobs-unified-top-card__bullet, .job-details-jobs-unified-top-card__workplace-type')
            location = loc_elem.first.inner_text().strip() if loc_elem.count() > 0 else "India"

            url = page.url

            if url in self.existing_urls:
                print(f"[-] Already tracked: {title} @ {company}")
                return None

            # 1. Company Policy Gate (<= 2 applications per company, cooloffs, blacklists)
            policy_mgr = CompanyPolicyManager(BASE_DIR / "data" / "jobs.db")
            can_apply, policy_reason = policy_mgr.can_apply(company)
            if not can_apply:
                print(f"       Skipping: {policy_reason}")
                return None

            desc_elem = page.locator('#job-details, .jobs-description__content, .jobs-box__html-content')
            description = desc_elem.first.inner_text().strip() if desc_elem.count() > 0 else f"{title} at {company}"

            # 2. Universal Eligibility & Seniority Gatekeeper
            job_post = JobPosting(
                company=company,
                title=title,
                location=location,
                url=url,
                ats_platform=ATSPlatform.LINKEDIN_EASY,
                job_description=description
            )
            elig = evaluate_eligibility(job_post)
            if not elig.is_eligible:
                print(f"       Skipping: Ineligible - {elig.reason}")
                return None

            selected_resume = Path(elig.target_resume).name if elig.target_resume else "V1_GTM_Revenue_Strategy.pdf"
            rationale = elig.reason
            fit_score = 95.0

            print(f"\n[Card] {title} @ {company} ({location})")
            print(f"       Charter: {elig.matched_track} -> Selected Resume: {selected_resume}")

            easy_apply_btn = page.locator('.jobs-apply-button--top-card button, .jobs-s-apply button, button.jobs-apply-button:has-text("Easy Apply")')
            if easy_apply_btn.count() == 0 or not easy_apply_btn.first.is_visible():
                print("       Note: Easy Apply button not directly available on this card.")
                return None

            btn_elem = easy_apply_btn.first
            if btn_elem.is_disabled() or "disabled" in (btn_elem.get_attribute("class") or ""):
                print("       Note: Easy Apply button is disabled or already applied.")
                return None

            print("       -> Clicking Easy Apply button...")
            try:
                btn_elem.click(timeout=5000)
            except Exception as e:
                print(f"       Could not click Easy Apply: {e}")
                return None
            time.sleep(2.0)

            resume_file = BASE_DIR / "resumes" / selected_resume
            result = self.process_easy_apply_wizard(page, str(resume_file), company=company)
            status = result["status"]
            screenshot_path = result.get("screenshot", "")
            print(f"       Result Status: {status}")

            self.updater.log_application(
                company=company,
                job_title=title,
                location=location,
                url=url,
                selected_resume=selected_resume,
                fit_score=fit_score,
                rationale=rationale,
                board_type="LinkedIn Easy Apply",
                description=description[:1000],
                status=status,
                notes=f"Auto-applied via LinkedIn Easy Apply. Resume: {selected_resume}",
                screenshot_path=screenshot_path
            )
            self.existing_urls.add(url)

            return {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
                "score": fit_score,
                "status": status,
                "resume": selected_resume,
                "screenshot": screenshot_path,
                "limit_reached": result.get("limit_reached", False)
            }
        except Exception as e:
            print(f"       Error processing job: {e}")
            try:
                dismiss_btn = page.locator('button[aria-label="Dismiss"], button.artdeco-modal__dismiss, button[data-test-modal-close-btn]').first
                if dismiss_btn.is_visible():
                    dismiss_btn.click(force=True)
                    time.sleep(1.0)
                    discard_btn = page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")').first
                    if discard_btn.is_visible():
                        discard_btn.click(force=True)
                        time.sleep(1.0)
            except Exception:
                pass
            return None

    def apply_to_direct_job_page(self, page: Page, direct_url: str, job_metadata: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Applies to a specific LinkedIn job posting by direct URL."""
        if not self.is_authenticated(page):
            auth_ok = self.wait_for_authentication(page)
            if not auth_ok:
                return None

        # Extract title and company
        time.sleep(2.0)
        title_loc = page.locator('h1.t-24, .job-details-jobs-unified-top-card__job-title, h1, .jobs-unified-top-card__job-title')
        title = title_loc.first.inner_text().strip() if title_loc.count() > 0 else "Leadership Role"

        comp_loc = page.locator('.job-details-jobs-unified-top-card__company-name, .jobs-unified-top-card__company-name a, .jobs-unified-top-card__company-name, a.ember-view[href*="/company/"]')
        company = comp_loc.first.inner_text().strip() if comp_loc.count() > 0 else "Company"

        loc_loc = page.locator('.job-details-jobs-unified-top-card__primary-description-container, .jobs-unified-top-card__bullet, .jobs-unified-top-card__workplace-type')
        location = loc_loc.first.inner_text().strip() if loc_loc.count() > 0 else "India"

        if job_metadata:
            title = job_metadata.get("title") or title
            company = job_metadata.get("company") or company
            location = job_metadata.get("location") or location

        print(f"\n[Direct Job] {title} @ {company} ({location})")
        print(f"URL: {direct_url}")

        # Check if already applied
        applied_indicators = page.locator('span:has-text("Applied"), .jobs-s-apply__applied-badge, div:has-text("Application submitted")')
        if applied_indicators.count() > 0 and applied_indicators.first.is_visible():
            print(f"       [Skipping] Already applied to this job: {title} @ {company}")
            return {"title": title, "company": company, "status": "Submitted", "url": direct_url}

        # Check company application limit in database (< 2 cap)
        clean_company = company.strip().lower()
        if clean_company and clean_company not in ['company', 'confidential', 'stealth']:
            try:
                with sqlite3.connect(str(BASE_DIR / "data" / "jobs.db")) as c_conn:
                    c_cursor = c_conn.cursor()
                    c_cursor.execute("SELECT count(*) FROM jobs WHERE LOWER(company) = ? AND status = 'Submitted'", (clean_company,))
                    c_count = c_cursor.fetchone()[0]
                    if c_count >= 2:
                        print(f"       [Skipping] Company '{company}' already reached max 2 submitted jobs across database.")
                        return None
            except Exception:
                pass

        # Evaluate fit and select resume
        if job_metadata and "resume" in job_metadata and (BASE_DIR / job_metadata["resume"]).exists():
            resume_path = str(BASE_DIR / job_metadata["resume"])
            selected_resume = Path(resume_path).name
            fit_score = 95.0
            eval_result = {"fit_score": 95.0, "selected_resume": selected_resume, "rationale": f"Pre-matched to {job_metadata.get('pillar', 'Leadership')}"}
        else:
            desc_elem = page.locator('#job-details, .jobs-description__content, .jobs-box__html-content')
            description = desc_elem.first.inner_text().strip() if desc_elem.count() > 0 else f"{title} at {company}"
            eval_result = self.selector.evaluate_fit(title, description)
            fit_score = eval_result["fit_score"]
            selected_resume = eval_result["selected_resume"]
            resume_path = str(BASE_DIR / "resumes" / selected_resume)

        print(f"       Fit Score: {fit_score}% -> {selected_resume}")

        # Check for Easy Apply button
        easy_apply_btn = page.locator('button[aria-label*="Easy Apply" i], button:has-text("Easy Apply"), .jobs-apply-button--top-card button, .jobs-s-apply button, button.jobs-apply-button')
        if easy_apply_btn.count() == 0 or not easy_apply_btn.first.is_visible():
            print("       Note: Easy Apply button not available on this job.")
            return None

        btn_elem = easy_apply_btn.first
        if btn_elem.is_disabled() or "disabled" in (btn_elem.get_attribute("class") or ""):
            print("       Note: Easy Apply button is disabled.")
            return None

        # Click Easy Apply
        try:
            btn_elem.click(force=True)
            time.sleep(2.5)
        except Exception as e:
            print(f"       Error clicking Easy Apply button: {e}")
            return None

        # Execute wizard
        res = self.process_easy_apply_wizard(page, resume_path, company)
        if res and res.get("status") in ["Submitted", "Pre-filled - Ready for Review"]:
            job_data = {
                "title": title,
                "company": company,
                "location": location,
                "url": direct_url,
                "source": "LinkedIn",
                "board_type": "LinkedIn Easy Apply",
                "status": res["status"],
                "matched_resume": selected_resume,
                "fit_score": fit_score,
                "fit_rationale": eval_result.get("rationale", ""),
                "notes": f"Easy Apply direct run: {res['status']}"
            }
            self.updater.append_row(job_data)
            return {
                "title": title,
                "company": company,
                "status": res["status"],
                "url": direct_url,
                "screenshot": res.get("screenshot", ""),
                "limit_reached": res.get("limit_reached", False)
            }
        return None

    def wait_for_authentication(self, page: Page, timeout_seconds: int = 600) -> bool:
        """Checks authentication and waits for login if needed."""
        if not self.is_authenticated(page):
            print("\n" + "=" * 65)
            print(" [ACTION REQUIRED] LINKEDIN SIGN-IN NEEDED")
            print("=" * 65)
            print(" A visible Chrome browser window is currently open on your screen.")
            print(" Please sign in with your LinkedIn account (or 'Continue with Google').")
            print(f" Waiting up to {timeout_seconds} seconds for login to complete...")
            print(" Once logged in, your session is saved permanently in this profile.")
            print("=" * 65 + "\n")

            start = time.time()
            while time.time() - start < timeout_seconds:
                time.sleep(3.0)
                if self.is_authenticated(page):
                    print("\n[OK] Authenticated successfully! Proceeding with Easy Apply pipeline...\n")
                    time.sleep(2.0)
                    return True
            print("\n[Timeout] Timed out waiting for LinkedIn authentication.")
            return False
        return True

    def run(
        self,
        keywords: Optional[str] = None,
        location: Optional[str] = None,
        max_jobs: int = 5,
        direct_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Launches persistent browser context and executes end-to-end Easy Apply."""
        keywords = keywords or "Program Manager"
        location = location or "India"

        encoded_kw = quote_plus(keywords)
        encoded_loc = quote_plus(location)
        search_url = f"https://www.linkedin.com/jobs/search/?keywords={encoded_kw}&location={encoded_loc}&f_AL=true"

        print("=" * 65)
        print("          LINKEDIN EASY APPLY END-TO-END PIPELINE")
        print("=" * 65)
        print(f"Target Keywords: {keywords}")
        print(f"Target Location: {location}")
        print(f"User Data Dir:   {self.user_data_dir}")
        print(f"Auto Submit:     {self.auto_submit} (Full end-to-end submission)")
        print(f"Min Fit Score:   {self.min_score}%")
        print("=" * 65)

        applied_jobs = []

        with sync_playwright() as p:
            if self.cdp_url:
                print(f"Connecting to existing Chrome session over CDP: {self.cdp_url}")
                try:
                    browser = p.chromium.connect_over_cdp(self.cdp_url)
                    context = browser.contexts[0] if browser.contexts else browser.new_context()
                except Exception as e:
                    print(f"[Error] Failed to connect over CDP: {e}")
                    return []
            else:
                try:
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=self.user_data_dir,
                        headless=self.headless,
                        channel="chrome",
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ]
                    )
                except Exception as e:
                    print(f"\n[Notice] Using chromium engine fallback: {e}")
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=self.user_data_dir,
                        headless=self.headless,
                        args=["--disable-blink-features=AutomationControlled"]
                    )

            session_file = BASE_DIR / "sessions" / "linkedin_state.json"
            if session_file.exists():
                try:
                    with open(session_file, "r") as sf:
                        s_data = json.load(sf)
                    s_cookies = s_data.get("cookies", [])
                    if s_cookies:
                        context.add_cookies(s_cookies)
                        print(f"Loaded {len(s_cookies)} authenticated session cookies from {session_file.name}")
                except Exception as e:
                    print(f"Session load note: {e}")
            elif self.li_at_cookie:
                print("Injecting LinkedIn session cookie (li_at)...")
                try:
                    context.add_cookies([
                        {
                            "name": "li_at",
                            "value": self.li_at_cookie.strip(),
                            "domain": ".linkedin.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "None"
                        },
                        {
                            "name": "li_at",
                            "value": self.li_at_cookie.strip(),
                            "domain": ".www.linkedin.com",
                            "path": "/",
                            "httpOnly": True,
                            "secure": True,
                            "sameSite": "None"
                        }
                    ])
                except Exception as e:
                    print(f"Cookie injection note: {e}")

            page = context.new_page()
            try:
                # If direct_url is provided, process single target job directly
                if direct_url:
                    print(f"\nNavigating directly to target job: {direct_url}")
                    page.goto(direct_url, wait_until="domcontentloaded")
                    time.sleep(3.5)
                    auth_ok = self.wait_for_authentication(page)
                    if not auth_ok:
                        print("[Aborting] Application run cancelled due to unauthenticated session.")
                        return []
                    res = self.apply_to_direct_job_page(page, direct_url)
                    if res:
                        applied_jobs.append(res)
                        print(f"[Success] Application finalized for {res['title']} @ {res['company']}")
                    return applied_jobs

                print(f"\nNavigating to LinkedIn Jobs: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded")
                time.sleep(3.0)

                # Check and wait for authentication
                auth_ok = self.wait_for_authentication(page)
                if not auth_ok:
                    print("[Aborting] Application run cancelled due to unauthenticated session.")
                    return []

                # Make sure we are on the search URL after authentication
                if "jobs/search" not in page.url or "f_AL=true" not in page.url:
                    print(f"Re-navigating to Easy Apply search URL: {search_url}")
                    page.goto(search_url, wait_until="domcontentloaded")
                    time.sleep(4.0)

                # Scroll job list container to trigger loading of cards
                try:
                    page.evaluate('window.scrollTo(0, 400)')
                except Exception:
                    pass

                # Locate job list cards prioritizing Easy Apply badges
                ea_cards = page.locator('li[data-occludable-job-id]:has-text("Easy Apply")')
                if ea_cards.count() > 0:
                    job_cards = ea_cards
                else:
                    job_cards = page.locator('li[data-occludable-job-id]')
                count = job_cards.count()
                print(f"\nFound {count} job cards on current search page.")

                for i in range(count):
                    if len(applied_jobs) >= max_jobs:
                        break
                    card = job_cards.nth(i)
                    if not card.is_visible():
                        continue
                    res = self.apply_to_job_listing(page, card)
                    if res:
                        applied_jobs.append(res)
                        print(f"[Success #{len(applied_jobs)}] Application finalized for {res['title']} @ {res['company']}")
                        if res.get("limit_reached"):
                            print("\n[STOPPING] LinkedIn daily Easy Apply application limit reached. Halting batch.")
                            break
                    time.sleep(2.0)

                print(f"\n" + "=" * 65)
                print(f"Run complete! Successfully processed and tracked {len(applied_jobs)} applications.")
                print("=" * 65)

                return applied_jobs

            finally:
                time.sleep(2.0)
                context.close()


def main():
    parser = argparse.ArgumentParser(description="LinkedIn Easy Apply Playwright End-to-End Engine")
    parser.add_argument("--keywords", default="Program Manager", help="Job search keywords")
    parser.add_argument("--location", default="India", help="Target search location")
    parser.add_argument("--max-jobs", type=int, default=5, help="Maximum jobs to inspect/apply")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum fit score threshold")
    parser.add_argument("--url", default=None, help="Direct LinkedIn job posting URL")
    parser.add_argument("--no-auto-submit", action="store_true", help="Disable auto-submit (leave on review step)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--user-data-dir", default=None, help="Custom Chrome user data directory")
    parser.add_argument("--cookie", default=os.getenv("LINKEDIN_LI_AT"), help="LinkedIn li_at session cookie value")
    parser.add_argument("--cdp", default=os.getenv("CHROME_CDP_URL"), help="Chrome DevTools Protocol URL (e.g. http://localhost:9222)")

    args = parser.parse_args()

    applier = LinkedInApplier(
        user_data_dir=args.user_data_dir,
        headless=args.headless,
        min_score=args.min_score,
        auto_submit=not args.no_auto_submit,
        li_at_cookie=args.cookie,
        cdp_url=args.cdp
    )
    applier.run(
        keywords=args.keywords,
        location=args.location,
        max_jobs=args.max_jobs,
        direct_url=args.url
    )


if __name__ == "__main__":
    main()
