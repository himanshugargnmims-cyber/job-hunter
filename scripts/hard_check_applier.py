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


def fetch_latest_security_code(wait_seconds: int = 40) -> Optional[str]:
    """Scans Gmail IMAP for a fresh, un-used security code from Greenhouse received recently."""
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
            mail.select('"[Gmail]/All Mail"')
            status, data = mail.search(None, 'FROM "us.greenhouse-mail.io"')
            if data[0]:
                msg_ids = data[0].split()
                for mid in reversed(msg_ids[-5:]):
                    status, mdata = mail.fetch(mid, "(RFC822)")
                    msg = email.message_from_bytes(mdata[0][1])
                    
                    # Verify message timestamp is fresh (within last 180s)
                    date_hdr = msg.get("Date")
                    if date_hdr:
                        try:
                            msg_time = email.utils.parsedate_to_datetime(date_hdr).timestamp()
                            if time.time() - msg_time > 180:
                                continue
                        except Exception:
                            pass

                    for part in msg.walk():
                        if part.get_content_type() in ["text/html"]:
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            code = None
                            m_h1 = re.findall(r'<h1[^>]*>\s*([A-Za-z0-9]{8})\s*</h1>', body)
                            if m_h1:
                                code = m_h1[0].strip()
                            else:
                                m_txt = re.findall(r'application:\s*\n+\s*([A-Za-z0-9]{8})', body)
                                if m_txt:
                                    code = m_txt[0].strip()

                            if code and code not in seen_codes:
                                record_seen_otp_code(code)
                                mail.logout()
                                return code
            mail.logout()
        except Exception:
            pass
        time.sleep(2)
    return None


def fill_greenhouse_application(target: Union[Page, Frame], resume_path: Path, company: str, job_title: str) -> None:
    """Fills Greenhouse ATS application forms with full React-Select, multi-pass EEO, and autocomplete support."""
    print("      [1/6] Attaching resume...")
    file_inputs = target.locator('input[type="file"]')
    if file_inputs.count() > 0 and resume_path.exists():
        try:
            file_inputs.first.set_input_files(str(resume_path))
            time.sleep(2)
            print(f"            Attached resume: {resume_path.name}")
        except Exception as e:
            print(f"            Resume upload note: {e}")

    print("      [2/6] Filling text and contact fields...")
    for fn in target.locator('input[id*="first_name" i], input[name*="first_name" i]').all():
        if fn.is_visible():
            fn.fill(CANDIDATE["first_name"])
            break

    for ln in target.locator('input[id*="last_name" i], input[name*="last_name" i]').all():
        if ln.is_visible():
            ln.fill(CANDIDATE["last_name"])
            break

    for em in target.locator('input[id*="email" i], input[name*="email" i]').all():
        if em.is_visible():
            em.fill(CANDIDATE["email"])
            break

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
    for ph in target.locator('input[id*="phone" i], input[name*="phone" i]').all():
        if ph.is_visible():
            ph.fill(CANDIDATE["phone_digits"])
            print(f"            Filled Phone: {CANDIDATE['phone_digits']}")
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
        if not inp.is_visible() or inp.input_value():
            continue
        cls = inp.get_attribute("class") or ""
        if "select__input" in cls:
            continue
        inp_id = (inp.get_attribute("id") or "").lower()
        lbl = inp.evaluate('''e => {
            let id = e.id;
            let l = id ? document.querySelector(`label[for="${id}"]`) : null;
            let p = e.closest("div");
            return ((l ? l.innerText : "") + " " + (p ? p.innerText : "")).toLowerCase();
        }''')
        if "linkedin" in lbl:
            inp.fill(CANDIDATE["linkedin"])
        elif "start" in lbl and "year" in lbl or "start-date-year" in inp_id:
            inp.fill("2021")
        elif "end" in lbl and "year" in lbl or "end-date-year" in inp_id:
            inp.fill("2026")
        elif "prefer" in lbl and "name" in lbl:
            inp.fill(CANDIDATE["first_name"])
        elif "adjustment" in lbl or "inclusive" in lbl or "accessible" in lbl:
            inp.fill("None required. Thank you.")
        elif "company" in lbl or "employer" in lbl or "company-name" in inp_id:
            inp.fill(CANDIDATE["current_company"])
        elif "title" in lbl or "designation" in lbl:
            inp.fill(CANDIDATE["current_title"])
        elif "notice" in lbl or "available" in lbl or "availability" in lbl:
            inp.fill("30 days")
        elif "city" in lbl or "location" in lbl:
            inp.fill("Bengaluru")
        elif "expected" in lbl and ("ctc" in lbl or "salary" in lbl or "compensation" in lbl):
            if inp.get_attribute("type") == "number":
                inp.fill("5500000")
            else:
                inp.fill("55 LPA (Flexible)")
        elif "current" in lbl and ("ctc" in lbl or "salary" in lbl or "compensation" in lbl):
            if inp.get_attribute("type") == "number":
                inp.fill("4000000")
            else:
                inp.fill("40 LPA")
        elif "ctc" in lbl or "salary" in lbl or "compensation" in lbl or "fixed" in lbl:
            if inp.get_attribute("type") == "number":
                inp.fill("5500000")
            else:
                inp.fill("55 LPA")
        elif "experience" in lbl or "exp" in lbl:
            inp.fill(CANDIDATE["total_years_exp"])
        elif "website" in lbl or "url" in lbl or "portfolio" in lbl:
            inp.fill(CANDIDATE["linkedin"])
        else:
            inp.fill("N/A")

    print("      [3/6] Populating React-Select controls (multi-pass for dynamic EEO)...")
    for p_round in range(3):
        unfilled_controls = []
        for ctrl in target.locator('.select__control').all():
            val = ctrl.inner_text().strip()
            if val in ["", "Select..."] or val.startswith("Select"):
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
                ctrl.click()
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
                elif any(k in parent_text for k in ["sponsorship", "require a work permit", "require visa", "require sponsorship", "need sponsorship", "additional right to work support", "sponsor"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["no", "not require", "do not", "never"]) and not any(k in o.inner_text().lower() for k in ["yes", "require sponsorship"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower().startswith("no")), None)
                elif any(k in parent_text for k in ["legal right to work", "authorized to work", "eligible to work", "legally authorized", "authorized in the location", "work authorization"]) and not any(k in parent_text for k in ["sponsor", "require"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "authorized"]) and not any(k in o.inner_text().lower() for k in ["no", "not authorized"])), None)
                elif any(k in parent_text for k in ["currently work", "previously worked", "employed by", "worked at", "former employee", "current employee", "have you worked", "previously been employed", "employee"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["never worked", "no, i have never", "no, i do not", "no", "external applicant"])), None)
                    if not chosen:
                        chosen = next((o for o in opts if o.inner_text().strip().lower() == "no"), None)
                elif any(k in parent_text for k in ["procurement", "contract award", "government employee", "government official", "conflict of interest", "non-compete", "restriction", "relative", "family member", "outside business activity", "referred to this position"]):
                    chosen = next((o for o in opts if o.inner_text().strip().lower() in ["no", "no, i have not", "none", "no, i do not"]), None)
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
                elif any(k in parent_text for k in ["bachelor's degree", "years of software", "lead experience", "building and deploying", "orchestration", "rag systems", "backend engineering", "aws experience", "years of experience", "project manager", "5+ years", "experience being a"]):
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
                elif any(k in parent_text for k in ["agreement", "restriction", "sponsorship", "visa"]):
                    chosen = next((o for o in opts if o.inner_text().strip() == "No"), None)
                elif "authorized" in parent_text or "eligible" in parent_text:
                    chosen = next((o for o in opts if o.inner_text().strip() == "Yes"), None)
                elif any(k in parent_text for k in ["learn", "how did you", "source", "hear about", "where have you learned"]):
                    chosen = next((o for o in opts if "linkedin" in o.inner_text().lower() or "website" in o.inner_text().lower()), None)
                elif any(k in parent_text for k in ["alerts", "updates", "stay up to date", "marketing"]):
                    chosen = next((o for o in opts if o.inner_text().strip() == "No"), None)
                elif any(k in parent_text for k in ["plagiarism", "original", "agree", "consent", "confirm", "certify", "processing of personal data", "privacy notice"]):
                    chosen = next((o for o in opts if any(k in o.inner_text().lower() for k in ["yes", "acknowledge", "agree", "consent"])), None)

                if chosen:
                    chosen_val = chosen.inner_text().strip()
                    chosen.click()
                    print(f"            Selected [{chosen_val}] for: {parent_text[:35].replace(chr(10), ' ')}")
                else:
                    # Safe fallback: avoid accidentally picking 'Yes' for veteran, disability, employee, or conflict
                    if any(k in parent_text for k in ["veteran", "disability", "currently work", "employed", "employee", "work", "government", "conflict"]):
                        safe_opts = [o for o in opts if not any(k in o.inner_text().lower() for k in ["yes", "active", "currently work", "current employee"])]
                        fallback_opt = safe_opts[0] if safe_opts else opts[0]
                    else:
                        fallback_opt = opts[0]
                    first_val = fallback_opt.inner_text().strip()
                    fallback_opt.click()
                    print(f"            Fallback selected [{first_val}] for: {parent_text[:35].replace(chr(10), ' ')}")
                time.sleep(0.4)
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

    # Check for secondary file inputs (e.g. Website/Portfolio attachment, cover letter)
    all_files = page.locator('input[type="file"]').all()
    if len(all_files) > 1 and resume_path.exists():
        for f_idx, extra_f in enumerate(all_files[1:], start=1):
            try:
                parent_text = extra_f.evaluate('el => el.closest("div")?.innerText || ""')
                if not any(k in parent_text.lower() for k in ["replace", "v6_operations", ".pdf"]):
                    extra_f.set_input_files(str(resume_path))
                    print(f"            Uploaded document to secondary file input #{f_idx}")
                    time.sleep(1.0)
            except Exception:
                pass

    print("      [2/5] Filling Ashby basic details...")
    name_inp = page.locator('input[name="_systemfield_name"], input[id*="name" i]').first
    if name_inp.count() > 0:
        name_inp.click()
        name_inp.fill(CANDIDATE["full_name"])
        page.keyboard.press("Tab")
        time.sleep(0.3)

    first_name_inp = page.locator('input[name*="firstName" i], input[id*="firstName" i]').first
    if first_name_inp.count() > 0 and not first_name_inp.input_value():
        first_name_inp.click()
        first_name_inp.fill(CANDIDATE["first_name"])
        page.keyboard.press("Tab")
        time.sleep(0.3)

    last_name_inp = page.locator('input[name*="lastName" i], input[id*="lastName" i]').first
    if last_name_inp.count() > 0 and not last_name_inp.input_value():
        last_name_inp.click()
        last_name_inp.fill(CANDIDATE["last_name"])
        page.keyboard.press("Tab")
        time.sleep(0.3)

    email_inp = page.locator('input[name="_systemfield_email"], input[id*="email" i], input[type="email"]').first
    if email_inp.count() > 0:
        email_inp.click()
        email_inp.fill(CANDIDATE["email"])
        page.keyboard.press("Tab")
        time.sleep(0.3)

    phone_inp = page.locator('input[name="_systemfield_phoneNumber"], input[type="tel"], input[name*="phone" i], input[id*="phone" i]').first
    if phone_inp.count() > 0 and not phone_inp.input_value():
        phone_inp.click()
        phone_inp.fill(CANDIDATE["phone"])
        page.keyboard.press("Tab")
        time.sleep(0.3)

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
            elif any(k in parent_text for k in ["office", "in-person", "relocate", "authorized", "eligible", "18 years", "experience", "timezone", "legally authorised", "legally authorized", "minimum of", "foster city", "bay area", "open to reloc"]):
                yes_btn = yn.locator('button[data-option="yes"]').first
                if yes_btn.count() > 0:
                    yes_btn.scroll_into_view_if_needed()
                    yes_btn.hover()
                    time.sleep(0.2)
                    yes_btn.click()
                    print(f"            Ashby Yes/No: Selected [Yes] for: {parent_text.split(chr(10))[0][:40]}")
            else:
                if any(k in parent_text for k in ["restriction", "conflict", "felony", "misconduct"]):
                    no_btn = yn.locator('button[data-option="no"]').first
                    if no_btn.count() > 0:
                        no_btn.click()
                else:
                    yes_btn = yn.locator('button[data-option="yes"]').first
                    if yes_btn.count() > 0:
                        yes_btn.scroll_into_view_if_needed()
                        yes_btn.hover()
                        time.sleep(0.2)
                        yes_btn.click()
            time.sleep(0.3)
        except Exception:
            pass

    # 4b. Field entries (inputs, textareas, file uploads)
    context_notes = load_default_context_notes()
    for entry in page.locator('.ashby-application-form-field-entry').all():
        try:
            lbl = entry.locator('label.ashby-application-form-question-title').first
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
                elif any(k in txt_l for k in ["employer", "company"]):
                    inp.fill(CANDIDATE["current_company"])
                elif any(k in txt_l for k in ["school", "university"]):
                    inp.fill(CANDIDATE["school"])
                elif any(k in txt_l for k in ["pronoun"]):
                    inp.fill("He/Him")
                elif any(k in txt_l for k in ["preferred name", "preferred first", "preferred"]):
                    inp.fill(CANDIDATE["first_name"])
                elif any(k in txt_l for k in ["preferred last"]):
                    inp.fill(CANDIDATE["last_name"])
                elif any(k in txt_l for k in ["legal first and last", "full name"]):
                    inp.fill(CANDIDATE["full_name"])
                elif any(k in txt_l for k in ["country", "based in"]):
                    inp.fill(CANDIDATE.get("country", "India"))
                elif any(k in txt_l for k in ["notice", "days"]):
                    if inp_type == "number":
                        inp.fill(CANDIDATE.get("notice_period", "30"))
                    else:
                        inp.fill(f"{CANDIDATE.get('notice_period', '30')} days")
                elif any(k in txt_l for k in ["salary", "compensation"]):
                    if inp_type == "number":
                        inp.fill("5000000")
                    else:
                        inp.fill(CANDIDATE.get("compensation", "Competitive / Flexible"))
                elif any(k in txt_l for k in ["experience", "years"]) and inp_type == "number":
                    inp.fill(CANDIDATE.get("total_years_exp", "5"))
                elif any(k in txt_l for k in ["twitter", "x handle", "if other", "specify below"]):
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

            # Fallback
            if not chosen_tuple and choices:
                if any(k in g_lower for k in ["conflict", "felony", "misconduct", "restriction", "non-compete", "employee", "previous", "previously", "referred", "work for", "worked at"]):
                    for c in choices:
                        if c[2].startswith("no"):
                            chosen_tuple = c
                            break
                else:
                    for c in choices:
                        if c[2].startswith("yes"):
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
    name_inp = page.locator('input[name="name"]').first
    if name_inp.count() > 0 and not name_inp.input_value():
        name_inp.fill(CANDIDATE["full_name"])

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
    li_inp = page.locator('input[name*="LinkedIn"]').first
    if li_inp.count() > 0:
        li_inp.fill(CANDIDATE["linkedin"])

    gh_inp = page.locator('input[name*="GitHub"]').first
    if gh_inp.count() > 0:
        gh_inp.fill(CANDIDATE.get("github") or CANDIDATE.get("linkedin"))

    port_inp = page.locator('input[name*="Portfolio"]').first
    if port_inp.count() > 0:
        port_inp.fill(CANDIDATE.get("portfolio") or CANDIDATE.get("linkedin"))

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
                    if any(loc in opt.inner_text().lower() for loc in ["bangalore", "bengaluru", "india"]):
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
                ans = answer_custom_question(q_text, context_notes)
                ta.fill(ans)
                continue

            inp = q.locator('input[type="text"]').first
            if inp.count() > 0 and inp.is_visible() and not inp.input_value():
                inp_name = (inp.get_attribute("name") or "").lower()
                if any(k in inp_name for k in ["urls[", "eeo[", "phone", "email", "location", "org", "name"]):
                    continue
                ans = answer_custom_question(q_text, context_notes)
                inp.fill(ans[:150])
                continue

            radios = q.locator('input[type="radio"]').all()
            if radios:
                if any(k in q_lower for k in ["sponsorship", "require visa", "visa support"]):
                    no_r = next((r for r in radios if "no" in (r.evaluate('e => e.closest("label")?.innerText || ""').lower())), None)
                    if no_r:
                        no_r.check(force=True)
                elif any(k in q_lower for k in ["authorized", "eligible", "right to work", "18 years"]):
                    yes_r = next((r for r in radios if "yes" in (r.evaluate('e => e.closest("label")?.innerText || ""').lower())), None)
                    if yes_r:
                        yes_r.check(force=True)
        except Exception:
            pass

    for cb in page.locator('input[type="checkbox"]').all():
        try:
            if not cb.is_checked():
                cb.check(force=True)
        except Exception:
            pass

    time.sleep(1)


def execute_hard_check_submission(target: Union[Page, Frame], page: Page, company: str, job_id: int) -> Dict[str, Any]:
    """Submits the form, handles OTP if prompted, and verifies unambiguous confirmation signal."""
    clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', company.lower())
    ts = time.strftime("%Y%m%d_%H%M%S")

    submit_btn = target.locator('button.ashby-application-form-submit-button, form button[type="submit"], button#btn-submit, button#submit_app, button[type="submit"], input[type="submit"]').first
    if submit_btn.count() == 0 or not submit_btn.is_visible():
        submit_btn = target.locator('button:has-text("Submit application"), button:has-text("Submit Application"), button:has-text("SUBMIT APPLICATION")').first
    if submit_btn.count() == 0 or not submit_btn.is_visible():
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
        submit_btn.hover()
        time.sleep(0.5)
        submit_btn.click()
    except Exception:
        submit_btn.click(force=True)
    time.sleep(3)

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
            is_disabled = final_submit_btn.get_attribute("disabled") is not None or "disabled" in (final_submit_btn.get_attribute("class") or "")
            if not is_disabled:
                print("      [Verification] Submit button enabled! Submitting verified application...")
                final_submit_btn.click(force=True)
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
            if any(k in body_text for k in [
                "we couldn't submit your application",
                "applied for more than",
                "limit their applications",
                "application limit"
            ]):
                error_list.append("Company Application Limit Reached (Max roles allowed by company policy)")
                break
            if "flagged as possible spam" in body_text:
                error_list.append("Flagged as possible spam by ATS")
                break
        except Exception:
            pass

        # 1. URL change
        if any(k in curr_url for k in ["/confirmation", "/thank_you", "/thanks", "/submitted", "/success", "submitted=true", "complete"]):
            confirmed = True
            confirmation_reason = f"Redirected to confirmation URL: {curr_url}"
            break

        # 2. Confirmation DOM text
        try:
            if any(k in body_text for k in [
                "thank you for applying",
                "your application has been received",
                "we have received your application",
                "application submitted",
                "application received",
                "thank you!",
                "application has been submitted",
                "your application was successfully submitted",
                "successfully submitted",
                "application was successfully submitted"
            ]):
                confirmed = True
                confirmation_reason = "Found verified confirmation heading in DOM"
                break
        except Exception:
            pass

        # 3. Validation errors
        error_locs = target.locator('.error, .invalid-feedback, [aria-invalid="true"], .field-error, p:has-text("This field is required")')
        if error_locs.count() > 0:
            for e_idx in range(min(error_locs.count(), 5)):
                txt = error_locs.nth(e_idx).inner_text().strip()
                if txt and txt not in error_list:
                    error_list.append(txt)

    if confirmed:
        proof = LOGS_DIR / f"submitted_hardcheck_{clean_comp}_{job_id}_{ts}.png"
        try:
            page.screenshot(path=str(proof), full_page=True)
        except Exception:
            pass
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

    res_name = matched_resume or "V3_Strategy_Ops_ChiefOfStaff.pdf"
    resume_path = BASE_DIR / "resumes" / res_name
    if not resume_path.exists():
        resume_path = BASE_DIR / "resumes" / "V1_GTM_Revenue_Strategy.pdf"

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
        if "jobs.lever.co" in url:
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
        else:
            try:
                page.goto(url, wait_until="networkidle", timeout=35000)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=15000)
        time.sleep(2)

        # Handle top-level apply buttons
        if "greenhouse.io" not in page.url and "ashbyhq.com" not in page.url and "jobs.lever.co" not in page.url:
            apply_btns = page.locator('a:has-text("Apply"), button:has-text("Apply"), a:has-text("Apply Now")')
            if apply_btns.count() > 0 and apply_btns.first.is_visible():
                try:
                    apply_btns.first.click()
                    time.sleep(2.5)
                except Exception:
                    pass

        # Ensure scroll to reveal lazy elements
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
            time.sleep(1)
        except Exception:
            pass

        # Check for iframe (MongoDB, HighRadius, Zenoti)
        grnhse_frame = None
        for f in page.frames:
            if f.name == "grnhse_iframe" or "greenhouse.io" in f.url:
                grnhse_frame = f
                break
        if not grnhse_frame:
            iframe_elem = page.locator("iframe#grnhse_iframe, iframe[src*='greenhouse.io']").first
            if iframe_elem.count() > 0:
                try:
                    grnhse_frame = iframe_elem.content_frame()
                except Exception:
                    pass
        target_ctx = grnhse_frame if grnhse_frame else page

        # Detect portal type
        if "ashbyhq.com" in page.url or "ashby" in page.url:
            fill_ashby_application(page, resume_path, company, title)
        elif "jobs.lever.co" in page.url or "lever.co" in page.url:
            fill_lever_application(page, resume_path, company, title)
        else:
            # Greenhouse or standard portal
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


def run_batch(limit: int = 10, priority: Optional[str] = None, company: Optional[str] = None, job_id: Optional[int] = None, headful: bool = False):
    print("=" * 70)
    print("       STRICT HARD-CHECK DIRECT ATS SUBMISSION ENGINE")
    print(f"Candidate: {CANDIDATE['full_name']} | Phone: {CANDIDATE['phone']} | Email: {CANDIDATE['email']}")
    print("=" * 70)

    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        query = """
            SELECT id, company, title, location, url, matched_resume
            FROM jobs
            WHERE board_type LIKE 'Direct%' AND status != 'Submitted' AND status != 'Duplicate'
        """
        params = []
        if job_id:
            query += " AND id = ?"
            params.append(job_id)
        elif company:
            query += " AND company LIKE ?"
            params.append(f"%{company}%")
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

    filt_desc = f"Job #{job_id}" if job_id else (f"Company '{company}'" if company else (priority or "All"))
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
    parser.add_argument("--headful", action="store_true", help="Run browser in headful mode")
    args = parser.parse_args()

    run_batch(limit=args.limit, priority=args.priority, company=args.company, job_id=args.job_id, headful=args.headful)
