#!/usr/bin/env python3
"""
application_models.py - Unified Data Models & Contracts for Job Hunter

Provides strongly-typed, immutable dataclasses for:
1. CandidateProfile: Identity, tenure, compensation policies, education, demographics.
2. JobPosting: Title, company, ATS type, URL, description, requirements.
3. EligibilityDecision: Seniority gate, pillar classification, geo-validation, target resume.
4. FormField & ResolvedAnswer: Field representation, constraint boundaries, format resolution.
5. ApplicationResult: Submission state, proof evidence, error tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import json


class ATSPlatform(str, Enum):
    LINKEDIN_EASY = "linkedin_easy"
    LINKEDIN_EXTERNAL = "linkedin_external"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    WORKDAY = "workday"
    SMARTRECRUITERS = "smartrecruiters"
    KULA = "kula"
    GENERIC = "generic"


class Pillar(str, Enum):
    PILLAR_1_REVOPS = "Pillar 1: Revenue Operations & Commercial Operations"
    PILLAR_2_CUSTOMER_SUCCESS = "Pillar 2: Customer Success & Post-Sales Strategy"
    PILLAR_3_STRATEGY_OPS = "Pillar 3: Strategy & Operations / Chief of Staff / Business Programs"
    DISQUALIFIED = "Disqualified"


class SeniorityLevel(str, Enum):
    LEAD = "Lead"
    MANAGER = "Manager"
    SENIOR_MANAGER = "Senior Manager"
    DIRECTOR = "Director"
    AVP = "AVP"
    VP = "VP"
    HEAD = "Head"
    CHIEF_OF_STAFF = "Chief of Staff"
    EXECUTIVE = "Executive"
    ENTRY_MID = "Entry/Mid (Ineligible)"


class ApplicationStatus(str, Enum):
    SUBMITTED = "Submitted"
    FAILED = "Failed"
    PENDING_VERIFICATION = "Pending Verification"
    SKIPPED_CAP_REACHED = "Skipped: Company Cap Reached"
    SKIPPED_COOLOFF = "Skipped: Platform Cooloff"
    SKIPPED_BLACKLISTED = "Skipped: Blacklisted"
    SKIPPED_INELIGIBLE = "Skipped: Ineligible"


@dataclass(frozen=True)
class CandidateIdentity:
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone_formatted: str
    phone_digits: str
    country_code: str
    linkedin_url: str
    website_url: str
    github_url: str = ""
    twitter_url: str = ""


@dataclass(frozen=True)
class CandidateLocation:
    country: str
    state: str
    city: str
    postal_code: str
    neighborhood: str
    full_address: str
    target_hubs: Tuple[str, ...]
    willing_to_relocate: bool = True
    willing_to_commute_hybrid: bool = True


@dataclass(frozen=True)
class CandidateCompensation:
    current_ctc_inr: int
    current_ctc_lpa: int
    expected_ctc_inr: int
    expected_ctc_lpa: int
    minimum_acceptable_ctc_lpa: int
    currency: str = "INR"


@dataclass(frozen=True)
class CandidateTenure:
    total_years_integer: int
    total_months_integer: int
    notice_period_days: int
    notice_period_months: int
    notice_period_weeks: int


@dataclass(frozen=True)
class CandidateEducationEntry:
    degree_level: str
    degree_name: str
    institution: str
    specialization: str
    start_year: str
    end_year: str
    is_mba: bool
    is_engineering: bool


@dataclass(frozen=True)
class CandidateProfile:
    identity: CandidateIdentity
    location: CandidateLocation
    compensation: CandidateCompensation
    tenure: CandidateTenure
    education: Tuple[CandidateEducationEntry, ...]
    work_authorization_india: bool = True
    work_authorization_us: bool = False
    requires_india_sponsorship: bool = False
    requires_us_sponsorship: bool = True
    gender: str = "Male"
    race_ethnicity: str = "Asian (Indian)"
    is_veteran: bool = False
    has_disability: bool = False
    resume_manifest: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load_from_json(cls, profile_path: Path) -> "CandidateProfile":
        target_path = profile_path
        if not target_path.exists():
            example_path = target_path.parent / "profile.example.json"
            if example_path.exists():
                target_path = example_path
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cand = data["candidate"]
        ident = cand["identity"]
        loc = cand["location"]
        comp = cand["compensation"]
        ten = cand.get("tenure_and_experience") or cand.get("tenure_and_notice") or {}
        auth = cand.get("work_authorization", {})
        demo = cand.get("demographics", {})

        edu_entries = []
        for e in cand.get("education", []):
            edu_entries.append(
                CandidateEducationEntry(
                    degree_level=e.get("degree_level", ""),
                    degree_name=e.get("degree_name", ""),
                    institution=e.get("institution", ""),
                    specialization=e.get("specialization", ""),
                    start_year=str(e.get("start_year", "")),
                    end_year=str(e.get("end_year", "")),
                    is_mba=bool(e.get("is_mba", False)),
                    is_engineering=bool(e.get("is_engineering", False)),
                )
            )

        manifest = {
            "v1": "resumes/V1_GTM_Revenue_Strategy.pdf",
            "v2": "resumes/V2_RevOps.pdf",
            "v3": "resumes/V3_Strategy_Ops_ChiefOfStaff.pdf",
            "v4": "resumes/V4_Program_Management.pdf",
            "v5": "resumes/V5_Customer_Success.pdf",
            "v6": "resumes/V6_Operations_Excellence.pdf",
        }

        return cls(
            identity=CandidateIdentity(
                full_name=ident["full_name"],
                first_name=ident["first_name"],
                last_name=ident["last_name"],
                email=ident["email"],
                phone_formatted=ident["phone_formatted"],
                phone_digits=ident["phone_digits"],
                country_code=ident["country_code"],
                linkedin_url=ident["linkedin_url"],
                website_url=ident.get("website_url", ident["linkedin_url"]),
                github_url=ident.get("github_url", ""),
                twitter_url=ident.get("twitter_url", ""),
            ),
            location=CandidateLocation(
                country=loc["country"],
                state=loc["state"],
                city=loc["city"],
                postal_code=loc["postal_code"],
                neighborhood=loc.get("neighborhood", ""),
                full_address=loc["full_address"],
                target_hubs=tuple(loc.get("target_hubs", ["Bengaluru", "Gurugram", "Hyderabad"])),
                willing_to_relocate=loc.get("willing_to_relocate", True),
                willing_to_commute_hybrid=loc.get("willing_to_commute_hybrid", True),
            ),
            compensation=CandidateCompensation(
                current_ctc_inr=comp["current_ctc_inr"],
                current_ctc_lpa=comp["current_ctc_lpa"],
                expected_ctc_inr=comp["expected_ctc_inr"],
                expected_ctc_lpa=comp["expected_ctc_lpa"],
                minimum_acceptable_ctc_lpa=comp.get("minimum_acceptable_ctc_lpa", 45),
                currency=comp.get("currency", "INR"),
            ),
            tenure=CandidateTenure(
                total_years_integer=int(ten.get("total_years_integer", 9)),
                total_months_integer=int(ten.get("total_months_integer", int(ten.get("total_years_integer", 9)) * 12)),
                notice_period_days=int(ten.get("notice_period_days", 30)),
                notice_period_months=int(ten.get("notice_period_months", 1)),
                notice_period_weeks=int(ten.get("notice_period_weeks", 4)),
            ),
            education=tuple(edu_entries),
            work_authorization_india=auth.get("authorized_in_india", True),
            work_authorization_us=auth.get("authorized_in_us", False),
            requires_india_sponsorship=auth.get("requires_india_sponsorship", False),
            requires_us_sponsorship=auth.get("requires_us_sponsorship", True),
            gender=demo.get("gender", "Male"),
            race_ethnicity=demo.get("race_ethnicity", "Asian (Indian)"),
            is_veteran=demo.get("is_veteran", False),
            has_disability=demo.get("has_disability", False),
            resume_manifest=manifest,
        )


@dataclass
class JobPosting:
    company: str
    title: str
    location: str
    url: str
    ats_platform: ATSPlatform
    requisition_id: Optional[str] = None
    job_description: str = ""
    salary_raw: Optional[str] = None
    created_at: Optional[str] = None


@dataclass
class EligibilityDecision:
    is_eligible: bool
    pillar: Pillar
    seniority: SeniorityLevel
    target_resume: str  # Relative path e.g. resumes/V2_RevOps.pdf
    matched_track: str
    reason: str
    confidence_score: float = 1.0


@dataclass
class FormField:
    name: str
    label: str
    field_type: str  # text, number, select, radio, checkbox, file, textarea
    required: bool = False
    help_text: str = ""
    options: List[str] = field(default_factory=list)
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    selector: Optional[str] = None


@dataclass
class ResolvedAnswer:
    field_name: str
    value: Any
    unit_applied: str  # e.g. 'lpa', 'full_digits', 'days', 'months', 'boolean'
    rationale: str
    is_verified: bool = True


@dataclass
class ApplicationResult:
    job_id: Optional[int]
    company: str
    title: str
    ats_platform: str
    status: ApplicationStatus
    proof_path: Optional[str] = None
    confirmation_text: Optional[str] = None
    error_message: Optional[str] = None
    execution_time_seconds: float = 0.0
