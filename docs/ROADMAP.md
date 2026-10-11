# Roadmap to a dependable Job Hunter

The goal is a plug-and-play job application assistant. A new user supplies accurate personal and career details, approved resumes, and job preferences; the system discovers suitable openings and handles supported applications with verifiable results. The current repository is a prototype. The checks below define what must work before it can be described as hands-off.

## 1. Make setup reliable

- Require an explicit, validated user profile. Remove silent fallback to fictional sample people from live flows.
- Collect structured facts: total and role-specific experience, compensation currency and period, education, contact details, location, work authorization, and user-defined exclusions.
- Ingest approved resume variants and record which roles each may support. Show the chosen file before any application.
- Make setup output compatible with the discovery input format. Run a fresh-install test with only documented commands.
- Keep secrets and personal artifacts out of the repository; provide a safe example profile with invented data.

**Release check:** A fresh user can enter data once, add multiple resumes, choose preferences, restart the app, and get the same validated profile and resume inventory back. Incomplete required facts cause a visible stop.

## 2. Discover and qualify jobs

- Maintain source adapters for direct ATS boards, company career pages, and selected portals. Report which sources ran, failed, or were unsupported.
- Read the full job description and preserve its URL, posting time when available, location, compensation, and mandatory requirements.
- Match roles against preferences and distinguish supported facts from inferred fit. Reject clear conflicts such as a US-only role for an India-only candidate.
- Deduplicate by canonical job and company identity. Persist applications across runs and enforce configurable company limits atomically, including when two workers run together.
- Keep a coverage report instead of claiming that every job platform or employer was checked.

**Release check:** If a company allows two applications, two confirmed submissions use the quota and a third is blocked before form submission. A failed attempt does not consume a confirmed-submission slot unless the portal says it does.

## 3. Answer forms according to their meaning

- Build a shared form-field resolver that reads label, help text, input type, allowed options, validation constraints, and relevant job context.
- Store numbers with units. For example, 55 lakh per year can be `55` in a “salary in lakhs” field and `5500000` in an “annual INR” field.
- Distinguish total experience from specialist experience. Never turn nine total years into nine years in an unsupported specialty.
- Return typed answers for dates, select boxes, yes/no questions, numeric years, and free text. Check the entered value after the page accepts it.
- Surface unknown or conflicting facts for review. Do not manufacture a plausible answer to bypass a required field.
- Test each adapter with realistic form fixtures and a live review flow when the site changes.

**Release check:** A numeric “total years of experience” field receives `9`, a dropdown receives one of its allowed values, and a field asking for specialist tenure stops if the profile has no verified answer.

## 4. Connect portals, email, and tracking

- Define a supported-site matrix for LinkedIn, IIMJobs, Naukri, Greenhouse, Lever, Ashby, and other sources as added. Document each source's search, login, form, account creation, verification, and proof capabilities separately.
- Handle account creation and Gmail verification only through a user-authorized connection, with explicit exception handling for CAPTCHA, 2FA, rate limits, and changed site flows.
- Make submission idempotent. Before retrying after a timeout, check whether the portal already accepted the application.
- Keep distinct states: discovered, eligible, draft, awaiting review, submitting, confirmed, rejected, and outcome unknown.
- Mark “confirmed” only when supported by an authoritative portal state, application ID, or confirmation message. Store a minimal, private evidence reference.

**Release check:** A thank-you screen with no application proof remains “outcome unknown.” A portal's applied page or application ID moves the record to “confirmed.” A retry never creates a second application.

## 5. Prove the end-to-end experience

- Test onboarding, discovery, routing, form entry, verification, and tracking as one workflow with invented applicant data.
- Measure precision of job qualification, correctness of field answers, duplicate avoidance, and confirmed-submission accuracy on an agreed test set.
- Run a small, supervised pilot on each supported portal, then document the observed success and failure rates.
- Define which actions can run automatically and when the user must review or approve. Make the default behavior clear in the UI.
- Publish a maintained compatibility matrix and known limitations before calling the product plug-and-play.

**Release check:** A fresh user can follow one documented setup path, see eligible jobs and the selected resume, complete supported applications, and audit each final status. Unsupported sites and ambiguous outcomes stay visible.

## Good first contributions

- Reproduce a broken setup or CLI path with invented data.
- Add a form fixture that demonstrates a unit, date, dropdown, or validation edge case.
- Add a source adapter with full-description extraction and clear failure reporting.
- Improve proof-backed application states and duplicate checks.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for local development steps.
