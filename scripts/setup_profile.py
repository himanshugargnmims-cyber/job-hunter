#!/usr/bin/env python3
"""
setup_profile.py - Interactive Onboarding & Candidate Configuration Wizard

Guides any user step-by-step:
1. Ingests candidate resume (PDF or TXT) and auto-detects profile details (Email, Phone, Name, Links).
2. Prompts for all configurable variables (Contact, Work Auth, Notice Period, CTC, Salary Floor, Target Roles, Locations).
3. Generates all required configuration files:
   - context/screening_qa.json
   - context/preferences.json
   - context/profile_notes.md
   - context/company_list.txt
   - .env
"""

import os
import sys
import re
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
CONTEXT_DIR = BASE_DIR / "context"
RESUMES_DIR = BASE_DIR / "resumes"
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

for d in [CONTEXT_DIR, RESUMES_DIR, DATA_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def extract_text_from_file(file_path: Path) -> str:
    """Extracts text from PDF or TXT resume."""
    if not file_path.exists():
        return ""
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            text = ""
            for page in reader.pages:
                text += (page.extract_text() or "") + "\n"
            return text.strip()
        except Exception as e:
            print(f"[Warning] PDF text extraction error: {e}")
            return ""
    else:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read().strip()
        except Exception as e:
            print(f"[Warning] Text file read error: {e}")
            return ""


def parse_resume_heuristics(text: str) -> Dict[str, str]:
    """Auto-detects contact details, links, and names using regex heuristics."""
    data = {}
    if not text:
        return data

    # 1. Email detection
    email_match = re.search(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    if email_match:
        data["email"] = email_match.group(0).strip()

    # 2. Phone detection
    phone_match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    if phone_match:
        data["phone"] = phone_match.group(0).strip()

    # 3. LinkedIn detection
    li_match = re.search(r'(https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+)', text, re.IGNORECASE)
    if li_match:
        data["linkedin_url"] = li_match.group(0).strip()
    else:
        li_short = re.search(r'(linkedin\.com/in/[a-zA-Z0-9_-]+)', text, re.IGNORECASE)
        if li_short:
            data["linkedin_url"] = "https://" + li_short.group(0).strip()

    # 4. GitHub / Portfolio detection
    gh_match = re.search(r'(https?://(?:www\.)?github\.com/[a-zA-Z0-9_-]+)', text, re.IGNORECASE)
    if gh_match:
        data["github_url"] = gh_match.group(0).strip()

    # 5. Full name candidate heuristic (first non-empty line with 2-4 words)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:5]:
        words = line.split()
        if 2 <= len(words) <= 4 and all(w[0].isupper() for w in words if w.isalpha()):
            if not any(k in line.lower() for k in ["curriculum", "resume", "cv", "page", "summary"]):
                data["full_name"] = line
                break

    return data


def prompt_user(label: str, default: str = "") -> str:
    """Prompt user with default value fallback."""
    if default:
        res = input(f"{label} [{default}]: ").strip()
        return res if res else default
    else:
        return input(f"{label}: ").strip()


def prompt_list(label: str, default_list: list) -> list:
    """Prompt user for comma-separated list."""
    default_str = ", ".join(default_list)
    val = prompt_user(label, default_str)
    return [item.strip() for item in val.split(",") if item.strip()]


def main():
    print("=" * 72)
    print("   JOB HUNTER — AUTOMATED ONBOARDING & PROFILE CONFIGURATION WIZARD")
    print("=" * 72)
    print("This wizard configures your candidate profile, resume routing, and job search filters.")
    print("All personal and career variables are fully customizable.\n")

    # ----------------------------------------------------
    # STEP 1: RESUME INTAKE
    # ----------------------------------------------------
    print("[Step 1/5] Resume File Selection & Ingestion")
    print("-" * 50)
    
    existing_resumes = list(RESUMES_DIR.glob("*.pdf")) + list(RESUMES_DIR.glob("*.txt"))
    resume_path_str = ""
    
    if existing_resumes:
        print("Discovered files in resumes/ directory:")
        for idx, r in enumerate(existing_resumes):
            print(f"  [{idx + 1}] {r.name}")
        choice = input(f"Select resume [1-{len(existing_resumes)}] or enter a custom path [1]: ").strip()
        if not choice:
            resume_path = existing_resumes[0]
        elif choice.isdigit() and 1 <= int(choice) <= len(existing_resumes):
            resume_path = existing_resumes[int(choice) - 1]
        else:
            resume_path = Path(choice).resolve()
    else:
        sample_path = RESUMES_DIR / "sample_resume.txt"
        custom_input = input(f"Enter path to your resume file (.pdf or .txt) [{sample_path}]: ").strip()
        resume_path = Path(custom_input).resolve() if custom_input else sample_path

    detected = {}
    resume_text = ""
    if resume_path.exists():
        print(f"-> Reading resume: {resume_path.name}")
        resume_text = extract_text_from_file(resume_path)
        detected = parse_resume_heuristics(resume_text)
        if detected:
            print("-> Successfully auto-detected candidate fields from resume!")
            for k, v in detected.items():
                print(f"   • {k}: {v}")
    else:
        print(f"[Notice] File not found at {resume_path}. Proceeding with manual input.")

    # ----------------------------------------------------
    # STEP 2: CANDIDATE PROFILE & SCREENING VARIABLES
    # ----------------------------------------------------
    print("\n[Step 2/5] Candidate Identity & Screening Details")
    print("-" * 50)

    # Load existing or example defaults
    curr_qa = {}
    qa_path = CONTEXT_DIR / "screening_qa.json"
    qa_ex = CONTEXT_DIR / "screening_qa.example.json"
    target_qa_read = qa_path if qa_path.exists() else qa_ex
    if target_qa_read.exists():
        try:
            with open(target_qa_read, "r", encoding="utf-8") as f:
                curr_qa = json.load(f)
        except Exception:
            pass

    full_name = prompt_user("Full Name", detected.get("full_name") or curr_qa.get("full_name", "Jane Doe"))
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else "Jane"
    last_name = name_parts[-1] if len(name_parts) > 1 else ""

    email = prompt_user("Email Address", detected.get("email") or curr_qa.get("email", "candidate@example.com"))
    phone = prompt_user("Phone Number (with country code)", detected.get("phone") or curr_qa.get("phone", "+1 555-0100"))
    location = prompt_user("Current Location (City, Country)", curr_qa.get("location", "Remote"))
    willing_relocate = prompt_user("Willing to Relocate?", curr_qa.get("willing_to_relocate", "Yes (Remote, New York, London, Bengaluru)"))
    work_auth = prompt_user("Work Authorization & Citizenship Status", curr_qa.get("work_authorization_india", curr_qa.get("work_authorization_us", "Fully authorized to work / Citizen")))
    requires_sponsorship = prompt_user("Requires Employer Visa Sponsorship? (Yes/No)", curr_qa.get("requires_sponsorship", "No"))
    notice_period = prompt_user("Notice Period (e.g. Immediate, 15 Days, 30 Days)", curr_qa.get("current_notice_period", "30 Days"))

    screening_ans = curr_qa.get("screening_answers", {})
    current_company = prompt_user("Current / Most Recent Company", screening_ans.get("current_company", "Tech Innovations Inc."))
    current_title = prompt_user("Current / Most Recent Title", screening_ans.get("current_title", "Senior Strategy & Operations Lead"))
    years_exp = prompt_user("Total Years of Professional Experience", str(screening_ans.get("total_years_experience", "6")))
    try:
        years_exp_num = int(years_exp)
    except ValueError:
        years_exp_num = 6

    current_ctc = prompt_user("Current CTC / Annual Salary (in local currency digits)", str(screening_ans.get("current_ctc", "4000000")))
    expected_ctc = prompt_user("Expected CTC / Annual Salary (in local currency digits)", str(screening_ans.get("expected_ctc", "5500000")))
    compensation_note = prompt_user("Compensation Summary Note", screening_ans.get("compensation", "Competitive market rate based on role mandate and scope."))
    summary = prompt_user("Executive Profile Summary (1-2 sentences)", screening_ans.get("summary", "Accomplished cross-functional leader with extensive experience driving strategic business growth and operating rigor."))

    linkedin_url = prompt_user("LinkedIn Profile URL", detected.get("linkedin_url") or curr_qa.get("linkedin_url", "https://linkedin.com/in/your-profile"))
    github_url = prompt_user("GitHub / Portfolio URL", detected.get("github_url") or curr_qa.get("github_portfolio_url", ""))

    # ----------------------------------------------------
    # STEP 3: SEARCH PREFERENCES & MATCHING FILTERS
    # ----------------------------------------------------
    print("\n[Step 3/5] Job Search Preferences & Filters")
    print("-" * 50)

    curr_pref = {}
    pref_path = CONTEXT_DIR / "preferences.json"
    pref_ex = CONTEXT_DIR / "preferences.example.json"
    target_pref_read = pref_path if pref_path.exists() else pref_ex
    if target_pref_read.exists():
        try:
            with open(target_pref_read, "r", encoding="utf-8") as f:
                curr_pref = json.load(f)
        except Exception:
            pass

    default_roles = curr_pref.get("target_roles", [
        "Strategy & Operations", "Chief of Staff", "Business Operations", 
        "Program Manager", "Revenue Operations", "Founder's Office"
    ])
    target_roles = prompt_list("Target Job Titles (comma-separated)", default_roles)

    default_locs = curr_pref.get("target_locations", [
        "Remote", "Global Remote", "Bengaluru", "Hyderabad", "Gurugram", "San Francisco", "New York"
    ])
    target_locations = prompt_list("Target Locations (comma-separated)", default_locs)

    salary_floor_lpa = prompt_user("Minimum Salary Floor (INR LPA) - Skip roles below this", str(curr_pref.get("min_salary_floor_lpa", 30.0)))
    salary_floor_usd = prompt_user("Minimum Salary Floor (USD Annual) - Skip roles below this", str(curr_pref.get("min_salary_floor_usd", 60000.0)))
    try:
        salary_floor_lpa_val = float(salary_floor_lpa)
        salary_floor_usd_val = float(salary_floor_usd)
    except ValueError:
        salary_floor_lpa_val = 30.0
        salary_floor_usd_val = 60000.0

    min_score = prompt_user("Minimum Resume Fit Score Threshold (0-100%)", str(curr_pref.get("minimum_match_score", 70)))
    try:
        min_score_val = int(min_score)
    except ValueError:
        min_score_val = 70

    default_excluded = curr_pref.get("excluded_keywords", [
        "Software Engineer", "DevOps", "QA Tester", "Intern", "Account Executive", "SDR", "Recruiter"
    ])
    excluded_keywords = prompt_list("Excluded Negative Keywords (comma-separated)", default_excluded)

    # ----------------------------------------------------
    # STEP 4: TARGET COMPANIES & ATS BOARDS
    # ----------------------------------------------------
    print("\n[Step 4/5] Target ATS Companies")
    print("-" * 50)
    
    comp_list_path = CONTEXT_DIR / "company_list.txt"
    comp_ex_path = CONTEXT_DIR / "company_list.example.txt"
    target_comp_read = comp_list_path if comp_list_path.exists() else comp_ex_path
    existing_companies = []
    if target_comp_read.exists():
        for line in target_comp_read.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                existing_companies.append(s)

    default_comp_str = ", ".join(existing_companies[:10]) if existing_companies else "gitlab, stripe, ramp, databricks, replit, perplexity"
    comp_input = prompt_user("Target ATS Company Slugs (comma-separated)", default_comp_str)
    target_companies = [c.strip() for c in comp_input.split(",") if c.strip()]

    # ----------------------------------------------------
    # STEP 5: AI & INTEGRATION CONFIGURATION
    # ----------------------------------------------------
    print("\n[Step 5/5] Automation & API Credentials (.env)")
    print("-" * 50)
    
    gemini_key = prompt_user("Google Gemini API Key (Optional, for smart screening question answering)", os.getenv("GEMINI_API_KEY", ""))
    gmail_user = prompt_user("Gmail Address for Automated OTP Resolution (Optional)", os.getenv("GMAIL_USER", ""))
    gmail_pwd = prompt_user("Gmail App Password (Optional, 16-character token)", os.getenv("GMAIL_APP_PASSWORD", ""))
    headless_mode = prompt_user("Run Browser in Headless Mode? (true = background, false = visible browser)", "false")

    # ----------------------------------------------------
    # WRITE CONFIGURATIONS
    # ----------------------------------------------------
    print("\n" + "=" * 50)
    print("Saving candidate profile & configurations...")
    print("=" * 50)

    # 1. screening_qa.json
    final_qa = {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "location": location,
        "willing_to_relocate": willing_relocate,
        "work_authorization": work_auth,
        "requires_sponsorship": requires_sponsorship,
        "current_notice_period": notice_period,
        "linkedin_url": linkedin_url,
        "github_portfolio_url": github_url,
        "screening_answers": {
            "notice_period": notice_period,
            "work_authorization": work_auth,
            "relocation": willing_relocate,
            "current_company": current_company,
            "current_title": current_title,
            "total_years_experience": years_exp_num,
            "current_ctc": current_ctc,
            "expected_ctc": expected_ctc,
            "compensation": compensation_note,
            "summary": summary
        }
    }
    with open(CONTEXT_DIR / "screening_qa.json", "w", encoding="utf-8") as f:
        json.dump(final_qa, f, indent=2)
    print("✓ context/screening_qa.json created")

    # 2. preferences.json
    final_pref = {
        "target_roles": target_roles,
        "target_locations": target_locations,
        "experience_years_min": max(1, years_exp_num - 3),
        "experience_years_max": years_exp_num + 4,
        "minimum_match_score": min_score_val,
        "min_salary_floor_lpa": salary_floor_lpa_val,
        "min_salary_floor_usd": salary_floor_usd_val,
        "excluded_keywords": excluded_keywords
    }
    with open(CONTEXT_DIR / "preferences.json", "w", encoding="utf-8") as f:
        json.dump(final_pref, f, indent=2)
    print("✓ context/preferences.json created")

    # 3. profile_notes.md
    profile_notes_content = f"""# Candidate Profile Notes: {full_name}

## Contact & Core Information
- **Full Name**: {full_name}
- **Email**: {email} | **Phone**: {phone}
- **LinkedIn**: [{linkedin_url}]({linkedin_url})
- **GitHub / Portfolio**: [{github_url}]({github_url})
- **Location**: {location}

---

## Executive Summary
{summary}

---

## Background & Achievements
- **Current Charter**: {current_title} at {current_company} with {years_exp_num}+ years of professional experience.
- **Compensation Expectations**: {compensation_note}
- **Work Authorization**: {work_auth} (Sponsorship required: {requires_sponsorship})
- **Availability**: Notice period of {notice_period}.
"""
    with open(CONTEXT_DIR / "profile_notes.md", "w", encoding="utf-8") as f:
        f.write(profile_notes_content.strip() + "\n")
    print("✓ context/profile_notes.md created")

    # 4. company_list.txt
    with open(CONTEXT_DIR / "company_list.txt", "w", encoding="utf-8") as f:
        f.write("# Target ATS Companies\n" + "\n".join(target_companies) + "\n")
    print("✓ context/company_list.txt created")

    # 5. .env
    env_content = f"""# Automation Configuration & API Keys
MIN_FIT_SCORE={min_score_val}
HEADLESS={headless_mode.lower()}

# AI Screening Question Answering
GEMINI_API_KEY={gemini_key}

# Compensation Floor
MIN_SALARY_FLOOR_LPA={salary_floor_lpa_val}
MIN_SALARY_FLOOR_USD={salary_floor_usd_val}

# Automated OTP Resolution via Gmail IMAP (Optional)
GMAIL_USER={gmail_user}
GMAIL_APP_PASSWORD={gmail_pwd}

# Application Persistence
GOOGLE_APPLICATION_CREDENTIALS=credentials.json
GOOGLE_SHEET_NAME=Job Application Tracker
"""
    with open(BASE_DIR / ".env", "w", encoding="utf-8") as f:
        f.write(env_content.strip() + "\n")
    print("✓ .env configuration created")

    print("\n" + "=" * 72)
    print("🎉 ONBOARDING COMPLETE! Your Job Hunter is configured and ready.")
    print("=" * 72)
    print("\nNext simple steps to run:")
    print("  1. Ingest matching jobs from ATS boards:")
    print("     python run.py --scrape")
    print("  2. Match and rank jobs against your resume:")
    print("     python run.py --match")
    print("  3. Run end-to-end automated job search & applications:")
    print("     python run.py --all")
    print("  4. Or launch the Web Dashboard interface:")
    print("     python run.py --ui\n")


if __name__ == "__main__":
    main()
