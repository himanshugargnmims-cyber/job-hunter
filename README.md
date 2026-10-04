# 🎯 Job Hunter — Automated ATS Job Search & Application Engine

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Playwright Automation](https://img.shields.io/badge/playwright-tested-green.svg)](https://playwright.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An end-to-end, privacy-first automated job discovery, resume matching, and ATS application engine. It discovers live postings across **Greenhouse**, **Lever**, and **Ashby**, evaluates job descriptions against your resume variants, verifies salary floors, auto-fills application forms with **Playwright**, and logs every step across local **SQLite**, **CSV**, and **Excel** trackers.

---

## ⚡ Key Capabilities

- **Multi-ATS Live Scraping**: Ingests live job listings and rich markdown descriptions from Greenhouse (`boards.greenhouse.io`), Lever (`jobs.lever.co`), and Ashby (`jobs.ashbyhq.com`).
- **Multi-Resume Routing & Scoring**: Parses your resume (PDF/TXT), evaluates alignment against job requirements, and computes an objective 0–100% fit score with decision rationale without hallucinating text.
- **Automated Form Pre-filling & Submissions**: Playwright-driven browser automation that uploads resumes, handles text inputs, radio buttons, dropdowns, and dynamically rendered EEO/diversity questions.
- **AI-Powered Screening Answering**: Uses **Google Gemini** grounded in your personal profile notes to answer open-ended screening questions, with robust offline heuristics fallback.
- **Strict Salary Floor Filter**: Automatically filters out roles paying below your compensation threshold (INR LPA, USD, EUR).
- **Automated Security Code / OTP Solver**: Optional Gmail IMAP integration that automatically fetches email verification codes for ATS portals.
- **Two User Interfaces**:
  - **🖥️ Web UI Dashboard**: Drag-and-drop your resume in your browser, tweak all variables on an interactive form, and launch with one click.
  - **⌨️ Interactive CLI Wizard**: Step-by-step terminal onboarding prompts.
- **Zero Privacy Leaks**: Clean template architecture with strict `.gitignore` ensuring your personal resumes, contact details, logs, and passwords never touch Git.

---

## 📁 Repository Directory Structure

```text
job-hunter/
├── context/
│   ├── preferences.example.json   # Template: target titles, locations, salary floors
│   ├── screening_qa.example.json  # Template: candidate contact, notice period, work auth
│   ├── profile_notes.example.md   # Template: candidate achievements & executive summary
│   └── company_list.example.txt   # Template: target company ATS slugs
├── data/                          # Application database (jobs.db), CSV, Excel (gitignored)
├── logs/                          # Verification screenshots & execution logs (gitignored)
├── resumes/                       # Pre-made resume variants / PDFs (gitignored)
│   └── sample_resume.txt          # Sample resume template for onboarding
├── scripts/
│   ├── applier.py                 # Core Playwright ATS application automation
│   ├── hard_check_applier.py      # Hard-check verified ATS submitter with OTP solver
│   ├── scraper.py                 # Multi-ATS scraper (Greenhouse, Lever, Ashby)
│   ├── resume_selector.py         # JD parsing and resume fit scoring engine (0-100%)
│   ├── salary_filter.py           # Compensation floor enforcement filter
│   ├── question_answerer.py       # Gemini AI screening question answering module
│   ├── sheet_updater.py           # SQLite, CSV & Google Sheets dual-tier tracker
│   ├── export_excel.py            # Formatted multi-tab Excel dashboard generator
│   ├── setup_profile.py           # Interactive CLI onboarding wizard
│   └── web_ui.py                  # Local Web UI server (zero external dependencies)
├── .env.example                   # Environment configuration template
├── .gitignore                     # Comprehensive privacy & runtime file ignore rules
├── requirements.txt               # Python package dependencies
└── run.py                         # Master CLI orchestrator entrypoint
```

---

## 🚀 Quick Start (In 3 Simple Steps)

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/<your-username>/job-hunter.git
cd job-hunter

python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

---

### 2. Configure Your Profile & Resume

You can set up your profile using either the **Web Interface** or the **Terminal Wizard**:

#### Option A: Web UI Dashboard (Recommended)
```bash
python run.py --ui
```
Open **`http://localhost:8080`** in your browser. Drag and drop your resume (PDF or TXT). The system extracts your contact details, skills, and links automatically. Review the form, adjust any variables, and click **Save Profile & Preferences**.

#### Option B: Terminal Setup Wizard
```bash
python run.py --setup
```
An interactive step-by-step CLI that prompts for your resume path, personal details, salary floor, target job titles, locations, and companies.

---

### 3. Run the Job Hunter

```bash
# Ingest live postings matching your titles and locations
python run.py --scrape

# Evaluate and score your resume against all discovered jobs
python run.py --match

# Auto-apply to matched jobs (simulates in review mode)
python run.py --apply --dry-run

# Run the complete end-to-end pipeline (Scrape -> Match -> Apply)
python run.py --all

# View live application pipeline statistics
python run.py --stats

# Export tracker to formatted Excel workbook
python run.py --export
```

---

## ⚙️ Configurable Variables Reference

All variables can be configured via `run.py --setup`, the Web UI, or directly in `context/`:

| Variable Category | Config Keys | Description |
| :--- | :--- | :--- |
| **Personal Identity** | `full_name`, `email`, `phone`, `location` | Candidate name, contact info, and current city/country. |
| **Work Authorization** | `work_authorization`, `requires_sponsorship` | Citizenship status and whether visa sponsorship is required. |
| **Availability** | `current_notice_period`, `earliest_start_date` | Notice period (e.g. `Immediate`, `30 Days`, `60 Days`). |
| **Compensation** | `current_ctc`, `expected_ctc`, `min_salary_floor_lpa`, `min_salary_floor_usd` | Explicit compensation expectations and minimum salary threshold. Roles below this floor are automatically skipped. |
| **Current Role** | `current_company`, `current_title`, `total_years_experience` | Present employer, title, and years of experience. |
| **Target Roles** | `target_roles` | Comma-separated job titles (e.g., `Strategy & Operations`, `Chief of Staff`, `Program Manager`). |
| **Target Locations** | `target_locations` | Geographical filters (e.g., `Remote`, `San Francisco`, `Bengaluru`, `London`). |
| **Exclusions** | `excluded_keywords` | Negative keywords to auto-reject (e.g., `Intern`, `Software Engineer`, `QA`). |
| **Match Threshold** | `minimum_match_score` | Minimum percentage fit score (e.g. `70`) required to trigger application. |
| **Target ATS Slugs** | `target_companies` | Company board slugs for Greenhouse, Lever, and Ashby (e.g., `gitlab`, `stripe`, `ramp`). |
| **AI Question Answering** | `GEMINI_API_KEY` | Optional Google Gemini key to generate 2-3 sentence answers to screening questions. |
| **Browser Visibility** | `HEADLESS` | Set `false` to watch browser submissions live, or `true` for headless background execution. |

---

## 🔒 Security & Privacy

This repository is designed from the ground up for open sharing:
- All real resumes (`resumes/*.pdf`, `resumes/*.docx`) are **strictly gitignored**.
- All personal credentials (`.env`, `credentials.json`) are **strictly gitignored**.
- All local application trackers (`data/*.db`, `data/*.csv`, `data/*.xlsx`) and screenshots (`logs/*`) are **strictly gitignored**.
- Fresh clones start with clean `.example` templates ready to be populated by the setup wizard.

---

## 📤 How to Publish to Your GitHub

Follow these steps to push this project to your own GitHub account:

### Method 1: Using GitHub CLI (`gh`)
```bash
# Authenticate GitHub CLI
gh auth login

# Create a new repository and push
gh repo create job-hunter --public --source=. --remote=origin --push
```

### Method 2: Using the GitHub Web Interface
1. Go to [github.com/new](https://github.com/new) and create a repository named **`job-hunter`**.
2. Connect and push your local commits:
   ```bash
   git remote add origin https://github.com/<your-username>/job-hunter.git
   git branch -M main
   git push -u origin main
   ```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
