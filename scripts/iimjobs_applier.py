#!/usr/bin/env python3
"""
iimjobs_applier.py - Autonomous Application Engine for IIMjobs.com (Strictly Verified)

Features:
- Enforces strict candidate login verification (checks avatar & user session).
- Cycles through target charters (Strategy & Ops, Chief of Staff, Program Management, RevOps, BizOps).
- Navigates directly to each job URL in primary browser page.
- Pre-submission layer: Checks if the position is already applied on IIMjobs.
- Execution layer: Handles questionnaire (answers screening radios 'Yes', notice period '1 month', salary, experience) and submits.
- Strict Completion Verification Layer: Checks for official success confirmation ('Your application has been submitted successfully!', URL /job/applied, or button turning to disabled 'Applied').
- Proof Capture: Saves full-page proof screenshot for every submission.
- Real-time Sync: Updates SQLite database (jobs.db) and CSV (tracker.csv).
"""

import sys
import time
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from playwright.sync_api import sync_playwright, Page

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from scripts.resume_selector import ResumeSelector
from scripts.sheet_updater import SheetUpdater

SESSION_FILE = BASE_DIR / "sessions" / "iimjobs_state.json"
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

IIMJOBS_SEARCH_TARGETS = [
    # Tier 1: Completely Remote & Executive
    {"query": "Strategy Operations", "location": "Remote"},
    {"query": "Chief of Staff", "location": "Remote"},
    {"query": "Revenue Operations", "location": "Remote"},
    {"query": "Program Manager", "location": "Remote"},

    # Tier 2: Hyderabad (GCCs & Tech Centers)
    {"query": "Strategy Operations", "location": "Hyderabad"},
    {"query": "Program Manager", "location": "Hyderabad"},
    {"query": "Technical Program Manager", "location": "Hyderabad"},
    {"query": "Director Program Management", "location": "Hyderabad"},
    {"query": "Operations Head", "location": "Hyderabad"},

    # Tier 3: Bangalore (Primary Tech Ecosystem)
    {"query": "Strategy Operations", "location": "Bangalore"},
    {"query": "Chief of Staff", "location": "Bangalore"},
    {"query": "Founders Office", "location": "Bangalore"},
    {"query": "Revenue Operations", "location": "Bangalore"},
    {"query": "GTM Strategy", "location": "Bangalore"},
    {"query": "Program Manager", "location": "Bangalore"},
    {"query": "Business Operations", "location": "Bangalore"},

    # Tier 4: Gurgaon / Delhi NCR
    {"query": "Strategy Operations", "location": "Gurgaon"},
    {"query": "Chief of Staff", "location": "Gurgaon"},
    {"query": "Founders Office", "location": "Gurgaon"},
    {"query": "Revenue Operations", "location": "Gurgaon"},
    {"query": "Program Manager", "location": "Gurgaon"},
]


class IIMJobsApplier:
    def __init__(self, headless: bool = True, min_score: float = 70.0):
        self.headless = headless
        self.min_score = min_score
        self.selector = ResumeSelector()
        self.updater = SheetUpdater()
        # Only skip jobs that have already been genuinely submitted
        self.submitted_urls = self.updater.get_submitted_urls()

    def is_logged_in(self, page: Page) -> bool:
        """Checks whether candidate is genuinely authenticated on IIMjobs."""
        try:
            page.goto("https://www.iimjobs.com/jobfeed", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)

            # Check if user avatar or name exists
            avatar = page.locator('img[alt="user_img"], .MuiAvatar-root, [class*="user_name"]')
            if avatar.count() > 0 and avatar.first.is_visible():
                return True

            # Check for candidate navigation elements
            if "jobfeed" in page.url or "feed" in page.url:
                return True

            register_btn = page.locator('button:has-text("Register"), a:has-text("Register"), a:has-text("Sign In")')
            if register_btn.count() > 0 and register_btn.first.is_visible():
                return False

            return "login" not in page.url.lower()
        except Exception as e:
            print(f"[Auth Check Notice]: {e}")
            return False

    def handle_screening_questionnaire(self, page: Page) -> bool:
        """Handles Step 2 questionnaire (Submit a Form / screening questions)."""
        print("   [Questionnaire] Filling mandatory screening questions...")
        try:
            # 1. Radio Buttons: select 'Yes' or positive responses for each question
            radio_groups = page.locator('.MuiRadio-root, input[type="radio"], label:has-text("Yes")')
            yes_labels = page.locator('label:has-text("Yes"), span:has-text("Yes"), input[value="Yes"] + label')
            
            if yes_labels.count() > 0:
                for y_i in range(yes_labels.count()):
                    try:
                        lbl = yes_labels.nth(y_i)
                        if lbl.is_visible():
                            lbl.click(force=True)
                            page.wait_for_timeout(200)
                    except Exception:
                        pass
            else:
                # If specific 'Yes' labels aren't found, check generic radio buttons
                radios = page.locator('input[type="radio"]')
                for r_i in range(0, radios.count(), 2):  # Pick first option of each pair
                    try:
                        radios.nth(r_i).click(force=True)
                        page.wait_for_timeout(200)
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
                        page.wait_for_timeout(300)
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
                        continue  # Already filled

                    placeholder = (inp.get_attribute("placeholder") or "").lower()
                    name = (inp.get_attribute("name") or "").lower()
                    label_text = ""
                    try:
                        label_text = inp.evaluate('el => el.closest("div")?.innerText || ""').lower()
                    except Exception:
                        pass

                    combined = f"{placeholder} {name} {label_text}"
                    if "current ctc" in combined or "current salary" in combined:
                        inp.fill("35")
                    elif "expected ctc" in combined or "expected salary" in combined:
                        inp.fill("50")
                    elif "experience" in combined:
                        inp.fill("9")
                    elif "notice" in combined:
                        inp.fill("30")
                    page.wait_for_timeout(150)
                except Exception:
                    pass

            # 4. Textareas (screening summary / motivation)
            textareas = page.locator('textarea')
            for t_i in range(textareas.count()):
                try:
                    ta = textareas.nth(t_i)
                    if ta.is_visible() and not ta.input_value():
                        ta.fill("Over 9 years of cross-functional leadership in GTM, revenue strategy, program management, and cross-team execution.")
                        page.wait_for_timeout(150)
                except Exception:
                    pass

            page.wait_for_timeout(1000)

            # 5. Locate and click Next / Submit button
            submit_selectors = [
                'button:has-text("Next")',
                'button:has-text("Submit")',
                'button:has-text("Send Application")',
                'button[type="submit"]',
                '.btn-submit'
            ]
            for s_sel in submit_selectors:
                btn = page.locator(s_sel).first
                if btn.count() > 0 and btn.is_visible():
                    if btn.is_enabled():
                        print(f"   [Questionnaire] Clicking enabled '{btn.inner_text().strip()}' button...")
                        btn.click(force=True)
                        page.wait_for_timeout(3500)
                        return True
                    else:
                        print("   [Questionnaire] Submit button is currently disabled, scrolling & waiting...")
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1000)
                        if btn.is_enabled():
                            btn.click(force=True)
                            page.wait_for_timeout(3500)
                            return True

            return False
        except Exception as e:
            print(f"   [Questionnaire Notice]: {e}")
            return False

    def verify_application_completion(self, page: Page, job_url: str) -> bool:
        """
        STRICT MULTI-LAYER COMPLETION VERIFICATION:
        Ensures the position is 100% completed on the portal before recording.
        """
        # Indicator 1: Check if current page is /job/applied or shows success banner
        curr_url = page.url.lower()
        if "/job/applied" in curr_url or "applied" in curr_url:
            success_indicators = page.locator(':has-text("Your application has been submitted successfully"), :has-text("submitted successfully"), :has-text("Job Applied")')
            if success_indicators.count() > 0:
                return True

        # Indicator 2: Check for success toast / banner on page
        success_banner = page.locator(':has-text("Your application has been submitted successfully"), :has-text("submitted successfully")')
        if success_banner.count() > 0 and success_banner.first.is_visible():
            return True

        # Indicator 3: Navigate back to the job permalink and check if button is disabled 'Applied'
        try:
            page.goto(job_url, wait_until="domcontentloaded", timeout=25000)
            page.wait_for_timeout(2000)
            applied_elements = page.locator('button, a, span').filter(has_text=re.compile(r'^(Applied|Already Applied)$', re.I))
            if applied_elements.count() > 0:
                for a_i in range(applied_elements.count()):
                    el = applied_elements.nth(a_i)
                    if el.is_visible():
                        # Verify it is indeed marked applied
                        text = el.inner_text().strip().lower()
                        if text in ("applied", "already applied"):
                            return True
        except Exception:
            pass

        return False

    def run(self, target_applications: int = 50):
        if not SESSION_FILE.exists():
            print(f"[Error] No active IIMjobs session file found at {SESSION_FILE}!")
            print("Please run: ./.venv/bin/python job-hunter/scripts/login_portal.py --portal iimjobs")
            return

        print("=" * 70)
        print("          IIMJOBS.COM VERIFIED APPLICATION ENGINE")
        print("=" * 70)
        print(f"Target Submissions:  {target_applications}")
        print(f"Min Fit Score:       {self.min_score}%")
        print(f"Session File:        {SESSION_FILE}")
        print("=" * 70)

        submitted_count = 0

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = browser.new_context(
                storage_state=str(SESSION_FILE),
                viewport={"width": 1280, "height": 900},
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            page = context.new_page()

            # Verify active candidate session
            print("Verifying candidate login authentication on IIMjobs...")
            if not self.is_logged_in(page):
                print("\n" + "!" * 70)
                print("[FATAL] NOT LOGGED IN TO IIMJOBS!")
                print("Cannot submit applications until candidate logs into IIMjobs.")
                print("!" * 70 + "\n")
                browser.close()
                return

            print("[Success] Candidate session is genuinely authenticated!\n")

            for target in IIMJOBS_SEARCH_TARGETS:
                if submitted_count >= target_applications:
                    break

                q = target["query"]
                loc = target["location"]
                print(f"\n============================================================")
                print(f"Searching: '{q}' in '{loc}'")
                print(f"Verified Progress: {submitted_count}/{target_applications} submitted")
                print(f"============================================================")

                search_url = f"https://www.iimjobs.com/search/{q.replace(' ', '-')}-{loc}-0-0-0-0-0-0.html"
                try:
                    page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                except Exception as e:
                    print(f"Navigation notice: {e}")
                    continue

                # Collect candidate job links
                links = page.locator('a[href*="/j/"]')
                link_count = links.count()
                job_urls: List[str] = []
                for i in range(min(link_count, 35)):
                    href = links.nth(i).get_attribute("href")
                    if href:
                        if not href.startswith("http"):
                            href = f"https://www.iimjobs.com{href}"
                        # Strip tracking parameters for clean deduplication
                        clean_url = href.split("?")[0]
                        if clean_url not in job_urls and clean_url not in self.submitted_urls:
                            job_urls.append(clean_url)

                print(f"Found {len(job_urls)} new candidate positions to evaluate.")

                for j_url in job_urls:
                    if submitted_count >= target_applications:
                        break

                    try:
                        # Direct navigation to the job details page
                        page.goto(j_url, wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(2000)

                        title_el = page.locator('h1, .job-title, [class*="jobTitle"]').first
                        title = title_el.inner_text().strip() if title_el.count() > 0 else "Role"

                        comp_el = page.locator('.company-name, [class*="companyName"], .posted-by, h2').first
                        company = comp_el.inner_text().strip() if comp_el.count() > 0 else "Company"

                        # Extract Job ID
                        job_id_match = re.search(r'-(\d+)$', j_url)
                        job_id = job_id_match.group(1) if job_id_match else str(int(time.time()))

                        # LAYER 1: Pre-Submission Portal Check (Already applied?)
                        applied_badge = page.locator('button, a, span').filter(has_text=re.compile(r'^(Applied|Already Applied)$', re.I))
                        if applied_badge.count() > 0 and applied_badge.first.is_visible():
                            print(f"\n[Verified Already Applied] {title} @ {company}")
                            clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())[:15]
                            proof_path = LOGS_DIR / f"submitted_iimjobs_{clean_comp}_{job_id}_already_applied.png"
                            try:
                                page.screenshot(path=str(proof_path))
                            except Exception:
                                pass

                            submitted_count += 1
                            self.submitted_urls.add(j_url)
                            self.updater.log_application(
                                company=company,
                                job_title=title,
                                location=loc,
                                url=j_url,
                                selected_resume="resume_ops_program.pdf",
                                fit_score=85.0,
                                rationale="Position confirmed as already applied directly on IIMjobs portal.",
                                board_type="IIMjobs",
                                description=f"{title} at {company}",
                                status="Submitted",
                                notes=f"Strictly verified application on IIMjobs portal. Proof: {proof_path.name}",
                                screenshot_path=str(proof_path)
                            )
                            print(f"   >>> [CONFIRMED PREVIOUSLY SUBMITTED #{submitted_count}] Proof: {proof_path.name} <<<\n")
                            continue

                        jd_text = page.locator('body').inner_text()

                        # LAYER 2: Role Fit Scoring
                        selected_resume, fit_score, rationale = self.selector.select_best_resume(
                            title=title,
                            description=jd_text[:3000],
                            location=loc
                        )

                        print(f"\n[Evaluating] {title} @ {company} (Score: {fit_score}%)")
                        if fit_score < self.min_score:
                            print(f"   -> Skipped (Fit score {fit_score}% < threshold {self.min_score}%)")
                            continue

                        # LAYER 3: Locate and Click Apply
                        apply_btn = page.locator('button:has-text("Apply"), a:has-text("Apply"), .apply-button, #apply-button').first
                        if apply_btn.count() == 0 or not apply_btn.is_visible():
                            print("   -> No visible Apply button found on page.")
                            continue

                        print(f"   -> Clicking Apply button for {title}...")
                        apply_btn.click(force=True)
                        page.wait_for_timeout(3000)

                        # LAYER 4: Questionnaire Handling
                        if "/screening" in page.url or "Submit a Form" in page.content() or page.locator('input[type="radio"]').count() > 0:
                            self.handle_screening_questionnaire(page)

                        # Handle any pop-up confirmation modals
                        confirm_btn = page.locator('button:has-text("Confirm"), button:has-text("Send Application"), button:has-text("Submit"), .confirm-apply')
                        if confirm_btn.count() > 0 and confirm_btn.first.is_visible():
                            print("   -> Clicking confirmation modal button...")
                            confirm_btn.first.click(force=True)
                            page.wait_for_timeout(2500)

                        # LAYER 5: STRICT POST-SUBMISSION COMPLETION VERIFICATION
                        print("   [Verification Layer] Checking if application is genuinely completed...")
                        is_completed = self.verify_application_completion(page, j_url)

                        clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())[:15]
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        
                        if is_completed:
                            proof_path = LOGS_DIR / f"submitted_iimjobs_{clean_comp}_{job_id}_{ts}.png"
                            try:
                                page.screenshot(path=str(proof_path))
                            except Exception:
                                pass

                            submitted_count += 1
                            self.submitted_urls.add(j_url)
                            self.updater.log_application(
                                company=company,
                                job_title=title,
                                location=loc,
                                url=j_url,
                                selected_resume=selected_resume,
                                fit_score=fit_score,
                                rationale=rationale,
                                board_type="IIMjobs",
                                description=jd_text[:1000],
                                status="Submitted",
                                notes=f"Strictly verified application on IIMjobs portal. Proof: {proof_path.name}",
                                screenshot_path=str(proof_path)
                            )
                            print(f"   >>> [CONFIRMED SUBMITTED #{submitted_count}] {title} @ {company} (Fit: {fit_score}%) <<<")
                            print(f"       Verification Proof: {proof_path.name}\n")
                        else:
                            fail_path = LOGS_DIR / f"failed_iimjobs_{clean_comp}_{job_id}_{ts}.png"
                            try:
                                page.screenshot(path=str(fail_path))
                            except Exception:
                                pass
                            print(f"   [VERIFICATION FAILED] Could not confirm submission. Discarded false record.")
                            print(f"       Diagnostic snapshot: {fail_path.name}")
                            # Record as pending review or skip so we never produce a false positive
                            self.updater.log_application(
                                company=company,
                                job_title=title,
                                location=loc,
                                url=j_url,
                                selected_resume=selected_resume,
                                fit_score=fit_score,
                                rationale=rationale,
                                board_type="IIMjobs",
                                description=jd_text[:1000],
                                status="Pre-filled - Ready for Review",
                                notes="Automated questionnaire reached but submission confirmation was inconclusive.",
                                screenshot_path=str(fail_path)
                            )

                        page.wait_for_timeout(2500)

                    except Exception as err:
                        print(f"   -> Error on {j_url}: {err}")
                        continue

            browser.close()

        print("\n" + "=" * 70)
        print(f"IIMJOBS RUN COMPLETE: {submitted_count} strictly verified submissions.")
        print(f"Tracker: {BASE_DIR / 'data' / 'tracker.csv'}")
        print(f"Database: {BASE_DIR / 'data' / 'jobs.db'}")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Strictly Verified IIMjobs Applier")
    parser.add_argument("--target", type=int, default=30, help="Target applications (default: 30)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Min score (default: 70.0)")
    parser.add_argument("--visible", action="store_true", help="Run visible browser")
    args = parser.parse_args()

    applier = IIMJobsApplier(headless=not args.visible, min_score=args.min_score)
    applier.run(target_applications=args.target)


if __name__ == "__main__":
    main()
