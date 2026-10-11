#!/usr/bin/env python3
"""
form_understanding.py - Universal Form Field Understanding & Resolution Engine

Transforms raw DOM input fields into strongly-typed FormField contracts, maps them
against verified CandidateProfile facts, and resolves the exact string or choice required.

Invariants Enforced:
1. Pure integer/digit compensation (55 or 5500000), never strings with commas or currency signs.
2. Notice period strictly 30 (or 1 month).
3. Total experience strictly 9 (or 108 months).
4. No LinkedIn URL stuffing into optional GitHub fields.
5. Multi-select checkboxes check only legal consent and candidate's demographics (Asian), never all.
6. Radio / dropdown options strictly match candidate answers, never blind index 0.
"""

import sys
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from playwright.sync_api import Locator, Page, Frame

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.application_models import (
    CandidateProfile,
    FormField,
    ResolvedAnswer
)
from scripts.field_resolver import (
    resolve_salary,
    resolve_notice_period,
    resolve_date,
    resolve_experience,
    resolve_text_input,
    resolve_radio_or_dropdown
)

PROFILE_PATH = BASE_DIR / "context" / "profile.json"
CANDIDATE = CandidateProfile.load_from_json(PROFILE_PATH)


class FormFieldInterpreter:
    def __init__(self, profile: CandidateProfile = CANDIDATE):
        self.profile = profile

    def extract_field_metadata(self, locator: Locator) -> FormField:
        """
        Extracts comprehensive metadata from a Playwright input/select/textarea locator.
        """
        try:
            tag_name = locator.evaluate("el => el.tagName.toLowerCase()")
        except Exception:
            tag_name = "input"

        input_type = "text"
        if tag_name == "input":
            try:
                input_type = locator.get_attribute("type") or "text"
            except Exception:
                input_type = "text"
        elif tag_name in ["select", "textarea"]:
            input_type = tag_name

        # Extract name, id, placeholder
        name = locator.get_attribute("name") or ""
        elem_id = locator.get_attribute("id") or ""
        placeholder = locator.get_attribute("placeholder") or ""
        aria_label = locator.get_attribute("aria-label") or ""
        max_length_str = locator.get_attribute("maxlength") or ""
        max_length = int(max_length_str) if max_length_str.isdigit() else None
        required = bool(locator.get_attribute("required") or locator.get_attribute("aria-required") == "true")

        # Discover associated label text
        label_text = ""
        try:
            # 1. Check aria-label
            if aria_label:
                label_text = aria_label
            # 2. Check label[for="elem_id"]
            elif elem_id:
                for_label = locator.page.locator(f"label[for='{elem_id}']")
                if for_label.count() > 0:
                    label_text = for_label.first.inner_text().strip()
            # 3. Check enclosing label or preceding sibling/parent
            if not label_text:
                label_text = locator.evaluate("""el => {
                    let p = el.closest('label');
                    if (p) return p.innerText;
                    let parent = el.closest('.field, .form-group, [class*="field"], [class*="question"]');
                    if (parent) {
                        let lbl = parent.querySelector('label, [class*="label"], [class*="title"]');
                        if (lbl) return lbl.innerText;
                    }
                    return '';
                }""")
        except Exception:
            pass

        if not label_text and placeholder:
            label_text = placeholder

        # Extract options if select element
        options = []
        if tag_name == "select":
            try:
                options = locator.locator("option").all_inner_texts()
                options = [o.strip() for o in options if o.strip()]
            except Exception:
                pass

        return FormField(
            name=name or elem_id,
            label=label_text.strip(),
            field_type=input_type,
            required=required,
            help_text="",
            options=options,
            max_length=max_length
        )

    def resolve_answer_for_field(self, field: FormField, context_notes: str = "") -> ResolvedAnswer:
        """
        Determines the precise value and format for any form field using verified profile facts.
        """
        label_norm = field.label.lower()
        name_norm = field.name.lower()
        combined = f"{label_norm} {name_norm}"

        # 1. SALARY / COMPENSATION
        if any(k in combined for k in ["ctc", "salary", "compensation", "remuneration", "earning", "pay"]):
            is_numeric = field.field_type in ["number", "tel"]
            val = resolve_salary(
                context_text=combined,
                max_length=field.max_length,
                is_numeric_input=is_numeric
            )
            unit = "lakhs" if val in ["55", "40"] else "full_digits"
            return ResolvedAnswer(
                field_name=field.name,
                value=val,
                unit_applied=unit,
                rationale=f"Resolved salary based on field context '{field.label}' (max_length={field.max_length})"
            )

        # 2. NOTICE PERIOD & START DATE
        if any(k in combined for k in ["notice", "availability", "start date", "how soon", "joining date"]):
            if "date" in combined or field.field_type == "date":
                val = resolve_date(combined)
                unit = "date"
            else:
                is_numeric = field.field_type in ["number", "tel"]
                val = resolve_notice_period(combined, is_numeric_input=is_numeric)
                unit = "integer_duration"
            return ResolvedAnswer(
                field_name=field.name,
                value=val,
                unit_applied=unit,
                rationale=f"Resolved notice period based on context '{field.label}'"
            )

        # 3. EXPERIENCE / TENURE
        if any(k in combined for k in ["experience", "tenure", "years in", "relevant experience"]):
            val = resolve_experience(combined)
            return ResolvedAnswer(
                field_name=field.name,
                value=val,
                unit_applied="integer_years",
                rationale=f"Resolved experience years based on context '{field.label}'"
            )

        # 4. CONTACT / IDENTITY
        if "first name" in combined or "given name" in combined:
            return ResolvedAnswer(field.name, self.profile.identity.first_name, "text", "Profile First Name")
        if "last name" in combined or "family name" in combined or "surname" in combined:
            return ResolvedAnswer(field.name, self.profile.identity.last_name, "text", "Profile Last Name")
        if any(k in combined for k in ["full name", "your name", "candidate name"]):
            return ResolvedAnswer(field.name, self.profile.identity.full_name, "text", "Profile Full Name")
        if "email" in combined:
            return ResolvedAnswer(field.name, self.profile.identity.email, "email", "Profile Email")
        if any(k in combined for k in ["phone", "mobile", "contact number"]):
            if "code" in combined or "country code" in combined:
                return ResolvedAnswer(field.name, self.profile.identity.country_code, "text", "Country code +91")
            return ResolvedAnswer(field.name, self.profile.identity.phone_digits, "digits", "Profile 10-digit Phone")

        # 5. LINKS / PORTFOLIO
        if "linkedin" in combined:
            return ResolvedAnswer(field.name, self.profile.identity.linkedin_url, "url", "LinkedIn profile URL")
        if "github" in combined:
            # Strictly NEVER put LinkedIn into GitHub
            return ResolvedAnswer(field.name, self.profile.identity.github_url, "url", "GitHub URL (Empty if not set)")
        if any(k in combined for k in ["website", "portfolio"]):
            return ResolvedAnswer(field.name, self.profile.identity.website_url, "url", "Profile Website / LinkedIn URL")

        # 6. LOCATION / ADDRESS
        if any(k in combined for k in ["city", "current location", "location"]):
            return ResolvedAnswer(field.name, self.profile.location.city, "text", "City Bengaluru")
        if "postal" in combined or "pincode" in combined or "zip" in combined:
            return ResolvedAnswer(field.name, self.profile.location.postal_code, "text", "Pincode 560102")
        if "address" in combined:
            return ResolvedAnswer(field.name, self.profile.location.full_address, "text", "Full Address")

        # 7. WORK AUTHORIZATION & CITIZENSHIP
        if any(k in combined for k in ["authorized to work in india", "legally authorized to work in india", "work permit in india"]):
            return ResolvedAnswer(field.name, "Yes", "boolean", "Indian Citizen with full right to work")
        if any(k in combined for k in ["sponsorship", "require visa", "require sponsorship"]):
            if "us" in combined or "united states" in combined:
                return ResolvedAnswer(field.name, "Yes", "boolean", "Requires US sponsorship")
            return ResolvedAnswer(field.name, "No", "boolean", "Does not require India sponsorship")
        if any(k in combined for k in ["authorized to work in the us", "us work authorization"]):
            return ResolvedAnswer(field.name, "No", "boolean", "Does not hold US work authorization")

        # 8. CURRENT EMPLOYMENT
        if any(k in combined for k in ["current company", "current employer", "present employer", "recent company"]):
            org = getattr(self.profile, "current_company", None) or "Technology Solutions"
            return ResolvedAnswer(field.name, org, "text", "Current Employer")
        if any(k in combined for k in ["current title", "current designation", "job title"]):
            tit = getattr(self.profile, "current_title", None) or "Lead - Strategy & Operations"
            return ResolvedAnswer(field.name, tit, "text", "Current Title")

        # 9. EDUCATION
        highest_edu = self.profile.education[0] if self.profile.education else None
        if any(k in combined for k in ["highest degree", "degree level", "education"]):
            deg = highest_edu.degree_level if highest_edu else "Master's Degree"
            return ResolvedAnswer(field.name, deg, "text", "Highest Degree")
        if "institution" in combined or "university" in combined or "college" in combined or "school" in combined:
            inst = highest_edu.institution if highest_edu else "University"
            return ResolvedAnswer(field.name, inst, "text", "Education Institution")
        if "major" in combined or "discipline" in combined or "specialization" in combined:
            maj = highest_edu.specialization if highest_edu else "Business Administration"
            return ResolvedAnswer(field.name, maj, "text", "Specialization")

        # 10. RELOCATION & COMMUTE
        if any(k in combined for k in ["relocate", "relocation"]):
            return ResolvedAnswer(field.name, "Yes", "boolean", "Willing to relocate")
        if any(k in combined for k in ["commute", "on-site", "hybrid"]):
            return ResolvedAnswer(field.name, "Yes", "boolean", "Willing to work on-site/hybrid")

        # 11. DROPDOWN / SELECT RESOLUTION
        if field.field_type == "select" and field.options:
            resolved_opt = resolve_radio_or_dropdown(combined, field.options)
            return ResolvedAnswer(field.name, resolved_opt, "select_option", f"Matched dropdown option '{resolved_opt}'")

        # 12. TEXT INPUT / GENERAL
        resolved_gen = resolve_text_input(combined, max_length=field.max_length)
        return ResolvedAnswer(field.name, resolved_gen, "text", "Resolved general text")


if __name__ == "__main__":
    interpreter = FormFieldInterpreter()
    print("=== Testing Form Field Understanding & Resolution ===")

    test_fields = [
        FormField(name="expected_ctc_lakhs", label="Expected Annual CTC (in Lakhs INR)", field_type="text", max_length=5),
        FormField(name="expected_salary_digits", label="Expected CTC (INR, digits only, no commas)", field_type="number"),
        FormField(name="current_ctc_full", label="Current Compensation (Annual)", field_type="text"),
        FormField(name="notice_days", label="Notice Period (in Days)", field_type="number"),
        FormField(name="github_url", label="GitHub Profile URL (Optional)", field_type="text"),
        FormField(name="linkedin_url", label="LinkedIn Profile", field_type="text"),
        FormField(name="work_auth_in", label="Are you legally authorized to work in India?", field_type="select", options=["Select an option", "Yes", "No"]),
        FormField(name="sponsorship_in", label="Will you now or in the future require visa sponsorship for employment in India?", field_type="select", options=["Select an option", "Yes", "No"]),
        FormField(name="total_exp", label="Total Years of Professional Experience", field_type="number")
    ]

    for tf in test_fields:
        ans = interpreter.resolve_answer_for_field(tf)
        print(f"Field: '{tf.label}' [{tf.field_type}]")
        print(f" -> Value: '{ans.value}' | Unit: {ans.unit_applied} | Rationale: {ans.rationale}\n")
