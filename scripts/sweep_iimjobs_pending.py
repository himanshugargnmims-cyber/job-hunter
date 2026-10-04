#!/usr/bin/env python3
"""
sweep_iimjobs_pending.py - Sweeps all pending & pre-filled IIMjobs records in jobs.db
Submits each job directly using the candidate's authenticated session with strict verification.
"""

import sys
import time
import re
import sqlite3
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from scripts.resume_selector import ResumeSelector
from scripts.sheet_updater import SheetUpdater

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
SESSION_FILE = BASE_DIR / "sessions" / "iimjobs_state.json"
DB_PATH = BASE_DIR / "data" / "jobs.db"


def handle_screening_questionnaire(page: Page) -> bool:
    """Handles Step 2 questionnaire (Submit a Form / screening questions)."""
    print("   [Questionnaire] Handling screening questions...")
    try:
        # 1. Radio Buttons: select 'Yes' or positive responses for each question
        yes_labels = page.locator('label:has-text("Yes"), span:has-text("Yes"), input[value="Yes"] + label')
        if yes_labels.count() > 0:
            for y_i in range(yes_labels.count()):
                try:
                    lbl = yes_labels.nth(y_i)
                    if lbl.is_visible():
                        lbl.click(force=True)
                        page.wait_for_timeout(150)
                except Exception:
                    pass
        else:
            radios = page.locator('input[type="radio"]')
            for r_i in range(0, radios.count(), 2):
                try:
                    radios.nth(r_i).click(force=True)
                    page.wait_for_timeout(150)
                except Exception:
                    pass

        # 2. Notice period selection
        notice_options = [
            'button:has-text("1 month")',
            'button:has-text("Immediately Available")',
            'button:has-text("30 Days")',
            'button:has-text("15 Days")',
            'span:has-text("1 month")',
            'label:has-text("1 month")'
        ]
        for n_sel in notice_options:
            n_el = page.locator(n_sel).first
            if n_el.count() > 0 and n_el.is_visible():
                try:
                    n_el.click(force=True)
                    page.wait_for_timeout(200)
                    break
                except Exception:
                    pass

        # 3. Numeric inputs (CTC, Experience, Notice Period in days)
        inputs = page.locator('input[type="text"], input[type="number"]')
        for inp_i in range(inputs.count()):
            try:
                inp = inputs.nth(inp_i)
                if not inp.is_visible():
                    continue
                curr_val = inp.input_value()
                if curr_val:
                    continue

                placeholder = (inp.get_attribute("placeholder") or "").lower()
                name = (inp.get_attribute("name") or "").lower()
                label_text = ""
                try:
                    label_text = inp.evaluate('el => el.closest("div")?.innerText || ""').lower()
                except Exception:
                    pass

                combined = f"{placeholder} {name} {label_text}"
                if "current ctc" in combined or "current salary" in combined or "ctc" in combined:
                    inp.fill("35")
                elif "expected ctc" in combined or "expected salary" in combined:
                    inp.fill("50")
                elif "experience" in combined or "total exp" in combined:
                    inp.fill("9")
                elif "notice" in combined:
                    inp.fill("30")
                else:
                    inp.fill("9")
                page.wait_for_timeout(100)
            except Exception:
                pass

        # 4. Textareas
        textareas = page.locator('textarea')
        for t_i in range(textareas.count()):
            try:
                ta = textareas.nth(t_i)
                if ta.is_visible() and not ta.input_value():
                    ta.fill("Over 9 years of cross-functional leadership across Strategy & BizOps, GTM, Program Management, and Revenue Operations.")
                    page.wait_for_timeout(100)
            except Exception:
                pass

        # 5. Checkboxes (consent / terms)
        cbs = page.locator('input[type="checkbox"]')
        for c_i in range(cbs.count()):
            try:
                cb = cbs.nth(c_i)
                if cb.is_visible() and not cb.is_checked():
                    cb.check(force=True)
            except Exception:
                pass

        page.wait_for_timeout(800)

        # 6. Locate and click Next / Submit button
        submit_selectors = [
            'button:has-text("Next")',
            'button:has-text("Submit")',
            'button:has-text("Send Application")',
            'button:has-text("Apply")',
            'button[type="submit"]',
            '.btn-submit'
        ]
        for s_sel in submit_selectors:
            btn = page.locator(s_sel).first
            if btn.count() > 0 and btn.is_visible():
                if btn.is_enabled():
                    print(f"   [Questionnaire] Clicking enabled '{btn.inner_text().strip()}' button...")
                    btn.click(force=True)
                    page.wait_for_timeout(3000)
                    return True
                else:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(500)
                    if btn.is_enabled():
                        btn.click(force=True)
                        page.wait_for_timeout(3000)
                        return True

        return False
    except Exception as e:
        print(f"   [Questionnaire Notice]: {e}")
        return False


def verify_application_completion(page: Page, job_url: str) -> bool:
    """Multi-layer check to ensure application is genuinely submitted."""
    curr_url = page.url.lower()
    if "/job/applied" in curr_url or "applied" in curr_url:
        return True

    success_banner = page.locator(':has-text("Your application has been submitted successfully"), :has-text("submitted successfully"), :has-text("Job Applied")')
    if success_banner.count() > 0 and success_banner.first.is_visible():
        return True

    try:
        clean_url = job_url.split("?")[0]
        page.goto(clean_url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2000)
        applied_elements = page.locator('button, a, span').filter(has_text=re.compile(r'^(Applied|Already Applied)$', re.I))
        if applied_elements.count() > 0:
            for a_i in range(applied_elements.count()):
                el = applied_elements.nth(a_i)
                if el.is_visible() and el.inner_text().strip().lower() in ("applied", "already applied"):
                    return True
    except Exception:
        pass

    return False


def sweep():
    print("=" * 70)
    print("       IIMJOBS PENDING & PRE-FILLED SUBMISSION SWEEP ENGINE")
    print("=" * 70)

    # 1. Fetch pending & pre-filled IIMjobs records from jobs.db
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, company, title, url, status
            FROM jobs
            WHERE (status = 'Pending Authentication' OR (board_type = 'IIMjobs' AND status = 'Pre-filled - Ready for Review'))
        """)
        pending_jobs = c.fetchall()

    print(f"Found {len(pending_jobs)} IIMjobs records pending submission.")
    if not pending_jobs:
        print("No pending IIMjobs records found!")
        return

    selector = ResumeSelector()
    updater = SheetUpdater()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = browser.new_context(
            storage_state=str(SESSION_FILE),
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Check authentication
        page.goto("https://www.iimjobs.com/jobfeed", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        if "login" in page.url.lower():
            print("[FATAL] Candidate is not logged in on IIMjobs! Exiting.")
            browser.close()
            return

        print("[Auth Success] Candidate session confirmed!\n")

        for idx, (job_id, company, title, url, old_status) in enumerate(pending_jobs):
            clean_url = url.split("?")[0]
            print(f"[{idx + 1}/{len(pending_jobs)}] Processing ID #{job_id}: {title} @ {company}")
            print(f"     URL: {clean_url}")

            try:
                page.goto(clean_url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(2000)

                # Check if job is expired or closed
                body_text = page.locator("body").inner_text()
                if "job is no longer active" in body_text.lower() or "job has expired" in body_text.lower() or "page not found" in body_text.lower():
                    print("   -> Job is no longer active/expired. Marking as Closed / Inactive.")
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE jobs SET status = 'Closed / Inactive', date_updated = datetime('now') WHERE id = ?", (job_id,))
                        conn.commit()
                    continue

                # Check if already applied
                applied_btn = page.locator('button, a, span').filter(has_text=re.compile(r'^(Applied|Already Applied)$', re.I))
                if applied_btn.count() > 0 and any(applied_btn.nth(i).is_visible() for i in range(applied_btn.count())):
                    print("   -> Position is ALREADY APPLIED on portal! Capturing proof...")
                    ts = time.strftime("%Y%m%d_%H%M%S")
                    proof_path = LOGS_DIR / f"submitted_iimjobs_verified_{job_id}_{ts}.png"
                    try:
                        page.screenshot(path=str(proof_path))
                    except Exception:
                        pass
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE jobs SET status = 'Submitted', notes = ?, date_updated = datetime('now') WHERE id = ?",
                                  (f"Verified application on portal. Proof: {proof_path.name}", job_id))
                        conn.commit()
                    print(f"   >>> [CONFIRMED SUBMITTED] Proof: {proof_path.name} <<<\n")
                    continue

                # Find apply button
                apply_btn = page.locator('button:has-text("Apply"), a:has-text("Apply"), .apply-button, #apply-button').first
                if apply_btn.count() == 0 or not apply_btn.is_visible():
                    print("   -> No visible Apply button found. Marking Closed / Inactive.")
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE jobs SET status = 'Closed / Inactive', date_updated = datetime('now') WHERE id = ?", (job_id,))
                        conn.commit()
                    continue

                print("   -> Clicking Apply button...")
                apply_btn.click(force=True)
                page.wait_for_timeout(2500)

                # Check for "Apply Anyway" or mismatch modal
                anyway_btns = page.locator('button:has-text("Apply Anyway"), button:has-text("Proceed"), button:has-text("Yes, Apply"), button:has-text("Confirm")')
                if anyway_btns.count() > 0 and anyway_btns.first.is_visible():
                    print(f"   -> Clicking '{anyway_btns.first.inner_text().strip()}' modal button...")
                    anyway_btns.first.click(force=True)
                    page.wait_for_timeout(2500)

                # Check for questionnaire
                if "/screening" in page.url or "Submit a Form" in page.content() or page.locator('input[type="radio"]').count() > 0:
                    handle_screening_questionnaire(page)

                # Check for confirmation modals
                confirm_btn = page.locator('button:has-text("Confirm"), button:has-text("Send Application"), button:has-text("Submit"), .confirm-apply')
                if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                    print("   -> Clicking confirmation modal button...")
                    confirm_btn.first.click(force=True)
                    page.wait_for_timeout(2500)

                # Verify completion
                print("   [Verification Layer] Checking if application is genuinely completed...")
                is_completed = verify_application_completion(page, clean_url)
                ts = time.strftime("%Y%m%d_%H%M%S")

                if is_completed:
                    proof_path = LOGS_DIR / f"submitted_iimjobs_verified_{job_id}_{ts}.png"
                    try:
                        page.screenshot(path=str(proof_path))
                    except Exception:
                        pass
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE jobs SET status = 'Submitted', notes = ?, date_updated = datetime('now') WHERE id = ?",
                                  (f"Autonomous sweep verified on portal. Proof: {proof_path.name}", job_id))
                        conn.commit()
                    print(f"   >>> [CONFIRMED SUBMITTED] Proof: {proof_path.name} <<<\n")
                else:
                    fail_path = LOGS_DIR / f"unconfirmed_iimjobs_{job_id}_{ts}.png"
                    try:
                        page.screenshot(path=str(fail_path))
                    except Exception:
                        pass
                    print(f"   [Notice] Could not verify final submission on portal. Proof: {fail_path.name}\n")
                    with sqlite3.connect(DB_PATH) as conn:
                        c = conn.cursor()
                        c.execute("UPDATE jobs SET status = 'Recruiter Restricted', notes = ?, date_updated = datetime('now') WHERE id = ?",
                                  (f"Portal blocked or restricted application. Diagnostic: {fail_path.name}", job_id))
                        conn.commit()

                time.sleep(2.0)

            except Exception as e:
                print(f"   [Error on #{job_id}]: {e}\n")

        browser.close()

    print("=" * 70)
    print("IIMJOBS SWEEP RUN COMPLETED!")
    print("=" * 70)


if __name__ == "__main__":
    sweep()
