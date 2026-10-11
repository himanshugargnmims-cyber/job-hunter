#!/usr/bin/env python3
"""
hard_check_applier.py - Production-Grade Direct ATS Submission Engine with Strict Hard-Check Verification

Key Features:
1. Dynamic Candidate Profile:
   - Configured dynamically via context/screening_qa.json and environment variables
   - Supports custom contact numbers, international phone formatting, and verified profiles
2. Enterprise-Grade Form Resolution:
   - Greenhouse React-Select controls (.select__control) mapped for Country, Restrictions, Sponsorship, EEO
   - Canonical & Enterprise custom fields (Nationality, School, Discipline, Work Authorization)
   - Multi-pass resolution for dynamically rendered EEO fields
   - Iframe encapsulation support for embedded Greenhouse boards (MongoDB, HighRadius, Zenoti)
   - Automated Greenhouse OTP / Security Code resolver via Gmail IMAP
   - Ashby Autocomplete (Country / Region) and dynamic label-based question answering
   - Grounded context answering using profile_notes.md
3. Strict Hard-Check Post-Submit Verification:
   - Asserts true confirmation DOM text / URL redirect
   - Explicitly rejects submissions if validation errors or spam warnings are detected
   - Stores definitive high-resolution proof screenshots
"""

import sys
import os
import re
import time
import random
import json
import sqlite3
import imaplib
import email
from email.header import decode_header
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, Page, Frame, TimeoutError as PlaywrightTimeoutError

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
sys.path.insert(0, str(BASE_DIR))

from scripts.question_answerer import answer_custom_question, load_default_context_notes
from scripts.company_policy import CompanyPolicyManager
from scripts.eligibility import evaluate_eligibility
from scripts.application_models import JobPosting, ATSPlatform
from scripts.field_resolver import (
    resolve_salary,
    resolve_notice_period,
    resolve_experience,
    resolve_text_input,
    resolve_radio_or_dropdown
)

try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = BASE_DIR / "data" / "jobs.db"

QA_PATH = BASE_DIR / "context" / "screening_qa.json"
QA_EXAMPLE_PATH = BASE_DIR / "context" / "screening_qa.example.json"
qa_file = QA_PATH if QA_PATH.exists() else QA_EXAMPLE_PATH
QA_DATA = {}
if qa_file.exists():
    try:
        with open(qa_file, "r", encoding="utf-8") as f:
            QA_DATA = json.load(f)
    except Exception:
        QA_DATA = {}

_full_name = QA_DATA.get("full_name", "Alex Taylor")
_name_parts = _full_name.split()
_phone = QA_DATA.get("phone", "+1 555-0100")
_digits = re.sub(r"\D", "", _phone)

CANDIDATE = {
    "first_name": QA_DATA.get("first_name", _name_parts[0] if _name_parts else "Alex"),
    "last_name": QA_DATA.get("last_name", _name_parts[-1] if len(_name_parts) > 1 else "Taylor"),
    "full_name": _full_name,
    "name": _full_name,
    "email": os.getenv("GMAIL_USER") or QA_DATA.get("email", "candidate@example.com"),
    "phone": _phone,
    "phone_digits": _digits[-10:] if len(_digits) >= 10 else _digits,
    "location": QA_DATA.get("location", "Remote"),
    "location_city": QA_DATA.get("location", "Remote").split(",")[0].strip(),
    "country": QA_DATA.get("country", "United States"),
    "linkedin": QA_DATA.get("linkedin_url", ""),
    "github": QA_DATA.get("github_portfolio_url", ""),
    "school": QA_DATA.get("school", "University"),
    "degree": QA_DATA.get("degree", "Bachelor's Degree"),
    "discipline": QA_DATA.get("discipline", "Engineering / Computer Science"),
    "current_company": QA_DATA.get("screening_answers", {}).get("current_company", QA_DATA.get("current_company", "Tech Corp")),
    "current_title": QA_DATA.get("screening_answers", {}).get("current_title", QA_DATA.get("current_title", "Senior Lead")),
    "total_years_exp": str(QA_DATA.get("screening_answers", {}).get("total_years_experience", QA_DATA.get("total_years_exp", "5"))),
    "notice_period": str(QA_DATA.get("current_notice_period", "30")),
    "compensation": QA_DATA.get("screening_answers", {}).get("compensation", "Competitive market rate based on charter"),
    "summary": QA_DATA.get("screening_answers", {}).get("summary", QA_DATA.get("summary", "Experienced leader driving operational excellence."))
}


OTP_CACHE_FILE = BASE_DIR / "data" / "seen_otp_codes.txt"

def get_seen_otp_codes() -> set:
    if OTP_CACHE_FILE.exists():
        return set(OTP_CACHE_FILE.read_text().split())
    return {
        'kdTjaAcb', 'XFOiVsPy', 'FxG7xNvg', 'bWJSfY9J', 'FrS15Lsg', 
        'vbuNZEiv', 'ZHbncZPV', 'gngwklnc', '1cvHlfva', 'NJwlN6Wp', 
        'YntEwdzq', 'JHbdeUAM', 'IOf0mZDq', 'tCZNLBOX', '1VY1Qipg',
        'Le18DSk0', 'n9NRQo2b', 'mi5EDzXE', 'RWv6NLmF'
    }

def record_seen_otp_code(code: str) -> None:
    seen = get_seen_otp_codes()
    seen.add(code)
    OTP_CACHE_FILE.write_text("\n".join(seen) + "\n")


def fetch_latest_security_code(wait_seconds: int = 50) -> Optional[str]:
    """Scans Gmail IMAP for a fresh, un-used security code from Greenhouse or Clinch/Toast received recently."""
    user = os.getenv("GMAIL_USER")
    pwd = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not user or not pwd:
        return None

    seen_codes = get_seen_otp_codes()
    print(f"      [OTP] Checking Gmail ({user}) for fresh security verification code (ignoring {len(seen_codes)} prior codes)...")
    start_time = time.time()
    while time.time() - start_time < wait_seconds:
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(user, pwd)
            for folder in ['"[Gmail]/All Mail"', '"[Gmail]/Spam"']:
                mail.select(folder)
                status, data = mail.search(None, 'ALL')
                if data[0]:
                    msg_ids = data[0].split()
                    for mid in reversed(msg_ids[-8:]):
                        status, mdata = mail.fetch(mid, "(RFC822)")
                        msg = email.message_from_bytes(mdata[0][1])
                        
                        # Verify message timestamp is fresh (within last 300s)
                        date_hdr = msg.get("Date")
                        if date_hdr:
                            try:
                                msg_time = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                                if time.time() - msg_time > 300:
                                    continue
                            except Exception:
                                pass

                        subj = (msg.get("Subject") or "").lower()
                        from_hdr = (msg.get("From") or "").lower()
                        
                        if not any(k in from_hdr for k in ["greenhouse", "clinchtalent", "toast"]) and not any(k in subj for k in ["security code", "verify your login", "validation code"]):
                            continue

                        for part in msg.walk():
                            if part.get_content_type() in ["text/html", "text/plain"]:
                                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                                code = None
                                
                                # 1. Greenhouse 8-char code
                                m_h1 = re.findall(r'<h1[^>]*>\s*([A-Za-z0-9]{8})\s*</h1>', body)
                                if m_h1:
                                    code = m_h1[0].strip()
                                else:
                                    m_txt = re.findall(r'application:\s*\n+\s*([A-Za-z0-9]{8})', body)
                                    if m_txt:
                                        code = m_txt[0].strip()
                                
                                # 2. Toast / Clinch Talent 5-char code
                                if not code:
                                    m_toast = re.findall(r'website\.\s*\n+\s*([A-Za-z0-9]{4,8})\s*\n', body)
                                    if m_toast:
                                        code = m_toast[0].strip()
                                    else:
                                        m_toast2 = re.findall(r'validation code:\s*([A-Za-z0-9]{4,8})', body, re.IGNORECASE)
                                        if m_toast2:
                                            code = m_toast2[0].strip()

                                if code and code not in seen_codes:
                                    record_seen_otp_code(code)
                                    mail.logout()
                                    return code
            mail.logout()
        except Exception:
            pass
        time.sleep(2)
    return None


def smart_human_type(locator, value: str, field_name: str, target: Union[Page, Frame] = None, delay_range=(25, 45)) -> bool:
    """Non-destructively inspects field first.
    If already accurately populated by background resume parser, logs and skips cleanly.
    Otherwise, scrolls, clicks, and human-types with natural keystroke cadence and Tab transition."""
    if locator.count() == 0:
        return False
    try:
        el = locator.first
        if not el.is_visible() or not el.is_editable():
            return False

        curr_val = (el.input_value() or "").strip()
        val_clean = str(value).strip()

        # If already accurately parsed from resume, leave it untouched
        if curr_val.lower() == val_clean.lower() or (val_clean.lower() in curr_val.lower() and len(curr_val) < len(val_clean) + 4):
            print(f"            [Smart Skip] {field_name} already correctly populated ('{curr_val}')")
            return True

        el.scroll_into_view_if_needed()
        el.click()
        time.sleep(random.uniform(0.12, 0.25))

        # If there is an existing partial/mismatched value, clear cleanly
        if curr_val:
            el.fill("")
            time.sleep(0.08)

        # Human typing cadence
        keystroke_delay = random.randint(*delay_range)
        el.press_sequentially(val_clean, delay=keystroke_delay)

        main_page = target.page if hasattr(target, "page") and target.page else (target if hasattr(target, "keyboard") else None)
        if main_page and hasattr(main_page, "keyboard"):
            main_page.keyboard.press("Tab")
        time.sleep(random.uniform(0.3, 0.6))
        print(f"            [Human Typed] {field_name}: '{val_clean}'")
        return True
    except Exception:
        return False


def fill_greenhouse_application(target: Union[Page, Frame], resume_path: Path, company: str, job_title: str) -> None:
    """Fills Greenhouse ATS application forms with full React-Select, multi-pass EEO, and autocomplete support."""
    main_page = target.page if hasattr(target, "page") and target.page else target
    print("      [1/6] Attaching resume...")
    file_inputs = target.locator('input[type="file"]')
    if file_inputs.count() > 0 and resume_path.exists():
        try:
            p_obj = target if hasattr(target, "expect_response") else main_page
            try:
                with p_obj.expect_response(lambda r: "amazonaws.com" in r.url and r.status == 201, timeout=8000):
                    file_inputs.first.set_input_files(str(resume_path))
                print(f"            Attached resume and verified S3 upload: {resume_path.name}")
            except Exception:
                file_inputs.first.set_input_files(str(resume_path))
                time.sleep(3)
                print(f"            Attached resume: {resume_path.name}")
        except Exception as e:
            print(f"            Resume upload note: {e}")

    print("      [2/6] Inspecting & reconciling text contact fields (human cadence)...")
    fn_loc = target.locator('input[id*="first" i], input[name*="first" i], input[placeholder*="first" i], input[aria-label*="first" i]').first
    smart_human_type(fn_loc, CANDIDATE["first_name"], "First Name", target)

    ln_loc = target.locator('input[id*="last" i], input[name*="last" i], input[placeholder*="last" i], input[aria-label*="last" i]').first
    smart_human_type(ln_loc, CANDIDATE["last_name"], "Last Name", target)

    ffn_loc = target.locator('input[id*="full_name" i], input[name*="full_name" i], input[id*="fullname" i], input[name*="fullname" i], input[placeholder*="full name" i]').first
    smart_human_type(ffn_loc, CANDIDATE["name"], "Full Name", target)

    em_loc = target.locator('input[id*="email" i], input[name*="email" i], input[type="email"], input[placeholder*="email" i]').first
    smart_human_type(em_loc, CANDIDATE["email"], "Email", target)

    # Phone Country Code -> India (+91)
    country_ctrl = target.locator('#country').locator('xpath=ancestor::*[contains(@class, "select__control")]').first
    if country_ctrl.count() == 0:
        country_ctrl = target.locator('label:has-text("Country") ~ div .select__control, .select__control:has(.flag-icon)').first
    if country_ctrl.count() > 0 and country_ctrl.is_visible():
        try:
            country_ctrl.click(timeout=3000)
            time.sleep(0.3)
            opt_91 = target.locator('.select__option:has-text("+91")').first
            if opt_91.count() > 0:
                opt_91.click()
                time.sleep(0.3)
                print("            Selected Phone Country Code: India (+91)")
        except Exception as e:
            print(f"            Phone country note: {e}")

    # Candidate Phone Number
    for ph in target.locator('input[id*="phone" i], input[name*="phone" i], input[type="tel"], input[placeholder*="phone" i]').all():
        if ph.is_visible():
            is_iti = "iti" in (ph.get_attribute("class") or "") or ph.get_attribute("type") == "tel" or ph.get_attribute("data-intl-tel-input-id") is not None
            val = CANDIDATE["phone"] if is_iti else CANDIDATE["phone_digits"]
            curr_p = (ph.input_value() or "").strip()
            if curr_p and (curr_p == val or CANDIDATE["phone_digits"] in curr_p):
                print(f"            [Smart Skip] Phone already correctly populated ('{curr_p}')")
            else:
                smart_human_type(ph, val, "Phone", target)
            break

    # Location Autocomplete
    loc = target.locator('#candidate-location, input[id*="location" i], input[name*="location" i]').first
    if loc.count() > 0 and loc.is_visible():
        try:
            if not loc.input_value():
                loc.click()
                loc.fill("Bengaluru, Karnataka, India")
                time.sleep(1.0)
                if hasattr(target, "page") and target.page:
                    target.page.keyboard.press("ArrowDown")
                    time.sleep(0.3)
                    target.page.keyboard.press("Enter")
                elif hasattr(target, "keyboard"):
                    target.keyboard.press("ArrowDown")
                    time.sleep(0.3)
                    target.keyboard.press("Enter")
                print("            Location selected via autocomplete: Bengaluru, Karnataka, India")
        except Exception:
            pass

    # Other text fields (LinkedIn, Preferred Name, adjustments, CTC, notice period, dates)
    for inp in target.locator('input[type="text"], input[type="number"], input:not([type])').all():
        try:
            if not inp.is_visible() or not inp.is_editable() or inp.input_value() or inp.get_attribute("readonly"):
                continue
            cls = inp.get_attribute("class") or ""
            if "select__input" in cls:
                continue
            inp_id = (inp.get_attribute("id") or "").lower()
            inp_name = (inp.get_attribute("name") or "").lower()
            inp_ph = (inp.get_attribute("placeholder") or "").lower()
            inp_type = (inp.get_attribute("type") or "").lower()
            lbl_text = inp.evaluate('''e => {
                let id = e.id;
                let l = id ? document.querySelector(`label[for="${id}"]`) : null;
                let container = e.closest(".chakra-form-control") || e.closest(".form-group") || e.closest("fieldset") || e.closest("div[class*='form']") || e.parentElement;
                let p = e.closest("div");
                return ((l ? l.innerText : "") + " " + (container ? container.innerText : "") + " " + (p ? p.innerText : "")).toLowerCase();
            }''')
            lbl = f"{inp_id} {inp_name} {inp_ph} {lbl_text}".lower()

            if "linkedin" in lbl:
                inp.fill(CANDIDATE["linkedin"], timeout=3000)
            elif "start" in lbl and "year" in lbl or "start-date-year" in inp_id:
                inp.fill("2021", timeout=3000)
            elif "end" in lbl and "year" in lbl or "end-date-year" in inp_id:
                inp.fill("2026", timeout=3000)
            elif "prefer" in lbl and "name" in lbl:
                inp.fill(CANDIDATE["first_name"], timeout=3000)
            elif "adjustment" in lbl or "inclusive" in lbl or "accessible" in lbl:
                inp.fill("None required. Thank you.", timeout=3000)
            elif "company" in lbl or "employer" in lbl or "company-name" in inp_id:
                inp.fill(CANDIDATE["current_company"], timeout=3000)
            elif "title" in lbl or "designation" in lbl:
                inp.fill(CANDIDATE["current_title"], timeout=3000)
            elif any(k in lbl for k in ["address line 1", "street address", "address_1", "address 1", "addressline1"]):
                inp.fill("Indiranagar, 100 Feet Road", timeout=3000)
            elif any(k in lbl for k in ["address line 2", "address 2", "addressline2"]):
                inp.fill("Suite 401", timeout=3000)
            elif any(k in lbl for k in ["postal", "zip", "pincode", "pin code", "zipcode"]):
                inp.fill("560038", timeout=3000)
            elif any(k in lbl for k in ["province", "state", "region"]):
                inp.fill("Karnataka", timeout=3000)
            elif any(k in lbl for k in ["city", "town"]):
                inp.fill("Bengaluru", timeout=3000)
            elif "country" in lbl and "code" not in lbl:
                inp.fill("India", timeout=3000)
            elif "address" in lbl:
                inp.fill("Bengaluru, Karnataka, India", timeout=3000)
                time.sleep(0.5)
                if hasattr(main_page, "keyboard"):
                    main_page.keyboard.press("ArrowDown")
                    time.sleep(0.2)
                    main_page.keyboard.press("Enter")
            elif "notice" in lbl or "available" in lbl or "availability" in lbl:
                if inp_type == "number" or inp.get_attribute("inputmode") == "numeric":
                    inp.fill("30", timeout=3000)
                elif "month" in lbl:
                    inp.fill("1", timeout=3000)
                else:
                    inp.fill("30", timeout=3000)
            elif "city" in lbl or "location" in lbl:
                inp.fill("Bengaluru", timeout=3000)
            elif "expected" in lbl and ("ctc" in lbl or "salary" in lbl or "compensation" in lbl):
                inp.fill(resolve_salary(lbl, is_numeric_input=(inp_type == "number"), is_current_override=False), timeout=3000)
            elif "current" in lbl and ("ctc" in lbl or "salary" in lbl or "compensation" in lbl):
                inp.fill(resolve_salary(lbl, is_numeric_input=(inp_type == "number"), is_current_override=True), timeout=3000)
            elif "ctc" in lbl or "salary" in lbl or "compensation" in lbl or "fixed" in lbl or "remuneration" in lbl:
                inp.fill(resolve_salary(lbl, is_numeric_input=(inp_type == "number")), timeout=3000)
            elif "experience" in lbl or "exp" in lbl or "years" in lbl:
                inp.fill("9", timeout=3000)
            elif "local" in lbl and "given" in lbl:
                inp.fill(CANDIDATE["first_name"], timeout=3000)
            elif "local" in lbl and ("family" in lbl or "last" in lbl or "surname" in lbl):
                inp.fill(CANDIDATE["last_name"], timeout=3000)
            elif "github" in lbl:
                pass  # Do NOT fill GitHub with LinkedIn
            elif "website" in lbl or "portfolio" in lbl:
                inp.fill(CANDIDATE["linkedin"], timeout=3000)
            elif any(k in lbl for k in ["based in", "currently based", "hybrid", "bangalore", "bengaluru", "onsite", "office", "comfortable working", "willing to"]):
                inp.fill("Yes", timeout=3000)
            elif inp_type == "number" or inp.get_attribute("inputmode") == "numeric":
                if any(k in lbl for k in ["notice", "days", "period", "joining"]):
                    inp.fill("30", timeout=3000)
                elif any(k in lbl for k in ["salary", "ctc", "comp", "pay"]):
                    inp.fill("5500000", timeout=3000)
                else:
                    inp.fill("9", timeout=3000)
            else:
                pass  # Do not blindly fill N/A
        except Exception:
            pass

    print("      [2.5/6] Selecting radio buttons (screening questions)...")
    try:
        radios = target.locator('input[type="radio"]').all()
        radio_names = set()
        for r in radios:
            r_n = r.get_attribute("name")
            if r_n:
                radio_names.add(r_n)

        for r_n in radio_names:
            r_group = target.locator(f'input[type="radio"][name="{r_n}"]').all()
            if not r_group:
                continue
            if any(r.is_checked() for r in r_group):
                continue
            first_r = r_group[0]
            q_context = first_r.evaluate('''e => {
                let container = e.closest("fieldset") || e.closest(".chakra-form-control") || e.closest(".form-group") || e.closest("div[class*='question']") || e.closest("div");
                return container ? container.innerText.toLowerCase() : "";
            }''')
            is_negative = any(k in q_context for k in [
                "previously worked", "former employee", "currently work here",
                "relative", "conflict", "sponsorship", "require sponsorship",
                "require visa", "felony", "criminal", "non-compete"
            ])
            target_val = "no" if is_negative else "yes"

            picked_radio = None
            for r in r_group:
                r_val = (r.get_attribute("value") or "").lower()
                r_lbl = r.evaluate('''e => {
                    let id = e.id;
                    let l = id ? document.querySelector(`label[for="${id}"]`) : null;
                    let p = e.closest("label") || e.parentElement;
                    return ((l ? l.innerText : "") + " " + (p ? p.innerText : "")).toLowerCase();
                }''')
                is_match = False
                if target_val == "yes":
                    is_match = r_val in ["y", "yes", "1", "true"] or "yes" in r_lbl or "y" == r_lbl.strip()
                else:
                    is_match = r_val in ["n", "no", "0", "false"] or "no" in r_lbl or "n" == r_lbl.strip()

                if is_match:
                    picked_radio = r
                    break
            if not picked_radio:
                fallback_idx = 1 if is_negative and len(r_group) > 1 else 0
                picked_radio = r_group[fallback_idx]

            # Trigger click on parent label or control to satisfy Chakra UI/React synthetic events
            try:
                clicked = picked_radio.evaluate('''e => {
                    let p = e.closest("label") || e.closest(".chakra-radio") || e.parentElement;
                    if (p) {
                        p.click();
                        return true;
                    }
                    e.checked = true;
                    e.dispatchEvent(new Event("change", { bubbles: true }));
                    return true;
                }''')
                if not clicked:
                    picked_radio.check(force=True)
            except Exception:
                try:
                    picked_radio.check(force=True)
                except Exception:
                    pass

        for r_lbl in target.locator('label.chakra-radio, label[class*="radio"]').all():
            try:
                if not r_lbl.is_visible():
                    continue
                inp_child = r_lbl.locator('input[type="radio"]').first
                if inp_child.count() > 0 and inp_child.is_checked():
                    continue
                lbl_text = r_lbl.inner_text().strip().lower()
                parent_context = r_lbl.evaluate('''e => {
                    let p = e.closest(".chakra-form-control") || e.closest("fieldset") || e.closest("div");
                    return p ? p.innerText.toLowerCase() : "";
                }''')
                is_negative = any(k in parent_context for k in [
                    "previously worked", "former employee", "relative",
                    "conflict", "sponsorship", "require visa"
                ])
                target_lbl = "no" if is_negative else "yes"
                if target_lbl == lbl_text or (target_lbl in lbl_text and len(lbl_text) <= 5):
                    r_lbl.click(force=True)
                    time.sleep(0.2)
            except Exception:
                pass
    except Exception as e:
        print(f"      [Radio Notice]: {e}")

    print("      [3/6] Populating React-Select controls (multi-pass for dynamic EEO)...")
    # Fast sequential pass on input.select__input elements
    for inp in target.locator('input.select__input').all():
        try:
            ctrl = inp.locator('xpath=ancestor::*[contains(@class, "select__control")]').first
            if ctrl.count() > 0:
                current_val = ctrl.inner_text().strip()
                if current_val and current_val not in ["Select..."] and not current_val.startswith("Select"):
                    continue
            p_txt = inp.evaluate('e => { let p = e.closest(".select__container") || e.closest(".field") || e.parentElement; return p ? p.innerText : ""; }').lower()
            if not p_txt:
                continue

            ans = None
            if "country" in p_txt and any(k in p_txt for k in ["phone", "code", "dial"]):
                ans = "+91"
            elif "country" in p_txt and not any(k in p_txt for k in ["right to work", "authorized"]):
                ans = "India"
            elif any(k in p_txt for k in ["city", "location"]):
                ans = "Bengaluru"
            elif any(k in p_txt for k in ["hybrid", "onsite", "office", "hyderabad", "bangalore", "bengaluru", "relocate", "relocation", "comply"]):
                ans = "Yes"
            elif any(k in p_txt for k in ["authorized", "legally", "eligible", "right to work"]):
                ans = "Yes"
            elif any(k in p_txt for k in ["sponsorship", "visa", "require sponsorship", "need sponsorship"]):
                ans = "No"
            elif any(k in p_txt for k in ["privacy", "policy"]):
                ans = "Yes"
            elif any(k in p_txt for k in ["acknowledge", "declaration", "consent", "confirm", "certify"]):
                ans = "Acknowledge"
            elif any(k in p_txt for k in ["gender", "sex"]):
                ans = "Male"
            elif any(k in p_txt for k in ["veteran", "disability", "previously worked", "consultant", "contractor", "former employee", "relative"]):
                ans = "No"
            elif any(k in p_txt for k in ["hear about", "source"]):
                ans = "LinkedIn"
            elif any(k in p_txt for k in ["race", "ethnicity"]):
                ans = "Asian"
            elif any(k in p_txt for k in ["school", "university"]):
                ans = "National Institute of Technology"
            elif any(k in p_txt for k in ["degree", "education"]):
                ans = "Bachelor"
            elif any(k in p_txt for k in ["discipline"]):
                ans = "Engineering"

            if ans:
                inp.focus()
                inp.press_sequentially(ans, delay=30)
                time.sleep(0.3)
                if hasattr(main_page, "keyboard"):
                    main_page.keyboard.press("Enter")
                time.sleep(0.2)
        except Exception:
            pass

    for p_round in range(2):
        unfilled_controls = []
        for ctrl in target.locator('.select__control').all():
            val = ctrl.inner_text().strip()
            if val in ["", "Select..."] or val.startswith("Select") or any(k in val.lower() for k in ["select", "acknowledge"]):
                unfilled_controls.append(ctrl)

        if not unfilled_controls:
            break

        for ctrl in unfilled_controls:
            try:
                ctrl.scroll_into_view_if_needed(timeout=3000)
                parent_text = ctrl.evaluate('''e => {
                    let p = e.parentElement;
                    while (p && p.innerText.trim().length < 15 && p !== document.body) {
                        p = p.parentElement;
                    }
                    return p ? p.innerText.toLowerCase() : "";
                }''')
                try:
                    ctrl.click(timeout=1500)
                except Exception:
                    continue
                time.sleep(0.3)
                opts = target.locator('.select__option').all()
                if not opts:
                    continue

                chosen = None
                if "school" in parent_text or "university" in parent_text:
                    chosen = next((o for o in opts if "national institute of technology" in o.inner_text().lower()), None)
                    if not chosen:
                        chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["technology", "institute", "engineering"])), None)
                elif "degree" in parent_text or "education" in parent_text:
                    chosen = next((o for o in opts if "bachelor" in o.inner_text().lower()), None)
                elif "years of experience" in parent_text or "years of" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["5+", "5 -", "5-", "7+", "6+", "3-5", "3 - 5", "4 - 5", "4+"])), None)
                elif "discipline" in parent_text:
                    chosen = next((o for o in opts if "engineering" in o.inner_text().lower()), None)
                elif "nationality" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().lower().strip() == "indian" or o.inner_text().lower().strip() == "india"), None)
                elif "phone" in parent_text and "country" in parent_text:
                    chosen = next((o for o in opts if "+91" in o.inner_text() or (o.inner_text().lower().startswith("india") and "+91" in o.inner_text())), None)
                elif any(k in parent_text for k in ["authorized to work", "legally authorized", "eligible to work", "work authorization", "authorized in the location"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["will not require", "do not require", "authorized without", "citizen", "yes -", "yes,"]) and not any(k in o.inner_text().lower() for k in ["not authorized", "no - i will require", "no, i will require"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "authorized"]) and not any(k in o.inner_text().lower() for k in ["no", "not authorized", "will require"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("yes")), None)
                elif any(k in parent_text for k in ["sponsorship", "require a work permit", "require visa", "require sponsorship", "need sponsorship", "additional right to work support", "sponsor"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["will not require", "do not require", "not require sponsorship", "no sponsorship", "authorized without sponsorship", "citizen"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["no", "not require", "do not", "never"]) and not any(k in o.inner_text().lower() for k in ["yes", "will require", "require sponsorship", "need sponsorship"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower() in ["no", "no, i do not", "no, i will not"]), None)
                elif any(k in parent_text for k in ["hybrid", "in office", "in-office", "onsite", "on-site", "relocate", "relocation", "commute", "office model"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "comfortable", "open to", "agree", "willing"]) and not any(k in o.inner_text().lower() for k in ["no - i am only", "only seeking 100% remote", "not comfortable", "no,"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("yes")), None)
                elif any(k in parent_text for k in ["currently work here", "previously worked here", "previously worked at", "employed by", "worked at", "former employee", "current employee", "have you worked here", "previously been employed by"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["never worked", "no, i have never", "no, i do not", "no", "external applicant", "none"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("no")), None)
                    if not chosen:
                        chosen = next((o for o in opts if "no" in o.inner_text().strip().lower()), None)
                elif any(k in parent_text for k in ["procurement", "contract award", "government employee", "government official", "conflict of interest", "non-compete", "restriction", "relative", "family member", "outside business activity", "referred to this position", "nepotism"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["no", "no, i have not", "none", "no, i do not", "not applicable"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("no")), None)
                elif any(k in parent_text for k in ["18 years", "at least 18"]):
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i am at least 18"]), None)
                elif any(k in parent_text for k in ["salary range", "accept the listed salary"]):
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i accept"]), None)
                elif any(k in parent_text for k in ["remote location", "country selected above", "plan to work from"]):
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i do"]), None)
                elif "whatsapp" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["no", "no, i do not"]), None)
                elif "how you use ai tools" in parent_text or "use ai tools today" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["daily", "regular", "advanced", "frequent", "often", "extensively"]) and not any(k in o.inner_text().lower() for k in ["opposed", "rarely", "never", "traditional"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if not any(k in o.inner_text().lower() for k in ["opposed", "rarely", "never", "traditional"])), opts[0])
                elif "may use ai tools" in parent_text or "ai tools to assist" in parent_text or "ai policy" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "understand", "agree", "acknowledge"])), opts[0])
                elif "start" in parent_text and "month" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["june", "august", "06", "08"])), opts[0])
                elif "end" in parent_text and "month" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["may", "december", "05", "12"])), opts[-1])
                elif any(k in parent_text for k in ["how many years", "years of experience", "experience with"]):
                    chosen = next((o for o in opts if any(k in o.inner_text() for k in ["9–12", "9-12", "6–8", "6-8", "8+", "7+", "6+", "5+"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i have", "yes, i do"]), None)
                elif any(k in parent_text for k in ["architecture", "ownership", "gtm systems"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["led multi-region", "enterprise-wide", "owned architecture"])), opts[-1])
                elif any(k in parent_text for k in ["bachelor's degree", "years of software", "lead experience", "building and deploying", "orchestration", "rag systems", "backend engineering", "aws experience", "project manager", "5+ years", "experience being a"]):
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i have", "yes, i do"]), None)
                elif "age range" in parent_text or "age" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text() for k in ["25–34", "25-34", "30-39", "25 - 34", "35–44", "35-44"])), None)
                    if not chosen:
                        chosen = opts[1] if len(opts) > 1 else opts[0]
                elif "meet in person" in parent_text or "commit" in parent_text or "travel" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip() == "Yes"), None)
                elif "transgender" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["no", "no, i do not", "cisgender", "i do not identify as transgender", "no, i am not"]), None)
                    if not chosen:
                        chosen = next((o for o in opts if "decline" in o.inner_text().lower() or "prefer not" in o.inner_text().lower()), None)
                elif "sexual" in parent_text or "orientation" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["heterosexual", "straight"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if "decline" in o.inner_text().lower() or "prefer not" in o.inner_text().lower()), None)
                elif "disability" in parent_text:
                    chosen = next((o for o in opts if ("do not have" in o.inner_text().lower() or o.inner_text().strip().lower() in ["no", "no, i do not", "no, i don't"] or "none" in o.inner_text().lower()) and not any(k in o.inner_text().lower() for k in ["yes", "visible", "have a disability"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if "decline" in o.inner_text().lower() or "prefer not" in o.inner_text().lower()), None)
                elif "veteran" in parent_text or "armed forces" in parent_text:
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["not a protected veteran", "not a veteran", "no, i am not", "i am not a veteran", "i am not a protected", "no"]) and not any(k in o.inner_text().lower() for k in ["yes", "active member", "i am a veteran", "self-describe"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if "decline" in o.inner_text().lower() or "prefer not" in o.inner_text().lower()), None)
                elif "race" in parent_text or "ethnicity" in parent_text or "ethnic" in parent_text or "racial" in parent_text:
                    # Prefer South Asian / Asian, strictly avoiding American Indian and East Asian
                    chosen = next((o for o in opts if ("south asian" in o.inner_text().lower() or o.inner_text().lower().strip() == "asian") and "american indian" not in o.inner_text().lower() and "east asian" not in o.inner_text().lower()), None)
                    if not chosen:
                        chosen = next((o for o in opts if "asian" in o.inner_text().lower() and "american indian" not in o.inner_text().lower() and "east asian" not in o.inner_text().lower()), None)
                    if not chosen:
                        chosen = next((o for o in opts if "indian" in o.inner_text().lower() and "american indian" not in o.inner_text().lower()), None)
                    if not chosen:
                        chosen = next((o for o in opts if "decline" in o.inner_text().lower() or "prefer not" in o.inner_text().lower()), None)
                elif "hispanic" in parent_text or "latino" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["no", "not hispanic or latino", "not hispanic/latino", "no, i am not"]), None)
                elif "gender" in parent_text or "sex" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["male", "man", "cisgender man", "cisgender male", "he/him"] or o.inner_text().strip() in ["Male", "Man"]), None)
                elif "country" in parent_text or "located" in parent_text or "reside" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["india", "india (+91)"]), None)
                elif any(k in parent_text for k in ["privacy policy", "privacy notice", "policy", "terms", "read and understood", "plagiarism", "original", "consent", "confirm", "certify", "processing of personal data"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "acknowledge", "agree", "consent", "i agree", "i understand"])), None)
                    if not chosen:
                        chosen = opts[0]
                elif any(k in parent_text for k in ["restriction", "sponsorship", "visa", "non-compete"]):
                    chosen = next((o for o in opts if o.inner_text().strip() == "No"), None)
                elif "authorized" in parent_text or "eligible" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip() == "Yes"), None)
                elif any(k in parent_text for k in ["learn", "how did you", "source", "hear about", "where have you learned"]):
                    chosen = next((o for o in opts if "linkedin" in o.inner_text().lower() or "website" in o.inner_text().lower()), None)
                elif any(k in parent_text for k in ["alerts", "updates", "stay up to date", "marketing"]):
                    chosen = next((o for o in opts if o.inner_text().strip() == "No"), None)

                if chosen:
                    chosen_val = chosen.inner_text().strip()
                    try:
                        chosen.evaluate("e => e.click()")
                    except Exception:
                        try:
                            chosen.click(force=True, timeout=1000)
                        except Exception:
                            pass
                    if hasattr(main_page, "keyboard"):
                        main_page.keyboard.press("Enter")
                    print(f"            Selected [{chosen_val}] for: {parent_text[:35].replace(chr(10), ' ')}")
                else:
                    # Safe fallback: avoid accidentally picking 'Yes' for veteran, disability, employee, or conflict
                    if any(k in parent_text for k in ["veteran", "disability", "currently work", "employed", "employee", "work", "government", "conflict"]):
                        safe_opts = [o for o in opts if not any(k in o.inner_text().lower() for k in ["yes", "active", "currently work", "current employee"])]
                        fallback_opt = safe_opts[0] if safe_opts else opts[0]
                    else:
                        fallback_opt = opts[0]
                    first_val = fallback_opt.inner_text().strip()
                    try:
                        fallback_opt.evaluate("e => e.click()")
                    except Exception:
                        try:
                            fallback_opt.click(force=True, timeout=1000)
                        except Exception:
                            pass
                    if hasattr(main_page, "keyboard"):
                        main_page.keyboard.press("Enter")
                    print(f"            Fallback selected [{first_val}] for: {parent_text[:35].replace(chr(10), ' ')}")
                time.sleep(0.3)
            except Exception:
                pass

    print("      [3.5/6] Handling standard HTML select dropdowns...")
    for sel in target.locator('select').all():
        try:
            if not sel.is_visible():
                continue
            s_text = sel.evaluate('''e => {
                let id = e.id;
                let l = id ? document.querySelector(`label[for="${id}"]`) : null;
                let p = e.closest("div") || e.parentElement;
                return ((l ? l.innerText : "") + " " + (p ? p.innerText : "")).toLowerCase();
            }''')
            if any(k in s_text for k in ["font", "opacity", "caption", "color", "style"]):
                continue
            opts = sel.locator('option').all()
            if len(opts) <= 1:
                continue
            chosen_opt = None
            if any(k in s_text for k in ["agree", "consent", "privacy", "terms", "understand", "policy"]):
                chosen_opt = next((o for o in opts if any(k in o.inner_text().lower() for k in ["agree", "yes", "i agree", "accept"])), None)
            elif any(k in s_text for k in ["sponsorship", "visa", "conflict", "felony", "criminal"]):
                chosen_opt = next((o for o in opts if o.inner_text().strip().lower() in ["no", "no, i do not"]), None)
            elif any(k in s_text for k in ["authorized", "eligible", "18 years"]):
                chosen_opt = next((o for o in opts if o.inner_text().strip().lower() in ["yes", "yes, i am"]), None)
            elif any(k in s_text for k in ["gender", "sex"]):
                chosen_opt = next((o for o in opts if o.inner_text().strip().lower() in ["male", "man"]), None)
            elif any(k in s_text for k in ["hear about", "source"]):
                chosen_opt = next((o for o in opts if any(k in o.inner_text().lower() for k in ["linkedin", "website"])), None)
            
            if not chosen_opt:
                chosen_opt = next((o for o in opts if o.get_attribute("value")), opts[-1])

            if chosen_opt:
                val = chosen_opt.get_attribute("value")
                sel.select_option(value=val)
                print(f"            Selected [{chosen_opt.inner_text().strip()}] for HTML select: {s_text[:35].replace(chr(10), ' ')}")
        except Exception:
            pass

    print("      [4/6] Answering custom screening questions (textareas)...")
    context_notes = load_default_context_notes()
    for ta in target.locator('textarea').all():
        if not ta.is_visible() or ta.input_value():
            continue
        lbl_text = ta.evaluate('e => e.closest("div")?.innerText || ""')
        ans = answer_custom_question(lbl_text, context_notes)
        ta.fill(ans)

    print("      [5/6] Checking required consents & agreements...")
    for cb in target.locator('input[type="checkbox"]').all():
        try:
            is_req = (cb.get_attribute("required") is not None) or (cb.get_attribute("aria-required") == "true")
            cb_id = cb.get_attribute("id") or ""
            cb_text = cb.evaluate('''e => {
                let id = e.id;
                let l = id ? document.querySelector(`label[for="${id}"]`) : null;
                let p = e.closest(".checkbox__wrapper") || e.closest("div") || e.closest("label");
                return ((l ? l.innerText : "") + " " + (p ? p.innerText : "")).toLowerCase();
            }''')
            if is_req or any(k in cb_text for k in ["consent", "privacy", "terms", "agree", "policy", "acknowledge", "data", "gdpr", "processing", "declaration"]):
                if not cb.is_checked():
                    cb.check(force=True)
                    time.sleep(0.2)
                    if not cb.is_checked() and cb_id:
                        lbl_target = target.locator(f'label[for="{cb_id}"]').first
                        if lbl_target.count() > 0:
                            lbl_target.click(force=True)
        except Exception:
            pass

    time.sleep(1)


def fill_ashby_application(page: Page, resume_path: Path, company: str, job_title: str) -> None:
    """Fills Ashby ATS application form with label resolution, Yes/No buttons, radio groups, and country autocomplete."""
    print("      [1/5] Uploading resume...")
    f_inps = page.locator('input[type="file"]').all()
    if f_inps and resume_path.exists():
        f_inps[0].set_input_files(str(resume_path))
        print("            Waiting up to 12s for Ashby background autofill to settle...")
        for _ in range(12):
            if page.locator('text="Autofill completed!"').count() > 0:
                print("            Detected: Autofill completed!")
                break
            time.sleep(1)
        time.sleep(2)

    # Check for secondary file inputs (e.g. Cover letter if explicitly required)
    all_files = page.locator('input[type="file"]').all()
    if len(all_files) > 1 and resume_path.exists():
        for f_idx, extra_f in enumerate(all_files[1:], start=1):
            try:
                parent_text = extra_f.evaluate('el => el.closest("div")?.innerText || ""').lower()
                is_req = extra_f.get_attribute("required") is not None or "required" in parent_text
                if is_req and not any(k in parent_text for k in ["replace", "v6_operations", ".pdf"]):
                    extra_f.set_input_files(str(resume_path))
                    print(f"            Uploaded document to required secondary file input #{f_idx}")
                    time.sleep(1.0)
            except Exception:
                pass

    print("      [2/5] Inspecting & reconciling Ashby basic details (human cadence)...")
    name_inp = page.locator('input[name="_systemfield_name"]').first
    smart_human_type(name_inp, CANDIDATE["full_name"], "Full Name", page)

    first_name_inp = page.locator('input[name*="firstName" i], input[id*="firstName" i]').first
    smart_human_type(first_name_inp, CANDIDATE["first_name"], "First Name", page)

    last_name_inp = page.locator('input[name*="lastName" i], input[id*="lastName" i]').first
    smart_human_type(last_name_inp, CANDIDATE["last_name"], "Last Name", page)

    email_inp = page.locator('input[name="_systemfield_email"], input[id*="email" i], input[type="email"]').first
    smart_human_type(email_inp, CANDIDATE["email"], "Email", page)

    phone_inp = page.locator('input[name="_systemfield_phoneNumber"], input[type="tel"], input[name*="phone" i], input[id*="phone" i]').first
    smart_human_type(phone_inp, CANDIDATE["phone"], "Phone", page)

    print("      [3/5] Setting Ashby location autocomplete...")
    for loc in page.locator('input.ashby-application-form-input-autocomplete').all():
        try:
            if not loc.input_value():
                loc.click()
                loc.press_sequentially("India", delay=50)
                time.sleep(1.5)
                popup = page.locator('div.ashby-application-form-input-autocomplete-popup-result, div[class*="autocomplete-popup-result"]').first
                if popup.count() > 0:
                    popup.click()
                    time.sleep(1.0)
                    print("            Selected Location: India")
        except Exception:
            pass

    print("      [4/5] Answering custom Ashby questions (Yes/No buttons, inputs, textareas, radios)...")
    # 4a. Ashby Yes/No buttons
    for yn in page.locator('.ashby-application-form-input-yesno').all():
        try:
            parent_text = yn.evaluate('e => e.closest(".ashby-application-form-field-entry") ? e.closest(".ashby-application-form-field-entry").innerText.toLowerCase() : ""')
            pressed_btn = yn.locator('button[aria-pressed="true"]').first
            if pressed_btn.count() > 0:
                continue

            if any(k in parent_text for k in ["without the need", "legally authorised to work", "legally authorized to work"]):
                yes_btn = yn.locator('button[data-option="yes"]').first
                if yes_btn.count() > 0:
                    yes_btn.scroll_into_view_if_needed()
                    yes_btn.hover()
                    time.sleep(0.2)
                    yes_btn.click()
                    print(f"            Ashby Yes/No: Selected [Yes] for: {parent_text.split(chr(10))[0][:40]}")
            elif any(k in parent_text for k in ["sponsorship", "require sponsorship", "require visa", "visa support", "ongoing employer support", "renewals", "visa renewal", "require a work permit", "support to maintain"]):
                no_btn = yn.locator('button[data-option="no"]').first
                if no_btn.count() > 0:
                    no_btn.scroll_into_view_if_needed()
                    no_btn.hover()
                    time.sleep(0.2)
                    no_btn.click()
                    print(f"            Ashby Yes/No: Selected [No] for: {parent_text.split(chr(10))[0][:40]}")
            elif any(k in parent_text for k in ["currently work", "previously worked", "employed by", "worked at", "former employee", "current employee", "have you worked", "previously been employed", "prior employee", "worked with", "worked for", "employed with"]):
                no_btn = yn.locator('button[data-option="no"]').first
                if no_btn.count() > 0:
                    no_btn.scroll_into_view_if_needed()
                    no_btn.hover()
                    time.sleep(0.2)
                    no_btn.click()
                    print(f"            Ashby Yes/No: Selected [No] for: {parent_text.split(chr(10))[0][:40]}")
            elif any(k in parent_text for k in ["restriction", "conflict", "felony", "misconduct", "disciplinary", "criminal", "non-compete", "relative", "family member", "contractor previously"]):
                no_btn = yn.locator('button[data-option="no"]').first
                if no_btn.count() > 0:
                    no_btn.scroll_into_view_if_needed()
                    no_btn.hover()
                    time.sleep(0.2)
                    no_btn.click()
                    print(f"            Ashby Yes/No: Selected [No] for: {parent_text.split(chr(10))[0][:40]}")
            elif any(k in parent_text for k in ["office", "in-person", "relocate", "authorized", "eligible", "18 years", "experience", "timezone", "legally authorised", "legally authorized", "minimum of", "foster city", "bay area", "open to reloc", "fluent", "proficient", "skill", "sql", "python", "salesforce", "hubspot", "crm", "experience with"]):
                yes_btn = yn.locator('button[data-option="yes"]').first
                if yes_btn.count() > 0:
                    yes_btn.scroll_into_view_if_needed()
                    yes_btn.hover()
                    time.sleep(0.2)
                    yes_btn.click()
                    print(f"            Ashby Yes/No: Selected [Yes] for: {parent_text.split(chr(10))[0][:40]}")
            else:
                if any(k in parent_text for k in ["agree", "understand", "acknowledge", "consent", "confirm", "available", "willing", "excited"]):
                    yes_btn = yn.locator('button[data-option="yes"]').first
                    if yes_btn.count() > 0:
                        yes_btn.scroll_into_view_if_needed()
                        yes_btn.hover()
                        time.sleep(0.2)
                        yes_btn.click()
                else:
                    no_btn = yn.locator('button[data-option="no"]').first
                    if no_btn.count() > 0:
                        no_btn.scroll_into_view_if_needed()
                        no_btn.hover()
                        time.sleep(0.2)
                        no_btn.click()
                    else:
                        yes_btn = yn.locator('button[data-option="yes"]').first
                        if yes_btn.count() > 0:
                            yes_btn.click()
            time.sleep(0.3)
        except Exception:
            pass

    # 4b. Field entries (inputs, textareas, file uploads)
    context_notes = load_default_context_notes()
    for entry in page.locator('.ashby-application-form-field-entry, div[class*="fieldEntry"], div[class*="_fieldEntry_"], div[class*="FieldEntry"]').all():
        try:
            lbl = entry.locator('label.ashby-application-form-question-title, label').first
            txt = lbl.inner_text().strip() if lbl.count() > 0 else entry.inner_text().strip().split('\n')[0]
            txt_l = txt.lower()

            # Check if this entry contains an unfilled file input
            entry_file = entry.locator('input[type="file"]').first
            if entry_file.count() > 0 and resume_path.exists():
                parent_txt = entry.inner_text().lower()
                if not any(k in parent_txt for k in ["replace", "v6_operations", ".pdf"]):
                    entry_file.set_input_files(str(resume_path))
                    print(f"            Uploaded document for required field: {txt[:40]}")
                    time.sleep(1.0)
                    continue

            ta = entry.locator('textarea:not([name*="recaptcha"])').first
            if ta.count() > 0 and ta.is_visible() and not ta.input_value():
                ans = answer_custom_question(txt, context_notes)
                ta.click()
                ta.fill(ans)
                page.keyboard.press("Tab")
                time.sleep(0.3)
                print(f"            Filled Ashby textarea for: {txt[:40]}")
                continue

            inp = entry.locator('input[type="text"], input[type="url"], input[type="tel"], input[type="number"], input:not([type])').first
            if inp.count() > 0 and inp.is_visible() and not inp.input_value():
                inp.click()
                inp_type = (inp.get_attribute("type") or "text").lower()
                if "github" in txt_l:
                    inp.fill(CANDIDATE.get("github") or CANDIDATE.get("linkedin"))
                elif any(k in txt_l for k in ["linkedin", "website", "portfolio", "replit", "project"]):
                    inp.fill(CANDIDATE.get("linkedin") or CANDIDATE.get("github"))
                elif any(k in txt_l for k in ["phone", "mobile"]):
                    inp.fill(CANDIDATE["phone"])
                elif any(k in txt_l for k in ["first name", "given name", "legal first", "preferred first", "preferred name"]):
                    inp.fill(CANDIDATE["first_name"])
                elif any(k in txt_l for k in ["last name", "family name", "surname", "legal last", "preferred last"]):
                    inp.fill(CANDIDATE["last_name"])
                elif any(k in txt_l for k in ["full name", "legal name", "legal first and last"]):
                    inp.fill(CANDIDATE["full_name"])
                elif any(k in txt_l for k in ["referred", "referral", "who referred"]):
                    inp.fill("No")
                elif any(k in txt_l for k in ["title", "designation", "role"]):
                    inp.fill(CANDIDATE.get("current_title", "Lead - CRO Office"))
                elif any(k in txt_l for k in ["employer", "company"]):
                    inp.fill(CANDIDATE["current_company"])
                elif any(k in txt_l for k in ["country", "based in", "working from"]):
                    inp.fill(CANDIDATE.get("country", "India"))
                elif any(k in txt_l for k in ["notice", "days", "availability"]):
                    if "month" in txt_l:
                        inp.fill("1")
                    else:
                        inp.fill("30")
                elif any(k in txt_l for k in ["salary", "compensation"]):
                    inp.fill(resolve_salary(txt_l, is_numeric_input=(inp_type == "number")))
                elif any(k in txt_l for k in ["experience", "years"]) and inp_type == "number":
                    inp.fill("9")
                elif any(k in txt_l for k in ["twitter", "x handle"]):
                    tw_val = CANDIDATE.get("twitter") or "https://x.com"
                    inp.fill(tw_val if inp_type == "url" else tw_val.split("/")[-1])
                elif any(k in txt_l for k in ["how did you hear", "hear about", "source"]):
                    inp.fill("LinkedIn / Company Careers")
                elif any(k in txt_l for k in ["if other", "specify below"]):
                    inp.fill("N/A")
                elif any(k in txt_l for k in ["portfolio", "url", "link", "website"]):
                    inp.fill(CANDIDATE.get("portfolio") or CANDIDATE.get("linkedin"))
                elif any(k in txt_l for k in ["why", "excited"]):
                    ans = answer_custom_question(f"Why are you excited to join {company}?", context_notes)
                    inp.fill(ans[:150])
                else:
                    ans = answer_custom_question(txt, context_notes)
                    inp.fill(ans[:150])
                page.keyboard.press("Tab")
                time.sleep(0.3)
                print(f"            Filled Ashby input for: {txt[:40]}")
                continue
        except Exception:
            pass

    # Direct pass for all unfilled visible textareas
    for ta in page.locator('textarea:not([name*="recaptcha"])').all():
        try:
            if ta.is_visible() and not ta.input_value():
                q_txt = ta.evaluate('''e => {
                    let p = e.closest("div[class*='field']") || e.closest("div") || e.parentElement;
                    let l = e.id ? document.querySelector(`label[for="${e.id}"]`) : null;
                    return (l ? l.innerText : (p ? p.innerText : e.placeholder || "")).trim().split('\\n')[0];
                }''')
                ans = answer_custom_question(q_txt, context_notes)
                ta.fill(ans)
                print(f"            Filled Ashby textarea (fallback) for: {q_txt[:40]}")
        except Exception:
            pass

    # Direct pass for all unfilled visible text inputs
    for inp in page.locator('input[type="text"], input[type="url"], input[type="tel"]').all():
        try:
            if inp.is_visible() and not inp.input_value():
                q_txt = inp.evaluate('''e => {
                    let p = e.closest("div[class*='field']") || e.closest("div") || e.parentElement;
                    let l = e.id ? document.querySelector(`label[for="${e.id}"]`) : null;
                    return (l ? l.innerText : (p ? p.innerText : e.placeholder || "")).trim().split('\\n')[0];
                }''')
                q_l = q_txt.lower()
                if "linkedin" in q_l:
                    inp.fill(CANDIDATE["linkedin"])
                elif any(k in q_l for k in ["country", "working from"]):
                    inp.fill("India")
                elif any(k in q_l for k in ["referred", "referral"]):
                    inp.fill("No")
                elif any(k in q_l for k in ["notice", "days"]):
                    inp.fill("30")
                elif any(k in q_l for k in ["years", "experience"]) and len(q_l.split()) < 8:
                    inp.fill("9")
                else:
                    ans = answer_custom_question(q_txt, context_notes)
                    inp.fill(ans[:120])
                print(f"            Filled Ashby input (fallback) for: {q_txt[:40]}")
        except Exception:
            pass

    # Checkboxes pass
    for cb in page.locator('input[type="checkbox"]').all():
        try:
            cb_label = cb.evaluate('e => (e.closest("label")?.innerText || e.closest("div")?.innerText || e.name || "").toLowerCase()')
            if any(k in cb_label for k in ["sponsorship", "require visa", "visa support"]):
                if cb.is_checked():
                    cb.uncheck(force=True)
            elif any(k in cb_label for k in [
                "authorized to work", "legally authorized", "straight", "heterosexual",
                "asian", "none of the above", "agree", "consent", "acknowledge", "terms"
            ]):
                if not cb.is_checked():
                    cb.check(force=True)
        except Exception:
            pass

    # 4c. Select dropdowns
    for sel in page.locator('select').all():
        try:
            sel_text = sel.evaluate('e => (e.closest(".ashby-application-form-field-entry")?.innerText || e.closest("div")?.innerText || "").toLowerCase()')
            opts = sel.locator('option').all()
            if not opts:
                continue
            if any(k in sel_text for k in ["sponsorship", "visa", "support"]):
                chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("no")), None)
            elif any(k in sel_text for k in ["authorized", "eligible", "right to work"]):
                chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("yes")), None)
            elif "gender" in sel_text:
                chosen = next((o for o in opts if "male" in o.inner_text().lower() or "man" in o.inner_text().lower()), None)
            elif "veteran" in sel_text:
                chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["not a protected veteran", "not a veteran", "no"])), None)
            elif "disability" in sel_text:
                chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["do not have", "no"])), None)
            elif "race" in sel_text or "ethnicity" in sel_text:
                chosen = next((o for o in opts if "asian" in o.inner_text().lower() and "american indian" not in o.inner_text().lower() and "east asian" not in o.inner_text().lower()), None)
            else:
                chosen = opts[0]
            if chosen:
                val = chosen.get_attribute("value")
                if val:
                    sel.select_option(value=val)
        except Exception:
            pass

    # 4d. Comprehensive Radio Button Group Resolution
    print("      [4d/5] Resolving all Ashby radio button groups...")
    radio_groups = page.locator('.ashby-application-form-input-radio-group, fieldset:has(input[type="radio"]), div:has(> input[type="radio"])').all()
    seen_radios = set()
    for rg in radio_groups:
        try:
            g_title_elem = rg.locator('legend, label.ashby-application-form-question-title, [class*="question-title"], label').first
            g_title = g_title_elem.inner_text().strip() if g_title_elem.count() > 0 else rg.inner_text().split("\n")[0]
            g_lower = g_title.lower()

            radios = rg.locator('input[type="radio"]').all()
            if not radios:
                continue

            # Check if any radio in group is already checked
            if any(r.is_checked() for r in radios):
                for r in radios:
                    rid = r.get_attribute("id")
                    if rid:
                        seen_radios.add(rid)
                continue

            choices = []
            for r in radios:
                rid = r.get_attribute("id") or ""
                if rid:
                    seen_radios.add(rid)
                lbl_elem = page.locator(f'label[for="{rid}"]').first if rid else None
                if lbl_elem and lbl_elem.count() > 0:
                    lbl_text = lbl_elem.inner_text().strip().lower()
                else:
                    lbl_text = r.evaluate('''el => {
                        let l = el.closest("label");
                        if (l) return l.innerText.trim();
                        let p = el.parentElement;
                        return p ? p.innerText.trim() : "";
                    }''').lower()
                choices.append((r, rid, lbl_text))

            chosen_tuple = None

            # Relocation / In-person / Office / HQ
            if any(k in g_lower for k in ["in-person", "office", "relocate", "relocation", "madison", "hybrid", "commute", "onsite", "foster city", "bay area", "new york", "san francisco", "nyc", "days/week"]):
                for c in choices:
                    if "able to relocate" in c[2]:
                        chosen_tuple = c
                        break
                if not chosen_tuple:
                    for c in choices:
                        if c[2].startswith("yes") or "yes" in c[2]:
                            chosen_tuple = c
                            break

            # SMS / Text updates consent
            elif any(k in g_lower for k in ["text message", "sms", "updates from"]):
                for c in choices:
                    if "do not consent" in c[2] or c[2].startswith("no"):
                        chosen_tuple = c
                        break
                if not chosen_tuple:
                    chosen_tuple = choices[0]

            # Prior Employment / Current Employment / Relatives / Non-Compete / Conflicts / Misconduct
            elif any(k in g_lower for k in [
                "employed", "employee", "worked", "worked for", "worked at", "prior employment", 
                "former", "currently work", "currently employed", "previously worked", "previously employed",
                "relative", "family member", "family", "nepotism", "relation",
                "conflict", "restriction", "non-compete", "non compete", "covenant", "nda",
                "felony", "crime", "conviction", "disciplinary", "misconduct", "investigation",
                "previously applied", "applied before", "prior application", "agency"
            ]):
                for c in choices:
                    if any(no_word in c[2] for no_word in ["no", "never", "none", "not employed", "external", "do not have"]):
                        chosen_tuple = c
                        break
                if not chosen_tuple:
                    for c in choices:
                        if c[2].startswith("no"):
                            chosen_tuple = c
                            break

            # Sponsorship / Visa
            elif any(k in g_lower for k in ["sponsor", "visa", "work permit", "ongoing support"]):
                for c in choices:
                    if c[2].startswith("no") or "do not require" in c[2]:
                        chosen_tuple = c
                        break

            # Work Authorization / Legally authorized
            elif any(k in g_lower for k in ["authorized", "eligible", "right to work"]):
                for c in choices:
                    if c[2].startswith("yes") or "authorized" in c[2]:
                        chosen_tuple = c
                        break

            # Veteran (Strict invariant: NOT veteran)
            elif any(k in g_lower for k in ["veteran", "armed forces"]):
                for c in choices:
                    if any(k in c[2] for k in ["not a protected veteran", "not a veteran", "no"]) and not any(k in c[2] for k in ["yes", "i am a veteran", "active"]):
                        chosen_tuple = c
                        break

            # Disability (Strict invariant: NO disability)
            elif any(k in g_lower for k in ["disability"]):
                for c in choices:
                    if any(k in c[2] for k in ["do not have", "no, i do not", "no"]) and not any(k in c[2] for k in ["yes", "have a disability"]):
                        chosen_tuple = c
                        break

            # Years of experience
            elif any(k in g_lower for k in ["years of", "how many years", "experience do you have"]):
                for c in choices:
                    if any(k in c[2] for k in ["8+", "7+", "6+", "5+", "9+", "6-8"]):
                        chosen_tuple = c
                        break

            # Gender
            elif any(k in g_lower for k in ["gender", "sex"]):
                for c in choices:
                    if ("male" in c[2] or "man" in c[2]) and "female" not in c[2]:
                        chosen_tuple = c
                        break

            # Race / Ethnicity
            elif any(k in g_lower for k in ["race", "ethnicity"]):
                for c in choices:
                    if ("south asian" in c[2] or "asian (not hispanic" in c[2] or c[2].strip() == "asian") and "american indian" not in c[2] and "east asian" not in c[2]:
                        chosen_tuple = c
                        break

            # Source / Referral / How did you hear
            elif any(k in g_lower for k in ["hear", "source", "referral", "learn"]):
                for c in choices:
                    if any(k in c[2] for k in ["linkedin", "company website", "careers website", "job board"]):
                        chosen_tuple = c
                        break

            # Global Region / Location
            elif any(k in g_lower for k in ["region", "global region", "located in", "based in"]):
                for c in choices:
                    if any(k in c[2] for k in ["apac", "asia", "india", "south asia", "asia pacific"]):
                        chosen_tuple = c
                        break

            # Fallback: Prefer YES for consent/agreements/authorization, and NO for everything else
            if not chosen_tuple and choices:
                if any(k in g_lower for k in ["agree", "consent", "confirm", "certify", "acknowledge", "authorized", "eligible", "18", "permit", "right to work"]):
                    for c in choices:
                        if c[2].startswith("yes") or "yes" in c[2]:
                            chosen_tuple = c
                            break
                else:
                    for c in choices:
                        if c[2].startswith("no") or "no" in c[2]:
                            chosen_tuple = c
                            break
                if not chosen_tuple:
                    chosen_tuple = choices[0]

            if chosen_tuple:
                chosen_r, chosen_rid, chosen_lbl = chosen_tuple
                if chosen_rid:
                    lbl_btn = page.locator(f'label[for="{chosen_rid}"]').first
                    if lbl_btn.count() > 0:
                        lbl_btn.click()
                    else:
                        chosen_r.check(force=True)
                else:
                    chosen_r.check(force=True)
                print(f"            Ashby Radio Selected: [{chosen_lbl[:35]}] for: {g_title[:35].replace(chr(10), ' ')}")
                time.sleep(0.3)
        except Exception as e:
            print(f"            Ashby radio note: {e}")

    # Check any remaining unchecked loose radios
    for r in page.locator('input[type="radio"]').all():
        try:
            rid = r.get_attribute("id") or ""
            if (rid and rid in seen_radios) or r.is_checked():
                continue
            lbl_elem = page.locator(f'label[for="{rid}"]').first if rid else None
            lbl_text = lbl_elem.inner_text().strip().lower() if lbl_elem and lbl_elem.count() > 0 else ""
            if not lbl_text:
                lbl_text = r.evaluate('el => el.closest("label")?.innerText.trim().toLowerCase() || ""')

            if any(k in lbl_text for k in ["linkedin", "company website", "careers website", "job board", "social media", "yes", "do not consent", "no"]):
                if rid and page.locator(f'label[for="{rid}"]').count() > 0:
                    page.locator(f'label[for="{rid}"]').first.click()
                else:
                    r.check(force=True)
                print(f"            Loose Ashby Radio checked: [{lbl_text[:30]}]")
                time.sleep(0.2)
        except Exception:
            pass

    # 4e. Required checkboxes (consent, privacy, gdpr)
    for cb in page.locator('input[type="checkbox"]').all():
        try:
            if not cb.is_checked():
                cb_lbl = cb.evaluate('e => (e.closest("label")?.innerText || e.closest("div")?.innerText || "").toLowerCase()')
                if any(k in cb_lbl for k in ['agree', 'consent', 'privacy', 'acknowledge', 'terms', 'gdpr', 'policy']):
                    cb.check(force=True)
                    print(f"            Checked Ashby consent: {cb_lbl[:30]}")
        except Exception:
            pass

    time.sleep(1)


def fill_lever_application(page: Page, resume_path: Path, company: str, job_title: str) -> None:
    """Fills Lever ATS application form with strict candidate details and EEO invariants."""
    print("      [1/5] Filling Lever basic details...")
    name_inp = page.locator('input[name="name"], input[name="fullName"], input[name*="name"]').first
    if name_inp.count() > 0 and (not name_inp.input_value() or not name_inp.input_value().strip()):
        name_inp.fill(CANDIDATE["full_name"])
        print(f"            Filled Lever Name: {CANDIDATE['full_name']}")

    email_inp = page.locator('input[name="email"]').first
    if email_inp.count() > 0 and not email_inp.input_value():
        email_inp.fill(CANDIDATE["email"])

    phone_inp = page.locator('input[name="phone"]').first
    if phone_inp.count() > 0 and not phone_inp.input_value():
        phone_inp.fill(CANDIDATE["phone"])

    loc_inp = page.locator('input[name="location"]').first
    if loc_inp.count() > 0 and not loc_inp.input_value():
        loc_inp.fill(CANDIDATE["location"])

    org_inp = page.locator('input[name="org"]').first
    if org_inp.count() > 0 and not org_inp.input_value():
        org_inp.fill(CANDIDATE["current_company"])

    # URLs
    li_inp = page.locator('input[name*="LinkedIn"], input[name*="linkedin"]').first
    if li_inp.count() > 0:
        li_inp.fill(CANDIDATE["linkedin"])

    # Do NOT fill GitHub with LinkedIn for business/revenue roles
    gh_inp = page.locator('input[name*="GitHub"], input[name*="github"]').first
    if gh_inp.count() > 0:
        gh_inp.fill("")

    port_inp = page.locator('input[name*="Portfolio"], input[name*="portfolio"]').first
    if port_inp.count() > 0:
        port_inp.fill(CANDIDATE["linkedin"])

    for extra_url in page.locator('input[name*="Twitter"], input[name*="Other"]').all():
        extra_url.fill("")

    print("      [2/5] Uploading resume...")
    f_inp = page.locator('input[name="resume"], input[type="file"]').first
    if f_inp.count() > 0 and resume_path.exists():
        f_inp.set_input_files(str(resume_path))
        time.sleep(2.5)

    print("      [3/5] Populating Lever EEO dropdowns & radios...")
    for sel in page.locator('select').all():
        try:
            s_text = sel.evaluate('e => (e.closest(".application-question")?.innerText || e.closest("div")?.innerText || "").toLowerCase()')
            sel_name = (sel.get_attribute("name") or "").lower()
            if any(k in s_text for k in ["location", "which location"]) or "location" in sel_name:
                for opt in sel.locator('option').all():
                    opt_txt = opt.inner_text().lower().strip()
                    if opt_txt in ["india", "bengaluru", "bangalore", "karnataka"]:
                        sel.select_option(value=opt.get_attribute("value"))
                        print(f"            Selected [{opt.inner_text().strip()}] for Location")
                        break
                    elif any(loc in opt_txt for loc in ["bangalore", "bengaluru"]) or ("india" in opt_txt and not any(bad in opt_txt for bad in ["ocean", "british", "indiana"])):
                        sel.select_option(value=opt.get_attribute("value"))
                        print(f"            Selected [{opt.inner_text().strip()}] for Location")
                        break
            elif "gender" in s_text:
                for opt in sel.locator('option').all():
                    if opt.inner_text().strip().lower() in ["male", "man"]:
                        sel.select_option(value=opt.get_attribute("value"))
                        print("            Selected [Male] for Gender")
                        break
            elif "veteran" in s_text:
                for opt in sel.locator('option').all():
                    if any(k in opt.inner_text().lower() for k in ["not a protected veteran", "not a veteran", "no"]):
                        sel.select_option(value=opt.get_attribute("value"))
                        print("            Selected [Not a protected veteran] for Veteran")
                        break
            elif "disability" in s_text:
                for opt in sel.locator('option').all():
                    if any(k in opt.inner_text().lower() for k in ["no, i do not have", "no", "do not have"]):
                        sel.select_option(value=opt.get_attribute("value"))
                        print("            Selected [No disability] for Disability")
                        break
        except Exception:
            pass

    # Race radio
    for r in page.locator('input[name*="race"]').all():
        try:
            r_lbl = r.evaluate('e => e.closest("label") ? e.closest("label").innerText.toLowerCase() : ""')
            if "asian" in r_lbl and "american indian" not in r_lbl and "east asian" not in r_lbl:
                r.check(force=True)
                print("            Selected [Asian] for Race")
                break
        except Exception:
            pass

    # Disability signature & date
    sig_inp = page.locator('input[name*="disabilitySignature"]:not([name*="Date"])').first
    if sig_inp.count() > 0:
        sig_inp.fill(CANDIDATE["full_name"])
        print(f"            Signed Disability: {CANDIDATE['full_name']}")
    date_inp = page.locator('input[name*="disabilitySignatureDate"]').first
    if date_inp.count() > 0:
        date_inp.fill(time.strftime("%m/%d/%Y"))
        print(f"            Dated Disability: {time.strftime('%m/%d/%Y')}")

    print("      [4/5] Answering custom screening questions (inputs/textareas)...")
    context_notes = load_default_context_notes()
    for q in page.locator('.application-question, .custom-question').all():
        try:
            q_text = q.inner_text().strip()
            q_lower = q_text.lower()
            
            ta = q.locator('textarea').first
            if ta.count() > 0 and ta.is_visible() and not ta.input_value():
                if any(k in q_lower for k in ["expected", "compensation", "salary", "ctc"]):
                    ta.fill(resolve_salary(q_lower, is_current_override=False))
                elif any(k in q_lower for k in ["current", "compensation", "salary", "ctc"]):
                    ta.fill(resolve_salary(q_lower, is_current_override=True))
                elif any(k in q_lower for k in ["notice", "days to join"]):
                    ta.fill(resolve_notice_period(q_lower))
                elif any(k in q_lower for k in ["years of", "experience"]) and len(q_lower.split()) < 8:
                    ta.fill(resolve_experience(q_lower))
                else:
                    ans = answer_custom_question(q_text, context_notes)
                    ta.fill(ans)
                continue

            inp = q.locator('input[type="text"]').first
            if inp.count() > 0 and inp.is_visible() and not inp.input_value():
                inp_name = (inp.get_attribute("name") or "").lower()
                if any(k in inp_name for k in ["urls[", "eeo[", "phone", "email", "location", "org", "name"]):
                    continue
                if any(k in q_lower for k in ["expected", "compensation", "salary", "ctc"]):
                    inp.fill(resolve_salary(q_lower, is_current_override=False))
                elif any(k in q_lower for k in ["current", "compensation", "salary", "ctc"]):
                    inp.fill(resolve_salary(q_lower, is_current_override=True))
                elif any(k in q_lower for k in ["notice", "days"]):
                    inp.fill(resolve_notice_period(q_lower))
                elif any(k in q_lower for k in ["years", "experience"]) and len(q_lower.split()) < 8:
                    inp.fill(resolve_experience(q_lower))
                else:
                    ans = answer_custom_question(q_text, context_notes)
                    inp.fill(ans[:150])
                continue

            radios = q.locator('input[type="radio"]').all()
            if radios:
                radio_items = [(r, (r.evaluate('e => e.closest("label")?.innerText || ""').strip().lower())) for r in radios]
                if any(k in q_lower for k in ["gender", "describe your gender"]):
                    m_r = next((r for r, l in radio_items if l == "male" or "male" in l), None)
                    if m_r:
                        m_r.check(force=True)
                elif any(k in q_lower for k in ["experience", "years of relevant", "total years"]):
                    h_r = next((r for r, l in radio_items if any(x in l for x in ["8yrs +", "8+", "8 yrs", "8-", ">8", "5+"])), None)
                    if h_r:
                        h_r.check(force=True)
                elif any(k in q_lower for k in ["compensation", "salary", "current ctc"]):
                    c_r = next((r for r, l in radio_items if any(x in l for x in [">35", "35 lacs", "35+", ">30"])), None)
                    if c_r:
                        c_r.check(force=True)
                elif any(k in q_lower for k in ["based out of", "currently in", "located in bangalore", "in bangalore", "in bengaluru"]):
                    y_r = next((r for r, l in radio_items if l == "yes" or "yes" in l), None)
                    if y_r:
                        y_r.check(force=True)
                elif any(k in q_lower for k in ["willing to relocate", "relocate"]):
                    na_r = next((r for r, l in radio_items if "not applicable" in l), None)
                    if not na_r:
                        na_r = next((r for r, l in radio_items if "yes" in l), None)
                    if na_r:
                        na_r.check(force=True)
                elif any(k in q_lower for k in ["how did you", "know about", "hear about"]):
                    li_r = next((r for r, l in radio_items if "linkedin" in l), None)
                    if li_r:
                        li_r.check(force=True)
                elif any(k in q_lower for k in ["sponsorship", "require visa", "visa support"]):
                    no_r = next((r for r, l in radio_items if "no" in l), None)
                    if no_r:
                        no_r.check(force=True)
                elif any(k in q_lower for k in ["employed", "employee", "worked", "worked for", "worked at", "former", "previously", "relative", "conflict", "non-compete", "felony", "misconduct"]):
                    no_r = next((r for r, l in radio_items if "no" in l), None)
                    if no_r:
                        no_r.check(force=True)
                elif any(k in q_lower for k in ["authorized", "eligible", "right to work", "18 years"]):
                    yes_r = next((r for r, l in radio_items if "yes" in l), None)
                    if yes_r:
                        yes_r.check(force=True)
        except Exception:
            pass

    for cb in page.locator('input[type="checkbox"]').all():
        try:
            cb_lbl = cb.evaluate('e => (e.closest("label")?.innerText || e.parentElement?.innerText || e.closest("div")?.innerText || "").toLowerCase()')
            is_req = (cb.get_attribute("required") is not None) or (cb.get_attribute("aria-required") == "true")
            if is_req or any(k in cb_lbl for k in ['agree', 'consent', 'privacy', 'acknowledge', 'terms', 'gdpr', 'policy']):
                if not cb.is_checked():
                    cb.check(force=True)
            elif "asian" in cb_lbl and not any(bad in cb_lbl for bad in ["american indian", "alaska"]):
                if not cb.is_checked():
                    cb.check(force=True)
        except Exception:
            pass

    time.sleep(1)


def fill_kula_application(page: Page, resume_path: Path, company: str, job_title: str) -> None:
    """Fills Kula ATS application form (careers.kula.ai) with candidate details and custom answers."""
    print("      [1/5] Navigating to Kula apply form...")
    apply_tab = page.locator('button:has-text("Apply for this position"), a:has-text("Apply for this position")').first
    if apply_tab.count() > 0 and apply_tab.is_visible():
        try:
            apply_tab.click()
            time.sleep(2)
        except Exception:
            pass

    print("      [2/5] Uploading resume...")
    for f in page.locator('input[type="file"]').all():
        try:
            f.set_input_files(str(resume_path))
        except Exception:
            pass
    time.sleep(2.5)

    print("      [3/5] Filling Kula basic contact information...")
    fn = page.locator('input[name="info.first_name"]').first
    if fn.count() > 0:
        fn.fill(CANDIDATE["first_name"])
    ln = page.locator('input[name="info.last_name"]').first
    if ln.count() > 0:
        ln.fill(CANDIDATE["last_name"])
    em = page.locator('input[name="info.email"]').first
    if em.count() > 0:
        em.fill(CANDIDATE["email"])
    ph = page.locator('input#phone, input[name*="phone" i]').first
    if ph.count() > 0:
        ph.fill(CANDIDATE["phone_digits"])
    li = page.locator('input[name="info.linkedin_url"]').first
    if li.count() > 0:
        li.fill(CANDIDATE["linkedin"])
    addr = page.locator('input[name="info.address"]').first
    if addr.count() > 0:
        addr.fill("Bengaluru, Karnataka, India")

    print("      [4/5] Populating Kula profile details (Education & Experience)...")
    inst = page.locator('input[name*="institution"]').first
    if inst.count() > 0:
        inst.fill("National Institute of Technology")
        time.sleep(0.4)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")

    deg = page.locator('input[name*="degree"]').first
    if deg.count() > 0:
        deg.fill("Bachelor")
        time.sleep(0.4)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")

    exp_title = page.locator('input[name*="experience"][name*="title"]').first
    if exp_title.count() > 0:
        exp_title.fill(CANDIDATE.get("current_title") or "Lead - Strategy & Operations")

    exp_comp = page.locator('input[name*="experience"][name*="company"]').first
    if exp_comp.count() > 0:
        exp_comp.fill(CANDIDATE.get("current_company") or "Technology Solutions")
        time.sleep(0.4)
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")

    print("      [5/5] Answering screening questions...")
    context_notes = load_default_context_notes()
    for inp in page.locator('input[name^="additional_info"]').all():
        try:
            ph_text = (inp.get_attribute("placeholder") or "").lower()
            p_text = inp.evaluate('e => e.closest("div")?.innerText || ""').lower()
            comb = ph_text + " " + p_text
            if any(k in comb for k in ["comfortable", "location", "relocate", "onsite"]):
                inp.fill("Yes")
            elif any(k in comb for k in ["how soon", "join", "notice"]):
                inp.fill("30")
            elif "current" in comb and "ctc" in comb:
                inp.fill("4000000")
            elif "expected" in comb and "ctc" in comb:
                inp.fill("5500000")
            elif any(k in comb for k in ["experience", "years"]):
                inp.fill("9")
            else:
                inp.fill("Yes")
        except Exception:
            pass

    for ta in page.locator('textarea:not([name*="recaptcha"])').all():
        try:
            if ta.is_visible() and not ta.input_value():
                q_text = ta.evaluate('e => e.closest("div")?.innerText || ""').strip()
                ans = answer_custom_question(q_text, context_notes) if q_text else "Excited about the role and mission. With 9+ years experience across strategy, cross-functional execution, and CRO office leadership, I look forward to driving high-impact strategic initiatives."
                ta.fill(ans)
        except Exception:
            pass

    time.sleep(1)


def check_fresh_confirmation_email(company: str, max_age_seconds: int = 180) -> Optional[str]:
    """Scans Gmail IMAP for a fresh auto-confirmation email from ATS or company received within max_age_seconds."""
    user = os.getenv("GMAIL_USER")
    pwd = (os.getenv("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    if not user or not pwd:
        return None
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(user, pwd)
        for folder in ['"[Gmail]/All Mail"', '"[Gmail]/Spam"']:
            mail.select(folder)
            status, data = mail.search(None, 'ALL')
            if data[0]:
                msg_ids = data[0].split()
                for mid in reversed(msg_ids[-8:]):
                    status, mdata = mail.fetch(mid, "(RFC822)")
                    msg = email.message_from_bytes(mdata[0][1])
                    date_hdr = msg.get("Date")
                    if date_hdr:
                        try:
                            msg_time = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                            if time.time() - msg_time > max_age_seconds:
                                continue
                        except Exception:
                            pass
                    subj = (msg.get("Subject") or "").lower()
                    from_hdr = (msg.get("From") or "").lower()
                    clean_c = re.sub(r'[^a-zA-Z0-9]', '', company.lower())
                    clean_subj = re.sub(r'[^a-zA-Z0-9]', '', subj)
                    clean_from = re.sub(r'[^a-zA-Z0-9]', '', from_hdr)
                    c_parts = [p.lower() for p in re.findall(r'[a-zA-Z0-9]+', company) if len(p) > 2]

                    # STRICT: Auto-confirmation MUST match this target company
                    comp_matched = (clean_c in clean_subj) or (clean_c in clean_from) or any(p in subj or p in from_hdr for p in c_parts)
                    if not comp_matched:
                        continue

                    # STRICT: Exclude security codes, verification codes, login tokens, and OTPs
                    if any(k in subj for k in ["security code", "verification code", "verify your", "verification", "one-time", "login", "password"]):
                        continue

                    if any(k in subj for k in [
                        "thank you for applying",
                        "thanks for applying",
                        "application received",
                        "we have received your application",
                        "received your application",
                        "application submitted",
                        "thank you for your interest"
                    ]) or any(k in subj for k in ["application", "applying", "candidacy", "interest"]):
                        mail.logout()
                        return f"Verified via official confirmation email: '{msg.get('Subject')}' from {msg.get('From')}"
        mail.logout()
    except Exception:
        pass
    return None


def execute_hard_check_submission(target: Union[Page, Frame], page: Page, company: str, job_id: int) -> Dict[str, Any]:
    """Submits the form, handles OTP if prompted, and verifies unambiguous confirmation signal."""
    clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())
    ts = time.strftime("%Y%m%d_%H%M%S")

    submit_btn = None
    btn_candidates = [
        'button#form_submit_2_0',
        'button:has-text("APPLY NOW!")',
        'button:has-text("Apply Now!")',
        'button.ashby-application-form-submit-button',
        'button:has-text("Submit application")',
        'button:has-text("Submit Application")',
        'button:has-text("SUBMIT APPLICATION")',
        'button:has-text("Submit your application")',
        'button#btn-submit',
        'button#submit_app',
        'form button[type="submit"]',
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Apply for this position")',
        'button:has-text("Apply for this job")',
        'button:has-text("Apply for Position")',
        'button:has-text("Apply Now")',
        'button:has-text("Apply now")',
        'button:has-text("Start application")',
        'button:has-text("Start Application")',
        'button:has-text("JOIN NOW")',
        'button:has-text("Join Now")',
        'button:has-text("Send Application")',
        'button:has-text("Submit")',
        'button:has-text("SUBMIT")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]
    def is_valid_submit(b):
        try:
            if not b.is_visible():
                return False
            b_txt = (b.inner_text().strip() or b.get_attribute("value") or "").lower()
            b_cls = (b.get_attribute("class") or "").lower()
            b_id = (b.get_attribute("id") or "").lower()
            if any(k in b_txt for k in ["favorite", "favourite", "bookmark", "share", "save", "alert", "near me", "search"]):
                return False
            if any(k in b_cls for k in ["favourite", "favorite"]):
                return False
            if any(k in b_id for k in ["favourite", "favorite"]):
                return False
            return True
        except Exception:
            return False

    for cand in btn_candidates:
        loc = target.locator(cand)
        for idx in range(loc.count()):
            btn = loc.nth(idx)
            if is_valid_submit(btn):
                submit_btn = btn
                break
        if submit_btn:
            break

    if not submit_btn and target != page:
        for cand in btn_candidates:
            loc = page.locator(cand)
            for idx in range(loc.count()):
                btn = loc.nth(idx)
                if is_valid_submit(btn):
                    submit_btn = btn
                    break
            if submit_btn:
                break

    if not submit_btn:
        for f in page.frames:
            if f == page.main_frame:
                continue
            for cand in btn_candidates:
                loc = f.locator(cand)
                for idx in range(loc.count()):
                    btn = loc.nth(idx)
                    if is_valid_submit(btn):
                        submit_btn = btn
                        target = f
                        break
                if submit_btn:
                    break
            if submit_btn:
                break

    if not submit_btn:
        proof = LOGS_DIR / f"blocked_nobtn_{clean_comp}_{job_id}_{ts}.png"
        page.screenshot(path=str(proof), full_page=True)
        return {
            "status": "Blocked - Submit Button Not Found",
            "proof": str(proof),
            "notes": "Could not find visible submit button on page"
        }

    btn_text = submit_btn.inner_text().strip() or submit_btn.get_attribute("value")
    print(f"      [6/6] Submitting application (Clicking '{btn_text}')...")
    try:
        submit_btn.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    time.sleep(1.0)
    try:
        submit_btn.evaluate("e => e.click()")
    except Exception:
        try:
            submit_btn.click(force=True, timeout=3000)
        except Exception:
            pass
    time.sleep(3)

    # If it was a multi-step 'Start application' or 'Next' button, check if new fields or next submit button appeared
    if any(k in btn_text.lower() for k in ["start", "next", "continue"]):
        time.sleep(2)
        # Check if form inputs are now visible
        for extra_cand in [
            'form button[type="submit"]',
            'button[type="submit"]',
            'button:has-text("Submit application")',
            'button:has-text("Submit Application")',
            'button:has-text("Apply for this position")',
            'button:has-text("Submit")',
            'button:has-text("SUBMIT")'
        ]:
            next_b = target.locator(extra_cand).first
            if next_b.count() > 0 and next_b.is_visible():
                print(f"      [Multi-step Form] Found subsequent submit button '{next_b.inner_text().strip()}', clicking...")
                try:
                    next_b.click()
                except Exception:
                    next_b.click(force=True)
                time.sleep(3)
                break

    # Check for immediate security code prompt (GitLab / Canonical / MongoDB / Greenhouse email verification)
    sec_inputs = []
    for _ in range(8):
        sec_inputs = target.locator('input[id^="security-input-"]').all()
        if not sec_inputs:
            sec_inputs = [i for i in target.locator('p:has-text("Security code") ~ div input, label:has-text("Security code") ~ div input, div:has(> p:has-text("Security code")) input').all() if i.is_visible()]
        if not sec_inputs:
            sec_inputs = [i for i in page.locator('input[id^="security-input-"]').all() if i.is_visible()]
        if len(sec_inputs) == 8:
            break
        # If already confirmed, don't wait for security code
        b_txt = (page.locator("body").inner_text() or "").lower()
        if any(k in b_txt for k in ["thank you for applying", "your application has been received", "we have received your application", "application submitted"]):
            break
        time.sleep(1)

    if len(sec_inputs) == 8:
        print(f"      [Verification] Detected {len(sec_inputs)} security code input boxes! Polling Gmail...")
        code = fetch_latest_security_code(wait_seconds=45)
        if code:
            print(f"      [Verification] Retrieved security code: {code}! Entering code into boxes...")
            for idx, ch in enumerate(code[:8]):
                box = sec_inputs[idx]
                box.click()
                box.press_sequentially(ch, delay=100)
                box.evaluate('e => { e.dispatchEvent(new Event("input", { bubbles: true })); e.dispatchEvent(new Event("change", { bubbles: true })); }')
                time.sleep(0.1)

            time.sleep(1.5)
            final_submit_btn = target.locator('form button[type="submit"], button[type="submit"], button:has-text("Submit application")').last
            if final_submit_btn.count() == 0:
                final_submit_btn = page.locator('form button[type="submit"], button[type="submit"], button:has-text("Submit application")').last
            for _ in range(12):
                is_disabled = final_submit_btn.get_attribute("disabled") is not None or "disabled" in (final_submit_btn.get_attribute("class") or "")
                if not is_disabled:
                    break
                time.sleep(0.5)
            print("      [Verification] Submitting verified application...")
            final_submit_btn.click(force=True)
            time.sleep(6)

    # Check for single verification code input box (Toast / Clinch Talent verification)
    single_code_inp = None
    for _ in range(10):
        for cand in ['input#code', 'input[name="code"]', 'input[placeholder*="validation code" i]']:
            c_loc = target.locator(cand).first
            if c_loc.count() > 0 and c_loc.is_visible():
                single_code_inp = c_loc
                break
            if target != page:
                c_loc2 = page.locator(cand).first
                if c_loc2.count() > 0 and c_loc2.is_visible():
                    single_code_inp = c_loc2
                    break
        if single_code_inp:
            break
        b_txt = (page.locator("body").inner_text() or "").lower()
        if any(k in b_txt for k in ["thank you for applying", "your application has been received", "we have received your application", "application submitted"]):
            break
        time.sleep(1)

    if single_code_inp:
        print("      [Verification] Detected single code verification input box! Polling Gmail...")
        code = fetch_latest_security_code(wait_seconds=60)
        if code:
            print(f"      [Verification] Retrieved verification code: {code}! Entering code...")
            single_code_inp.click()
            single_code_inp.fill(code)
            time.sleep(1)
            v_btn = target.locator('button:has-text("VERIFY"), button:has-text("Verify"), input[value*="VERIFY" i]').first
            if v_btn.count() == 0 and target != page:
                v_btn = page.locator('button:has-text("VERIFY"), button:has-text("Verify"), input[value*="VERIFY" i]').first
            if v_btn.count() > 0 and v_btn.is_visible():
                print(f"      [Verification] Clicking '{v_btn.inner_text().strip()}' button...")
                v_btn.click(force=True)
                time.sleep(5)

    # Check for hCaptcha
    has_hcaptcha = any("hcaptcha" in f.url for f in page.frames)
    max_wait = 60 if has_hcaptcha else 15
    if has_hcaptcha:
        print("      [Verification] Detected hCaptcha challenge! Activating Chrome window and chiming...")
        try:
            import subprocess
            subprocess.run(["osascript", "-e", 'tell application "Google Chrome" to activate'], check=False)
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], check=False)
        except Exception:
            pass

    # HARD CHECK: Monitor page
    print(f"      [Hard Check] Monitoring page for verified confirmation state (up to {max_wait}s)...")
    start_time = time.time()
    confirmed = False
    confirmation_reason = ""
    error_list = []

    while time.time() - start_time < max_wait:
        time.sleep(1.5)
        curr_url = page.url.lower()

        # Check company application limit or submission failure banners FIRST
        try:
            body_text = page.locator("body").inner_text().lower()
            if hasattr(target, "locator"):
                body_text += " " + target.locator("body").inner_text().lower()
            if "flagged as possible spam" in body_text:
                error_list.append("Flagged as possible spam by ATS (anti-bot triggered)")
                break
            if any(k in body_text for k in [
                "applied for more than",
                "limit their applications",
                "limiting applications",
                "maximum number of applications",
                "reached the maximum",
                "within the last 90 days",
                "within the last 60 days",
                "within the last 30 days",
                "within 60 days",
                "within 30 days",
                "within 90 days",
                "exceeded the maximum",
                "more than 2 times in any 60 day"
            ]):
                error_list.append("Company Application Limit Reached (Max roles allowed by company policy)")
                break
            if "we couldn't submit your application" in body_text:
                error_list.append("Form submission error (field validation or required answer missing)")
                break
        except Exception:
            pass

        # 1. URL change
        if any(k in curr_url for k in ["/confirmation", "/thank_you", "/thanks", "/submitted", "/success", "submitted=true", "complete", "applysuccess=true"]):
            confirmed = True
            confirmation_reason = f"Redirected to confirmation URL: {curr_url}"
            break

        # 2. Confirmation DOM text (Strict Phrases Only)
        try:
            if any(k in body_text for k in [
                "thank you for applying",
                "thank you for your interest",
                "thanks for applying",
                "your application has been received",
                "we have received your application",
                "application submitted",
                "application received",
                "application has been submitted",
                "your application was successfully submitted",
                "your application was submitted successfully",
                "we will contact you for the next steps",
                "successfully submitted",
                "application was successfully submitted",
                "track your application",
                "delighted that you would consider",
                "view more jobs at",
                "apply now\nthank you",
                "apply now\r\nthank you"
            ]) or re.search(r'apply now\s+thank you', body_text):
                confirmed = True
                confirmation_reason = "Found verified confirmation heading in DOM"
                break
        except Exception:
            pass

        # 3. Validation errors
        error_locs = target.locator('.error, .invalid-feedback, [aria-invalid="true"], .field-error, [class*="--error"], [id$="-error"], p:has-text("This field is required"), p:has-text("is required"), div:has-text("Your form needs corrections"), [class*="banner-error"], li:has-text("Invalid value"), div:has-text("Please correct the errors")')
        if error_locs.count() == 0 and target != page:
            error_locs = page.locator('.error, .invalid-feedback, [aria-invalid="true"], .field-error, [class*="--error"], [id$="-error"], p:has-text("This field is required"), p:has-text("is required"), div:has-text("Your form needs corrections"), [class*="banner-error"], li:has-text("Invalid value"), div:has-text("Please correct the errors")')
        if error_locs.count() > 0:
            for e_idx in range(min(error_locs.count(), 5)):
                txt = error_locs.nth(e_idx).inner_text().strip()
                if txt and txt not in error_list:
                    error_list.append(txt)

    # Secondary check: verify incoming ATS auto-confirmation email in Gmail (ONLY IF no validation errors exist on page)
    if not confirmed and not error_list:
        print("      [IMAP Check] Checking Gmail for incoming ATS auto-confirmation email (up to 30s)...")
        for _ in range(6):
            email_confirm = check_fresh_confirmation_email(company, max_age_seconds=180)
            if email_confirm:
                confirmed = True
                confirmation_reason = email_confirm
                break
            time.sleep(5)

    if confirmed:
        proof = LOGS_DIR / f"submitted_hardcheck_{clean_comp}_{job_id}_{ts}.png"
        try:
            page.screenshot(path=str(proof), full_page=True)
        except Exception:
            try:
                page.screenshot(path=str(proof))
            except Exception as err:
                print(f"      [Screenshot note]: {err}")
        print(f"      >>> [HARD CHECK VERIFIED: SUBMITTED] Proof: {proof.name} ({confirmation_reason}) <<<\n")
        return {
            "status": "Submitted",
            "proof": str(proof),
            "notes": f"Hard check passed: {confirmation_reason} | Proof: {proof.name}"
        }
    else:
        err_summary = "; ".join(error_list) if error_list else "Form not submitted (page unchanged or verification required)"
        proof = LOGS_DIR / f"blocked_validation_{clean_comp}_{job_id}_{ts}.png"
        try:
            page.screenshot(path=str(proof), full_page=True)
        except Exception:
            pass
        print(f"      !!! [HARD CHECK FAILED: BLOCKED] Reason: {err_summary} | Proof: {proof.name} !!!\n")
        final_status = "Blocked - Company Limit" if "Company Application Limit Reached" in err_summary else "Blocked - Form Error"
        return {
            "status": final_status,
            "proof": str(proof),
            "notes": f"{err_summary} | Proof: {proof.name}"
        }


def process_direct_job(browser_or_context, job_record: tuple, is_persistent_context: bool = False) -> Dict[str, Any]:
    job_id, company, title, location, url, matched_resume = job_record
    print(f"\n{'='*70}")
    print(f"TARGET: [#{job_id}] {title} @ {company} ({location})")
    print(f"URL:    {url}")
    print(f"{'='*70}")

    # 1. Company Policy Gate (<= 2 applications per company, cooloffs, blacklists)
    policy_mgr = CompanyPolicyManager(DB_PATH)
    can_apply, policy_reason = policy_mgr.can_apply(company)
    if not can_apply:
        print(f"      [Company Policy Block]: {policy_reason}")
        return {
            "status": "Skipped",
            "proof": None,
            "notes": f"Skipped: {policy_reason}"
        }

    # 2. Eligibility & Seniority Gatekeeper Check
    job_post = JobPosting(
        company=company,
        title=title,
        location=location,
        url=url,
        ats_platform=ATSPlatform.GENERIC
    )
    elig = evaluate_eligibility(job_post)
    if not elig.is_eligible:
        print(f"      [Eligibility Gatekeeper Block]: {elig.reason}")
        return {
            "status": "Skipped",
            "proof": None,
            "notes": f"Ineligible: {elig.reason}"
        }

    # Deterministic resume routing based on candidate architecture
    if elig.target_resume and (BASE_DIR / elig.target_resume).exists():
        resume_path = BASE_DIR / elig.target_resume
    else:
        res_name = matched_resume or "V1_GTM_Revenue_Strategy.pdf"
        p = Path(res_name)
        if p.is_absolute() and p.exists():
            resume_path = p
        elif (BASE_DIR / "resumes" / res_name).exists():
            resume_path = BASE_DIR / "resumes" / res_name
        else:
            resume_path = BASE_DIR / "resumes" / "V1_GTM_Revenue_Strategy.pdf"
    print(f"      [Target Resume Selected]: {resume_path.name} (Matched Track: {elig.matched_track})")

    if is_persistent_context:
        page = browser_or_context.new_page()
        context = None
    else:
        context = browser_or_context.new_context(
            viewport={"width": 1280, "height": 950},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

    if Stealth:
        try:
            Stealth().apply_stealth_sync(page)
        except Exception:
            pass

    if "jobs.lever.co" in url and not url.endswith("/apply"):
        url = url.rstrip("/") + "/apply"
    if "ashbyhq.com" in url and not url.rstrip("/").endswith("/application"):
        url = url.rstrip("/") + "/application"

    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except Exception:
            page.goto(url, wait_until="load", timeout=15000)
        time.sleep(2)

        # Wait up to 6s for redirects (e.g. Greenhouse redirects to careers.company.com/jobs?gh_jid=...)
        for _ in range(6):
            if page.locator('a:has-text("APPLY NOW"), a:has-text("Apply Now"), button#form_submit_2_0, input[type="file"]').count() > 0:
                break
            time.sleep(1)

        # Check for expired/closed Greenhouse job boards (?error=true or Error 404)
        body_text_initial = ""
        try:
            body_text_initial = page.locator("body").inner_text().lower()
        except Exception:
            pass

        if "error=true" in page.url.lower() or "error 404" in body_text_initial or "can't find what you're looking for" in body_text_initial:
            clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())
            proof = LOGS_DIR / f"closed_job_{clean_comp}_{job_id}.png"
            try:
                page.screenshot(path=str(proof), full_page=True)
            except Exception:
                pass
            print(f"      [Job Closed/Expired]: Posting closed/expired by company ({page.url})")
            return {
                "status": "Closed - Position Expired",
                "proof": str(proof),
                "notes": f"Job posting closed/expired by company ({page.url})"
            }

        # Dismiss common cookie / privacy banners that block form interactions
        cookie_selectors = [
            '#consent_agree',
            'button#consent_agree',
            'button:has-text("I accept")',
            '#ketch-banner-button-primary',
            '#onetrust-accept-btn-handler',
            '#onetrust-reject-all-handler',
            'button:has-text("Accept All")',
            'button:has-text("Accept all")',
            'button:has-text("Accept Cookies")',
            'button:has-text("Accept cookies")',
            'button:has-text("Accept")',
            'button:has-text("I Agree")',
            'button:has-text("Allow all")',
            'button:has-text("Reject All")',
            'button[id*="cookie" i]:has-text("Accept")',
        ]
        for c_sel in cookie_selectors:
            cb = page.locator(c_sel)
            if cb.count() > 0 and cb.first.is_visible():
                try:
                    cb.first.click()
                    time.sleep(1)
                    break
                except Exception:
                    pass

        # Handle top-level apply buttons (e.g. company career sites embedding Greenhouse or Ashby)
        apply_btn_selectors = [
            'a[href*="/form?gh_jid="]',
            'a[href*="gh_jid="]:not([href*="#/"])',
            'a:has-text("Apply Now for")',
            'a:has-text("Apply for this position")',
            'a:has-text("Apply for this job")',
            'button:has-text("Apply for this position")',
            'button:has-text("Apply for this job")',
            'a[href*="#apply"]',
            '[role="tab"]:has-text("Application")',
            'button:has-text("Apply to job"):not(#form_submit_2_0)',
            'a:has-text("APPLY NOW"):not([href*="#/"]):not([href*="jobs.elastic.co/#/"])',
            'a:has-text("Apply Now"):not([href*="#/"]):not([href*="jobs.elastic.co/#/"])',
            'a:has-text("Apply now"):not([href*="#/"]):not([href*="jobs.elastic.co/#/"])',
            'button:has-text("APPLY NOW"):not(#form_submit_2_0)',
            'button:has-text("Apply Now"):not(#form_submit_2_0)',
            'button:has-text("Apply now"):not(#form_submit_2_0)',
            'button:has-text("Apply"):not(#form_submit_2_0)',
            'a:has-text("Apply"):not([href*="#/"]):not([href*="jobs.elastic.co/#/"])',
        ]
        for a_sel in apply_btn_selectors:
            apply_b = page.locator(a_sel)
            if apply_b.count() > 0 and apply_b.first.is_visible():
                try:
                    print(f"      [Portal Nav] Clicking apply button: {a_sel}")
                    apply_b.first.click(force=True)
                    time.sleep(3)
                    break
                except Exception:
                    pass

        # Ensure scroll to reveal lazy elements
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            time.sleep(1)
        except Exception:
            pass

        # Check for iframe (MongoDB, HighRadius, Zenoti, PubMatic, Fivetran, Toast, Payoneer)
        grnhse_frame = None
        if "greenhouse.io" not in page.url:
            for _ in range(8):
                for f in page.frames:
                    if f != page.main_frame and (f.name == "grnhse_iframe" or "job-boards.greenhouse.io" in f.url or "boards.greenhouse.io" in f.url):
                        grnhse_frame = f
                        break
                if grnhse_frame:
                    break
                iframe_elem = page.locator("iframe#grnhse_iframe, iframe[src*='greenhouse.io']").first
                if iframe_elem.count() > 0:
                    try:
                        grnhse_frame = iframe_elem.content_frame()
                        if grnhse_frame:
                            break
                    except Exception:
                        pass
                time.sleep(1)
        target_ctx = grnhse_frame if grnhse_frame else page

        # Detect portal type
        if "kula.ai" in page.url or "kula" in page.url:
            fill_kula_application(page, resume_path, company, title)
        elif "ashbyhq.com" in page.url or "ashby" in page.url:
            fill_ashby_application(page, resume_path, company, title)
        elif "jobs.lever.co" in page.url or "lever.co" in page.url:
            fill_lever_application(page, resume_path, company, title)
        else:
            # Greenhouse or standard portal
            if target_ctx.locator('input[type="file"]').count() == 0:
                for a_sel in ['a:has-text("APPLY NOW")', 'a:has-text("Apply Now")', 'a[href*="#apply"]']:
                    ab = page.locator(a_sel).first
                    if ab.count() > 0 and ab.is_visible():
                        ab.click()
                        time.sleep(2.5)
                        break
            fill_greenhouse_application(target_ctx, resume_path, company, title)

        result = execute_hard_check_submission(target_ctx, page, company, job_id)
        return result
    except Exception as e:
        clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())
        proof = LOGS_DIR / f"blocked_error_{clean_comp}_{job_id}.png"
        try:
            page.screenshot(path=str(proof), full_page=True)
        except Exception:
            pass
        print(f"      [Exception occurred]: {e}")
        return {
            "status": "Blocked - System Error",
            "proof": str(proof),
            "notes": f"Error during run: {str(e)[:100]}"
        }
    finally:
        try:
            page.close()
        except Exception:
            pass
        if context:
            try:
                context.close()
            except Exception:
                pass


def run_batch(limit: int = 10, priority: Optional[str] = None, company: Optional[str] = None, job_id: Optional[int] = None, filter_ats: Optional[str] = None, headful: bool = False):
    print("=" * 70)
    print("       STRICT HARD-CHECK DIRECT ATS SUBMISSION ENGINE")
    print(f"Candidate: {CANDIDATE['full_name']} | Phone: {CANDIDATE['phone']} | Email: {CANDIDATE['email']}")
    print("=" * 70)

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        query = """
            SELECT id, company, title, location, url, matched_resume
            FROM jobs
            WHERE (LOWER(board_type) LIKE 'direct%' OR LOWER(board_type) IN ('ashby', 'greenhouse', 'lever')) 
              AND status NOT IN ('Submitted', 'Duplicate', 'Closed - Position Expired')
        """
        params = []
        if job_id:
            query += " AND id = ?"
            params.append(job_id)
        elif company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
        elif filter_ats:
            if filter_ats.lower() == "greenhouse":
                query += " AND url LIKE '%greenhouse%'"
            elif filter_ats.lower() == "ashby":
                query += " AND url LIKE '%ashby%'"
            elif filter_ats.lower() == "lever":
                query += " AND url LIKE '%lever.co%'"
        elif priority == "Remote":
            query += " AND (location LIKE '%Remote%' OR location LIKE '%Worldwide%')"
        elif priority == "Hyderabad":
            query += " AND location LIKE '%Hyderabad%'"
        elif priority == "Bengaluru":
            query += " AND (location LIKE '%Bengaluru%' OR location LIKE '%Bangalore%')"
        elif priority == "Gurugram":
            query += " AND (location LIKE '%Gurugram%' OR location LIKE '%Gurgaon%' OR location LIKE '%Noida%' OR location LIKE '%Delhi%')"

        query += " ORDER BY CASE WHEN status IN ('Found', 'Pending', 'Pre-filled') THEN 0 ELSE 1 END, id ASC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        jobs = c.fetchall()

    filt_desc = f"Job #{job_id}" if job_id else (f"Company '{company}'" if company else (f"ATS '{filter_ats}'" if filter_ats else (priority or "All")))
    print(f"Found {len(jobs)} jobs ready for hard-check processing (Filter: {filt_desc}).")
    if not jobs:
        print("No pending direct jobs found for this filter.")
        return

    with sync_playwright() as p:
        has_ashby_or_lever = any("ashbyhq.com" in j[4] or "lever.co" in j[4] for j in jobs)
        use_headful = headful or has_ashby_or_lever
        
        if use_headful:
            profile_dir = os.path.expanduser(f"~/.chrome_ashby_profile_{priority or 'default'}")
            os.makedirs(profile_dir, exist_ok=True)
            context = p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                viewport={"width": 1280, "height": 950}
            )
            browser = None
        else:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            context = None

        for job in jobs:
            job_id = job[0]
            target_instance = context if context else browser
            res = process_direct_job(target_instance, job, is_persistent_context=(context is not None))

            # Update DB with strict verification result
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                c.execute("""
                    UPDATE jobs
                    SET status = ?, notes = ?, date_updated = ?
                    WHERE id = ?
                """, (res["status"], res["notes"], now, job_id))
                conn.commit()

            print(f"Updated #{job_id}: Status -> '{res['status']}'")

        if context:
            try:
                context.close()
            except Exception:
                pass
        elif browser:
            try:
                browser.close()
            except Exception:
                pass

    print("\nBatch execution complete. Syncing to Excel...")
    try:
        from scripts.export_excel import export_tracker_to_excel
        export_tracker_to_excel()
    except Exception as e:
        print(f"Excel sync note: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="Number of jobs to process")
    parser.add_argument("--priority", type=str, default=None, choices=["Remote", "Hyderabad", "Bengaluru", "Gurugram"], help="Priority filter")
    parser.add_argument("--company", type=str, default=None, help="Filter by company name")
    parser.add_argument("--job-id", type=int, default=None, help="Process a specific job ID")
    parser.add_argument("--filter-ats", type=str, default=None, choices=["greenhouse", "ashby", "lever"], help="Filter by ATS platform")
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode")
    args = parser.parse_args()

    run_batch(limit=args.limit, priority=args.priority, company=args.company, job_id=args.job_id, filter_ats=args.filter_ats, headful=args.headful)
