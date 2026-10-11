# Contributing to Job Hunter

Job Hunter is a prototype aiming for accurate, verifiable job applications. Contributions are welcome, especially fixes that make setup, field answers, source coverage, and application outcomes easier to trust.

Use invented applicant data in tests, issues, screenshots, and pull requests. Never include a real resume, email, phone number, session, API key, or employer account credential.

---

## Code of conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone. Please be respectful and constructive in all issues and pull requests.

---

## Local development

### 1. Clone and set up a virtual environment

```bash
git clone https://github.com/himanshugargnmims-cyber/job-hunter.git
cd job-hunter

python3.10 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install pytest flake8

# Only if working on browser automation
playwright install chromium
```

### 2. Check your change

Run the checks relevant to your change and include the results in your pull request:

```bash
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

pytest -v
```

---

## What to contribute

### Source adapters

For a new source, capture the full job description, title, company, location, canonical URL, and any explicit eligibility limits. Show failures and unsupported flows instead of silently skipping them. Use invented data in fixtures. See the [roadmap](docs/ROADMAP.md) for acceptance checks.

### Form answers and application tracking

Provide a fixture for the exact field or portal state you are fixing. Include units and allowed values for salary, years of experience, dates, and select controls. Keep “confirmed submission” separate from drafts and uncertain outcomes. An application status must be backed by portal evidence.

### RevOps examples

The separate `revops_kit/` examples remain open to improvements. Add tests for changed calculations and keep sample data clearly fictional.

### Pull requests

Describe the behavior before and after your change, the source or form fixture used, and the checks you ran. For live-portal changes, state what you could verify and what remains untested.

---

If you change setup, commands, or supported-site behavior, update the README and roadmap at the same time.
