# Sharing Job Hunter

Job Hunter is an open-source prototype. Promotion should invite feedback on a concrete problem and a reproducible demo. It should not promise unattended, accurate applications across every site until the [release checks](ROADMAP.md) have passed.

## Positioning

**One-line description:** An open-source job search prototype exploring verified profiles, resume routing, exact form answers, and proof-backed application tracking.

**Who it is for:** Job seekers who repeatedly enter the same information, and developers interested in reliable browser automation for job applications.

**What to show:** A short recording using invented applicant data: preferences, one job description, chosen resume, a typed form answer, and a final confirmed-or-unknown tracker state. Label any simulated or incomplete step.

## Where to share

| Stage | Channel | Approach |
| --- | --- | --- |
| Now | [GitHub repository](https://github.com/himanshugargnmims-cyber/job-hunter) | Keep the About description, topics, README, issues, and roadmap accurate. Link to one reproducible demo as soon as it exists. |
| Now, for feedback | Personal LinkedIn | Share the problem, the prototype's current scope, and a specific request for feedback from job seekers and builders. Use one personal post rather than automated outreach. |
| After a reproducible technical demo | [DEV Community](https://dev.to/) | Write a useful engineering article about form units, duplicate limits, and proof of submission. Include the repo as a reference, not the whole purpose of the article. |
| Only when a community permits it | Relevant Reddit communities | Read the rules, contribute a tailored technical or job-seeker discussion, and disclose that this is your project. Do not mass-post the same promotion. |
| When a stranger can try the core flow | [Show HN](https://news.ycombinator.com/showhn.html) | Offer a working, accessible demo and stay available to answer technical questions. |
| When onboarding and core flow work end to end | [Product Hunt](https://www.producthunt.com/) | Prepare a usable product page, demo, screenshots, and clear support expectations. |

## Suggested first LinkedIn post

> I am building Job Hunter, an open-source prototype for the repetitive parts of job applications. The goal is simple: enter a verified profile, resumes, and role preferences once; then find relevant jobs, choose the right resume, answer each field in the format it asks for, and keep proof of what was submitted.
>
> The hard parts are where automation usually fails: a salary field may ask for lakhs instead of rupees, a company may limit applications, and a page may appear complete without actually accepting the application. I am designing around those cases.
>
> The repository is public, but the application workflow is still a prototype. I would value feedback on the most painful application forms and on what evidence you would need before trusting an “applied” status.
>
> https://github.com/himanshugargnmims-cyber/job-hunter

## Suggested technical article

**Title:** Why job application automation needs typed answers and proof of submission

1. Show a field asking for annual salary in lakhs versus annual INR.
2. Show total years of experience versus years in a specific specialty.
3. Explain the company-level two-application limit and concurrent retries.
4. Show how a portal confirmation differs from a clicked Submit button.
5. End with a fake-data demo, known limitations, and the roadmap.

## Launch readiness

Before a broad launch, use a fresh account and invented applicant profile to reproduce setup, discovery, resume selection, form entry, and outcome tracking. Publish what passed, what failed, and which portals are supported. Keep screenshots and videos free of real resumes, credentials, and email messages.
