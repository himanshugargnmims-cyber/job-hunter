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
        """Determines if the current page has an active authenticated LinkedIn session."""
        try:
            curr_url = page.url.lower()
            if any(k in curr_url for k in ["/uas/login", "/checkpoint", "/signup", "session_redirect"]):
                return False

            title_lower = page.title().lower()
            if any(k in title_lower for k in ["sign up", "sign in", "login", "log in", "join linkedin"]):
                return False

            # Check for unauthenticated signup/login form elements
            has_login_form = page.locator('input[autocomplete="username"], input[name="session_key"], button:has-text("Agree & Join"), a:has-text("Sign in")').count() > 0
            has_auth_nav = page.locator('#global-nav, nav.global-nav, .global-nav__me, button.global-nav__primary-link').count() > 0

            if has_auth_nav:
                return True
            if has_login_form:
                return False

            # Check if job search cards are rendered
            has_cards = page.locator('.jobs-search-results-list, .job-card-container, [data-occludable-job-id]').count() > 0
            if has_cards:
                return True

            return False
        except Exception:
            return False

    def fill_form_fields(self, page: Page, modal, resume_path: str):
        """Fills standard inputs, dropdowns, radios, and textareas inside the Easy Apply modal."""
        # 1. Resume upload if an input file is present and needs a file
        file_inputs = modal.locator('input[type="file"]')
        if file_inputs.count() > 0 and Path(resume_path).exists():
            try:
                file_inputs.first.set_input_files(str(resume_path))
                print(f"      [File] Attached resume: {Path(resume_path).name}")
                time.sleep(1.0)
            except Exception as e:
                pass

        # If LinkedIn provides selectable pre-uploaded resumes, select the first or matching one
        resume_radios = modal.locator('input[type="radio"][id*="jobsDocumentCard"], input[type="radio"][name*="resume"]')
        if resume_radios.count() > 0:
            checked_count = sum(1 for i in range(resume_radios.count()) if resume_radios.nth(i).is_checked())
            if checked_count == 0:
                try:
                    rad_id = resume_radios.first.get_attribute("id")
                    if rad_id:
                        lbl = modal.locator(f'label[for="{rad_id}"]')
                        if lbl.count() > 0:
                            lbl.first.click(force=True)
                        else:
                            resume_radios.first.click(force=True)
                    else:
                        resume_radios.first.click(force=True)
                except Exception:
                    pass
                time.sleep(0.5)

        # 2. Text / Tel / Email / Number fields
        text_inputs = modal.locator('input[type="text"], input[type="tel"], input[type="email"], input[type="number"]')
        for i in range(text_inputs.count()):
            elem = text_inputs.nth(i)
            if not elem.is_visible():
                continue

            attrs = " ".join([
                elem.get_attribute("name") or "",
                elem.get_attribute("id") or "",
                elem.get_attribute("placeholder") or "",
                elem.get_attribute("aria-label") or ""
            ]).lower()

            elem_id = elem.get_attribute("id")
            label_text = ""
            if elem_id:
                lbl = modal.locator(f'label[for="{elem_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text().lower()

            parent_text = ""
            try:
                parent_text = elem.evaluate('''e => {
                    let p = e.closest(".fb-form-element, .jobs-easy-apply-form-section__grouping, div");
                    return p ? p.innerText.toLowerCase() : "";
                }''')
            except Exception:
                pass
            combined_desc = attrs + " " + label_text + " " + parent_text
            current_val = elem.input_value().strip()

            # Phone number
            if any(k in combined_desc for k in ["phone", "mobile", "tel"]):
                _phone_digits = re.sub(r"\D", "", QA_DATA.get("phone", "5550100"))
                if not current_val:
                    elem.fill(_phone_digits[-10:] if len(_phone_digits) >= 10 else _phone_digits)
            # Email
            elif "email" in combined_desc:
                if not current_val:
                    elem.fill(QA_DATA.get("email", "candidate@example.com"))
            # First name
            elif "first name" in combined_desc or "given name" in combined_desc:
                if not current_val:
                    elem.fill(QA_DATA.get("first_name", QA_DATA.get("full_name", "Alex Taylor").split()[0]))
            # Last name
            elif "last name" in combined_desc or "family name" in combined_desc:
                if not current_val:
                    _parts = QA_DATA.get("full_name", "Alex Taylor").split()
                    elem.fill(QA_DATA.get("last_name", _parts[-1] if len(_parts) > 1 else ""))
            # Notice period
            elif any(k in combined_desc for k in ["notice", "days", "period"]):
                if not current_val:
                    elem.fill(str(QA_DATA.get("current_notice_period", "30")))
            # Income / Salary / Compensation
            elif any(k in combined_desc for k in ["expected", "desired", "target"]) and any(k in combined_desc for k in ["income", "salary", "ctc", "compensation"]):
                if not current_val:
                    elem.fill(str(QA_DATA.get("screening_answers", {}).get("expected_ctc", QA_DATA.get("expected_ctc", "5000000"))))
            elif any(k in combined_desc for k in ["current"]) and any(k in combined_desc for k in ["income", "salary", "ctc", "compensation"]):
                if not current_val:
                    elem.fill(str(QA_DATA.get("screening_answers", {}).get("current_ctc", QA_DATA.get("current_ctc", "4000000"))))
            elif any(k in combined_desc for k in ["income", "salary", "ctc", "compensation"]):
                if not current_val:
                    elem.fill(str(QA_DATA.get("screening_answers", {}).get("expected_ctc", QA_DATA.get("expected_ctc", "5000000"))))
            # Years of experience (numeric or text)
            elif any(k in combined_desc for k in ["how many years", "years of experience", "years"]):
                if not current_val:
                    elem.fill(str(QA_DATA.get("screening_answers", {}).get("total_years_experience", QA_DATA.get("total_years_exp", "5"))))
            # City / Location
            elif any(k in combined_desc for k in ["city", "location", "address"]):
                if not current_val:
                    elem.fill(QA_DATA.get("location", "Remote"))
                    time.sleep(0.5)
                    suggestions = modal.locator('.jobs-easy-apply-form-element__typeahead-results li, div[role="option"]')
                    if suggestions.count() > 0:
                        try:
                            suggestions.first.click()
                        except Exception:
                            pass
            # LinkedIn URL / Website
            elif any(k in combined_desc for k in ["linkedin", "profile"]):
                if not current_val:
                    elem.fill(QA_DATA.get("linkedin_url", ""))
            # Current Company
            elif any(k in combined_desc for k in ["company", "current employer"]):
                if not current_val:
                    elem.fill(QA_DATA.get("screening_answers", {}).get("current_company", QA_DATA.get("current_company", "")))
            # Current Title
            elif any(k in combined_desc for k in ["title", "designation"]):
                if not current_val:
                    elem.fill(QA_DATA.get("screening_answers", {}).get("current_title", QA_DATA.get("current_title", "")))
            # Numeric general fallback
            elif elem.get_attribute("type") == "number" or elem.get_attribute("inputmode") == "numeric" or "-numeric" in (elem.get_attribute("id") or ""):
                if not current_val:
                    if any(k in combined_desc for k in ["income", "salary", "ctc", "compensation"]):
                        elem.fill("5500000")
                    else:
                        elem.fill("9")
            elif elem.get_attribute("required") or elem.get_attribute("aria-required") == "true":
                if not current_val:
                    elem.fill("Yes")

        # 3. Handle Select Dropdowns
        selects = modal.locator('select')
        for i in range(selects.count()):
            sel = selects.nth(i)
            if not sel.is_visible():
                continue
            sel_text = " ".join([
                sel.get_attribute("name") or "",
                sel.get_attribute("id") or "",
                sel.get_attribute("aria-label") or ""
            ]).lower()

            try:
                options = sel.locator('option')
                opt_texts = [options.nth(j).inner_text().strip() for j in range(options.count())]

                if any(k in sel_text for k in ["phone", "country code"]):
                    for opt in opt_texts:
                        if "india" in opt.lower() or "+91" in opt:
                            sel.select_option(label=opt)
                            break
                elif any(k in sel_text for k in ["veteran"]):
                    for opt in opt_texts:
                        if any(k in opt.lower() for k in ["not a protected", "not a", "i am not", "no"]):
                            sel.select_option(label=opt)
                            break
                elif any(k in sel_text for k in ["disability"]):
                    for opt in opt_texts:
                        if any(k in opt.lower() for k in ["no, i do not", "don't have", "no", "decline"]):
                            sel.select_option(label=opt)
                            break
                elif any(k in sel_text for k in ["gender"]):
                    for opt in opt_texts:
                        if opt.lower() in ["male", "man"]:
                            sel.select_option(label=opt)
                            break
                elif any(k in sel_text for k in ["race", "ethnicity"]):
                    for opt in opt_texts:
                        if any(k in opt.lower() for k in ["south asian", "asian"]) and not any(k in opt.lower() for k in ["american indian", "east asian"]):
                            sel.select_option(label=opt)
                            break
                elif any(k in sel_text for k in ["sponsorship", "visa"]):
                    for opt in opt_texts:
                        if opt.lower() == "no":
                            sel.select_option(label=opt)
                            break
                elif any("yes" == o.lower() for o in opt_texts):
                    if "sponsorship" in sel_text or "visa" in sel_text:
                        sel.select_option(label="No")
                    else:
                        sel.select_option(label="Yes")
                elif any(k in [o.lower() for o in opt_texts] for k in ["professional", "expert", "advanced"]):
                    for opt in opt_texts:
                        if any(k in opt.lower() for k in ["professional", "expert", "advanced"]):
                            sel.select_option(label=opt)
                            break
                elif len(opt_texts) > 1:
                    sel.select_option(index=1)
            except Exception:
                pass

        # 4. Radio buttons (Fieldsets)
        radios = modal.locator('fieldset')
        for i in range(radios.count()):
            fs = radios.nth(i)
            fs_text = fs.inner_text().lower()

            try:
                if any(k in fs_text for k in ["veteran", "military"]):
                    no_opt = fs.locator('label:has-text("not a protected"), label:has-text("I am not"), label:has-text("No"), input[value*="not"] + label, input[value="No"] + label')
                    if no_opt.count() > 0:
                        no_opt.first.click(force=True)
                elif any(k in fs_text for k in ["disability"]):
                    no_opt = fs.locator('label:has-text("No, I do not"), label:has-text("No"), label:has-text("Decline"), input[value*="No"] + label')
                    if no_opt.count() > 0:
                        no_opt.first.click(force=True)
                elif any(k in fs_text for k in ["gender"]):
                    male_opt = fs.locator('label:has-text("Male"), label:has-text("Man")')
                    if male_opt.count() > 0:
                        male_opt.first.click(force=True)
                elif any(k in fs_text for k in ["race", "ethnicity"]):
                    asian_opt = fs.locator('label:has-text("Asian"), label:has-text("South Asian")')
                    if asian_opt.count() > 0:
                        asian_opt.first.click(force=True)
                elif "require sponsorship" in fs_text or "require visa" in fs_text or "sponsorship now or in the future" in fs_text:
                    no_opt = fs.locator('label:has-text("No"), input[value="No"] + label, input[value="0"] + label')
                    if no_opt.count() > 0:
                        no_opt.first.click(force=True)
                elif any(k in fs_text for k in ["authorized to work", "legally authorized", "authorization"]):
                    yes_opt = fs.locator('label:has-text("Yes"), input[value="Yes"] + label, input[value="1"] + label')
                    if yes_opt.count() > 0:
                        yes_opt.first.click(force=True)
                elif any(k in fs_text for k in ["conflict", "felony", "criminal", "investigation"]):
                    no_opt = fs.locator('label:has-text("No"), input[value="No"] + label')
                    if no_opt.count() > 0:
                        no_opt.first.click(force=True)
                elif any(k in fs_text for k in ["commute", "relocate", "willing to"]):
                    yes_opt = fs.locator('label:has-text("Yes"), input[value="Yes"] + label, input[value="1"] + label')
                    if yes_opt.count() > 0:
                        yes_opt.first.click(force=True)
                else:
                    yes_opt = fs.locator('label:has-text("Yes"), input[value="Yes"] + label')
                    if yes_opt.count() > 0:
                        yes_opt.first.click(force=True)
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

    def process_easy_apply_wizard(self, page: Page, resume_path: str, company: str = "Company") -> Dict[str, Any]:
        """Walks through multi-step Easy Apply dialog modal and clicks Submit."""
        modal = page.locator('.jobs-easy-apply-modal, div[role="dialog"]:has-text("Easy Apply")')
        if modal.count() == 0:
            return {"status": "Failed to open modal", "screenshot": ""}

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

                    # Dismiss any post-submit confirmation modal
                    dismiss_btn = page.locator('button[aria-label="Dismiss"], button:has-text("Done"), button[data-test-modal-close-btn]')
                    if dismiss_btn.count() > 0:
                        try:
                            dismiss_btn.first.click(force=True)
                        except Exception:
                            pass

                    return {
                        "status": "Submitted",
                        "screenshot": str(submitted_screen)
                    }
                else:
                    return {
                        "status": "Pre-filled - Ready for Review",
                        "screenshot": ""
                    }

            # Check for Review button
            review_btn = modal.locator('button[aria-label="Review your application"], button:has-text("Review"), footer button:has-text("Review")')
            if review_btn.count() > 0 and review_btn.first.is_visible():
                print("   -> Clicking Review button...")
                review_btn.first.click(force=True)
                time.sleep(1.5)

                # Check if validation error blocked Review
                error_msgs = modal.locator('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]')
                if error_msgs.count() > 0:
                    print(f"   -> Handled {error_msgs.count()} validation warnings on review step, attempting fix...")
                    self.fill_form_fields(page, modal, resume_path)
                    time.sleep(0.5)
                    review_btn.first.click(force=True)
                continue

            # Check for Next button
            next_btn = modal.locator('button[aria-label="Continue to next step"], button:has-text("Next"), footer button:has-text("Next")')
            if next_btn.count() > 0 and next_btn.first.is_visible():
                print("   -> Clicking Next button...")
                next_btn.first.click(force=True)
                time.sleep(1.5)

                # Check if validation error prevents proceeding
                error_msgs = modal.locator('.artdeco-inline-feedback--error, [data-test-form-element-error-messages]')
                if error_msgs.count() > 0:
                    print(f"   -> Handled {error_msgs.count()} validation warnings, attempting fix...")
                    self.fill_form_fields(page, modal, resume_path)
                    time.sleep(0.5)
                    next_btn.first.click(force=True)
                continue

            break

        # If modal could not be submitted, dismiss it cleanly so next card can be processed
        try:
            dismiss_btn = modal.locator('button[aria-label="Dismiss"], button.artdeco-modal__dismiss').first
            if dismiss_btn.is_visible():
                dismiss_btn.click()
                time.sleep(1.0)
                discard_btn = page.locator('button[data-control-name="discard_application_confirm_btn"], button:has-text("Discard")').first
                if discard_btn.is_visible():
                    discard_btn.click()
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

            desc_elem = page.locator('#job-details, .jobs-description__content, .jobs-box__html-content')
            description = desc_elem.first.inner_text().strip() if desc_elem.count() > 0 else f"{title} at {company}"

            # Evaluate fit score
            eval_result = self.selector.evaluate_fit(title, description)
            fit_score = eval_result["fit_score"]
            selected_resume = eval_result["selected_resume"]
            rationale = eval_result["rationale"]

            print(f"\n[Card] {title} @ {company} ({location})")
            print(f"       Fit Score: {fit_score}% (Min: {self.min_score}%) -> {selected_resume}")

            if fit_score < self.min_score:
                print(f"       Skipping: score {fit_score}% < threshold {self.min_score}%")
                return None

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
                "screenshot": screenshot_path
            }
        except Exception as e:
            print(f"       Error processing job: {e}")
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
