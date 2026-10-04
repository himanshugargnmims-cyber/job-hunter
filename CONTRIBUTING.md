# Contributing to Job Hunter & Nexus RevOps

First off, thank you for considering contributing! Projects like this thrive because of open-source contributors like you.

Whether you are fixing a bug, adding an ATS scraper adapter, improving the RevOps forecasting model, or expanding the documentation, your help is welcome.

---

## 🧭 Code of Conduct

We are committed to providing a welcoming, inclusive, and harassment-free experience for everyone. Please be respectful and constructive in all issues and pull requests.

---

## 🛠 Local Development Setup

### 1. Clone & Set Up Virtual Environment

```bash
# Clone the repository
git clone https://github.com/himanshugargnmims-cyber/job-hunter.git
cd job-hunter

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install pytest flake8

# Install Playwright browser drivers (if running browser automation)
playwright install chromium
```

### 2. Verify Tests & Code Style

Before submitting a pull request, verify that all unit tests pass and that there are no syntax/lint errors:

```bash
# Run flake8 linter
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics

# Run unit tests
pytest -v
```

---

## 🚀 How to Contribute

### 1. Adding a New ATS Scraper Adapter
To support a new ATS platform (e.g. Workday, SmartRecruiters, Jobvite):
1. Create a script in `scripts/` following the existing patterns in `sweep_direct_ats.py`.
2. Ensure it extracts: Job Title, Company, Location, Job URL, and Raw Description.
3. Save structured jobs into `data/jobs.db` via standard SQLite queries.

### 2. Expanding the RevOps Toolkit (`revops_kit/`)
To add a new revenue metric or commercial model:
1. Implement your model in `revops_kit/<your_module>.py`.
2. Add comprehensive docstrings and typed inputs.
3. Export the class in `revops_kit/__init__.py`.
4. Add corresponding test cases in `tests/test_revops.py`.

### 3. Submitting a Pull Request
1. Fork the repo and create a new feature branch (`git checkout -b feature/amazing-feature`).
2. Commit your changes with clear messages (`git commit -m 'feat: Add Ashby ATS scraper adapter'`).
3. Ensure all tests pass (`pytest -v`).
4. Push to your branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request on GitHub describing your changes and testing steps.

---

## 📜 Pull Request Guidelines

- **No Personal Data**: Never commit personal resumes, private API keys, emails, or phone numbers. Always use generic placeholders or templates.
- **Maintain Test Coverage**: Ensure newly added logic is tested with unit tests.
- **Documentation**: If you add new CLI arguments or environment variables, update `README.md` and `run.py`.

Thank you for building the future of autonomous job hunting and revenue operations!
