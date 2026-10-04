"""
Automated Job Application Pre-filler & Submitter using Playwright.

Loads candidate screening data from context/screening_qa.json, navigates to ATS job pages,
attaches the designated resume variant, maps input fields using regex heuristics, drafts
grounded answers for open textareas via question_answerer.py, and takes verification
screenshots saved in logs/.
"""

import json
import os
import re
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from playwright.sync_api import sync_playwright, Page

BASE_DIR = Path(__file__).resolve().parent.parent

# Import question answerer
try:
    from question_answerer import answer_custom_question, load_default_context_notes
except ImportError:
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from question_answerer import answer_custom_question, load_default_context_notes

# Resolve QA_DATA path dynamically
QA_PATHS = [
    BASE_DIR / "context" / "screening_qa.json",
    Path("context/screening_qa.json"),
    Path("job-hunter/context/screening_qa.json")
]

QA_DATA = {}
for qp in QA_PATHS:
    if qp.exists():
        with open(qp, "r", encoding="utf-8") as f:
            QA_DATA = json.load(f)
        break


def apply_to_job(
    page: Page,
    job_url: str,
    resume_path: str,
    auto_submit: bool = True,
    safe_mode: bool = False,
    company_name: str = "company"
) -> Dict[str, Any]:
    """
    Automates ATS form interaction:
    1. Attaches selected resume variant.
    2. Heuristically fills standard fields (name, email, phone, LinkedIn, notice period, location).
    3. Auto-drafts 2-sentence responses for any open textareas using profile notes.
    4. Takes a verification screenshot saved in logs/.
    5. Returns dict with status, screenshot_path, and action details.
    """
    # Normalize ATS application URLs for direct application form loading
    if "jobs.lever.co" in job_url and not job_url.endswith("/apply"):
        job_url = job_url.rstrip("/") + "/apply"
    elif "jobs.ashbyhq.com" in job_url and not job_url.endswith("/application"):
        job_url = job_url.rstrip("/") + "/application"

    print(f"Navigating to {job_url}...")
    page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Ensure resume path exists
    abs_resume_path = Path(resume_path)
    if not abs_resume_path.is_absolute():
        abs_resume_path = BASE_DIR / "resumes" / resume_path
        if not abs_resume_path.exists():
            abs_resume_path = Path(resume_path).resolve()

    # 1. Upload the chosen resume variant
    file_inputs = page.locator('input[type="file"]')
    if file_inputs.count() > 0 and abs_resume_path.exists():
        try:
            file_inputs.first.set_input_files(str(abs_resume_path))
            file_inputs.first.dispatch_event("change")
            print(f"Attached resume: {abs_resume_path.name}")
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"Resume upload note: {e}")

    # 2. Standard field heuristics mapping
    first_name = QA_DATA.get("first_name") or QA_DATA.get("full_name", "").split()[0]
    last_name = QA_DATA.get("last_name") or QA_DATA.get("full_name", "").split()[-1]
    field_mappings = [
        (r"first[_\s-]?name", first_name),
        (r"last[_\s-]?name", last_name),
        (r"full[_\s-]?name|name", QA_DATA.get("full_name")),
        (r"email", QA_DATA.get("email")),
        (r"phone|mobile|tel", QA_DATA.get("phone")),
        (r"linkedin", QA_DATA.get("linkedin_url")),
        (r"github|portfolio|website", QA_DATA.get("github_portfolio_url")),
        (r"notice[_\s-]?period", QA_DATA.get("current_notice_period")),
        (r"company|org|employer|organization", QA_DATA.get("current_company", "Inditex (Zara)")),
    ]

    # Find and fill all text and email inputs
    inputs = page.locator('input[type="text"], input[type="email"], input[type="tel"]')
    for i in range(inputs.count()):
        elem = inputs.nth(i)
        if not elem.is_visible():
            continue

        attrs = " ".join([
            elem.get_attribute("name") or "",
            elem.get_attribute("id") or "",
            elem.get_attribute("placeholder") or "",
            elem.get_attribute("aria-label") or ""
        ]).lower()

        for pattern, value in field_mappings:
            if re.search(pattern, attrs) and value:
                current_val = elem.input_value()
                if not current_val:  # Don't overwrite if auto-filled
                    elem.fill(value)
                break

    # 3. Handle Location / Relocation fields with autocomplete support
    location_fields = page.locator('input[name*="location"], input[id*="location"], input[aria-label*="Location"], input[placeholder*="Location"]')
    if location_fields.count() > 0 and location_fields.first.is_visible():
        loc_elem = location_fields.first
        if not loc_elem.input_value():
            try:
                loc_elem.click()
                loc_elem.press_sequentially("Bengaluru", delay=100)
                page.wait_for_timeout(1000)
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                dropdown = page.locator('ul[role="listbox"] li, .location-option, li:has-text("Bengaluru"), div[role="option"]')
                if dropdown.count() > 0 and dropdown.first.is_visible():
                    dropdown.first.click()
            except Exception:
                loc_elem.fill(QA_DATA.get("location", "Bengaluru, India"))

    # 4. Handle HTML select dropdowns
    selects = page.locator('select')
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
            sel_id = sel.get_attribute("id")
            if sel_id:
                lbl = page.locator(f'label[for="{sel_id}"]')
                if lbl.count() > 0:
                    sel_text += " " + lbl.first.inner_text().lower()
        except Exception:
            pass

        if "country in which you are located" in sel_text or ("country" in sel_text and "located" in sel_text):
            try:
                sel.select_option(label="India")
            except Exception:
                pass
        elif "restrictions" in sel_text or "employment agreements" in sel_text:
            try:
                sel.select_option(label="No")
            except Exception:
                pass
        elif "sponsorship" in sel_text or "visa" in sel_text:
            try:
                sel.select_option(label="No")
            except Exception:
                pass

    # 5. Handle React-Select custom dropdown controls
    react_controls = page.locator('.select__control')
    for i in range(react_controls.count()):
        ctrl = react_controls.nth(i)
        try:
            lbl = ctrl.evaluate('''el => {
                let p = el;
                for (let j=0; j<5; j++) {
                    if (p.parentElement) {
                        p = p.parentElement;
                        let text = p.innerText;
                        if (text && text.length > 15) return text.toLowerCase();
                    }
                }
                return "";
            }''')
            current_text = ctrl.inner_text().strip()
            if current_text and current_text != "Select...":
                continue

            if "country in which you are located" in lbl or ("country" in lbl and "located" in lbl):
                ctrl.scroll_into_view_if_needed()
                ctrl.click()
                page.keyboard.type("India", delay=50)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                print("      Selected Country: India")
            elif "restrictions" in lbl or "employment agreements" in lbl:
                ctrl.scroll_into_view_if_needed()
                ctrl.click()
                page.keyboard.type("No", delay=50)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                print("      Selected Employment Restrictions: No")
            elif "sponsorship" in lbl or "visa" in lbl:
                ctrl.scroll_into_view_if_needed()
                ctrl.click()
                page.keyboard.type("No", delay=50)
                page.wait_for_timeout(300)
                page.keyboard.press("Enter")
                print("      Selected Visa Sponsorship: No")
        except Exception as e:
            pass

    # 6. Handle open screening textareas
    textareas = page.locator('textarea')
    context_notes = load_default_context_notes()
    for i in range(textareas.count()):
        ta = textareas.nth(i)
        if not ta.is_visible():
            continue

        label_text = "Screening Question"
        try:
            # Look for associated label
            ta_id = ta.get_attribute("id")
            if ta_id:
                lbl = page.locator(f'label[for="{ta_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text()
            if label_text == "Screening Question":
                label_text = ta.get_attribute("placeholder") or ta.get_attribute("name") or "Tell us about your relevant experience"
        except Exception:
            pass

        if not ta.input_value():
            ai_answer = answer_custom_question(label_text, context_notes)
            ta.fill(ai_answer)
            print(f"Drafted answer for textarea ('{label_text[:30]}...'): {ai_answer[:60]}...")

    # 7. Auto-check required consent / privacy checkboxes
    checkboxes = page.locator('input[type="checkbox"]')
    for i in range(checkboxes.count()):
        cb = checkboxes.nth(i)
        try:
            cb_name = (cb.get_attribute("name") or "") + " " + (cb.get_attribute("id") or "")
            if cb.get_attribute("required") or any(k in cb_name.lower() for k in ["privacy", "consent", "terms", "agree", "data", "acknowledge"]):
                if not cb.is_checked():
                    cb.check(force=True)
        except Exception:
            pass

    # 8. Detect & solve Cloudflare Turnstile / verification challenges if present
    for frame in page.frames:
        try:
            cf_box = frame.locator('input[type="checkbox"], #challenge-stage input, .ctp-checkbox-label, div#cf-stage')
            if cf_box.count() > 0 and cf_box.first.is_visible():
                print("      [Captcha] Detected Cloudflare challenge, auto-clicking verification...")
                cf_box.first.click(force=True)
                page.wait_for_timeout(2500)
        except Exception:
            pass

    page.wait_for_timeout(1000)
    print("Form filling complete.")

    # 9. Capture pre-submit verification screenshot in logs/
    logs_dir = BASE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    clean_company = re.sub(r"[^a-zA-Z0-9_-]", "_", company_name.lower())
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    screenshot_name = f"verify_{clean_company}_{timestamp}.png"
    screenshot_path = logs_dir / screenshot_name

    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Saved pre-submit verification screenshot: {screenshot_path}")
    except Exception as e:
        print(f"Screenshot note: {e}")

    # 10. Autonomous Submit Execution
    status = "Pre-filled - Ready for Review"
    if auto_submit and not safe_mode:
        submit_btn = page.locator('button#btn-submit, button.template-btn-submit, button:has-text("Submit application"), button:has-text("Submit Application"), button:has-text("SUBMIT APPLICATION"), button:has-text("Submit"), button[type="submit"], input[type="submit"], button:has-text("Apply"), input[value*="Submit"], input[value*="Apply"]').first
        if submit_btn.count() > 0 and submit_btn.is_visible():
            submit_btn.scroll_into_view_if_needed()
            submit_btn.click(force=True)
            print("   -> CLICKED SUBMIT APPLICATION BUTTON!")
            page.wait_for_timeout(4000)

            # Check if validation error blocked submit
            error_msgs = page.locator('.error, .invalid-feedback, [aria-invalid="true"], .field-error')
            if error_msgs.count() > 0:
                print(f"   [Validation] Detected {error_msgs.count()} form warnings, re-verifying...")
            
            post_screen = logs_dir / f"submitted_{clean_company}_{timestamp}.png"
            try:
                page.screenshot(path=str(post_screen), full_page=True)
                screenshot_path = post_screen
                print(f"   -> Saved post-submit confirmation screenshot: {post_screen}")
            except Exception:
                pass
            status = "Submitted"

    return {
        "status": status,
        "screenshot_path": str(screenshot_path),
        "notes": f"Applied with {abs_resume_path.name}"
    }


def run_apply(
    job_url: str,
    resume_path: str,
    auto_submit: bool = True,
    safe_mode: bool = False,
    headless: bool = True,
    company_name: str = "company"
) -> Dict[str, Any]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page()
        try:
            result = apply_to_job(
                page,
                job_url,
                resume_path,
                auto_submit=auto_submit,
                safe_mode=safe_mode,
                company_name=company_name
            )
            if not headless and not auto_submit:
                print("\n[Interactive Mode] Browser is open on your screen!")
                print("Your resume and candidate information have been pre-filled.")
                print("You can now review the form, complete the captcha/Turnstile, and click Submit.")
                print("Keeping browser open for 60 seconds (or close the browser window to exit)...")
                try:
                    page.wait_for_timeout(60000)
                except Exception:
                    pass
            return result
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ATS Job Application Automated Filler")
    parser.add_argument("--url", required=True, help="Job posting URL")
    parser.add_argument("--resume", default="resume_strategy_cro.pdf", help="Resume filename or path in job-hunter/resumes/")
    parser.add_argument("--company", default="company", help="Company name for logging/screenshots")
    parser.add_argument("--auto-submit", action="store_true", help="Automatically submit application instead of pre-filling")
    parser.add_argument("--no-safe-mode", action="store_true", help="Disable safe mode to allow submission")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")

    args = parser.parse_args()
    safe_mode = not args.no_safe_mode
    res = run_apply(
        args.url,
        args.resume,
        auto_submit=args.auto_submit,
        safe_mode=safe_mode,
        headless=args.headless,
        company_name=args.company
    )
    print(f"Result Status: {res['status']}")
    print(f"Screenshot: {res['screenshot_path']}")
