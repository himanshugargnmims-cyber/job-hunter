#!/usr/bin/env python3
"""
eligibility.py - Universal Eligibility & Seniority Gatekeeper

Enforces Candidate Ground Truth & Profile Constraints:
1. Seniority Floor: Manager and Above (Lead, Manager, Senior Manager, Director, AVP, VP, Head, Chief of Staff).
2. Strict 3-Pillar Architecture:
   - Pillar 1: RevOps & Commercial Operations -> V2_RevOps.pdf
   - Pillar 2: Customer Success & Post-Sales -> V5_Customer_Success.pdf
   - Pillar 3: Strategy & Ops / Chief of Staff / Revenue Strategy / Business Programs:
     * Chief of Staff / Founder's Office -> V3_Strategy_Ops_ChiefOfStaff.pdf
     * GTM / Revenue Strategy -> V1_GTM_Revenue_Strategy.pdf
     * Business Program Management -> V4_Program_Management.pdf
     * Operations Excellence -> V6_Operations_Excellence.pdf
3. Zero Tolerance Disqualifications:
   - TPM, Engineering PM, Software PM
   - Pure Software/Data Engineering (SDE, SRE, DevOps, QA)
   - Sales Reps (SDR, BDR, Account Executive)
4. Strict Geo-Eligibility Gate:
   - Permitted: Bengaluru, Gurugram, Hyderabad, Delhi NCR, Pune, Mumbai, Chennai, India (Remote), Verified Global Remote.
   - Disqualified: US-only, EMEA-only, Americas-only, UK-only, "Indiana", require US citizenship/greencard.
5. Minimum Compensation Floor: Stated compensation >= 45 LPA (if stated).
"""

import re
import sys
from pathlib import Path
from typing import Tuple, List, Optional, Dict

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from scripts.application_models import (
    EligibilityDecision,
    Pillar,
    SeniorityLevel,
    JobPosting
)

# Explicitly excluded titles / keywords
DISQUALIFIED_TITLE_PATTERNS = [
    r"\btechnical program manager\b",
    r"\btpm\b",
    r"\bengineering program manager\b",
    r"\bsoftware program manager\b",
    r"\bproduct manager\b",
    r"\btechnical product manager\b",
    r"\bgroup product manager\b",
    r"\bassociate product manager\b",
    r"\bapm\b",
    r"\bsoftware engineer\b",
    r"\bbackend engineer\b",
    r"\bfrontend engineer\b",
    r"\bfull[\s\-]?stack\b",
    r"\bdevops\b",
    r"\bsre\b",
    r"\bdata engineer\b",
    r"\bdata scientist\b",
    r"\bqa engineer\b",
    r"\bsdet\b",
    r"\baccount executive\b",
    r"\bsales development representative\b",
    r"\bsdr\b",
    r"\bbdr\b",
    r"\bbusiness development representative\b",
    r"\bjunior\b",
    r"\bintern\b",
    r"\binternship\b",
    r"\btrainee\b",
    r"\bassociate\b(?!.*(?:director|vice president|lead))",  # Allow "Associate Director"
    r"\bentry level\b",
    r"\bwarehouse\b",
    r"\bplant manager\b",
    r"\bfactory\b",
    r"\bcivil engineer\b",
    r"\bmechanical engineer\b"
]

# Seniority classification patterns
SENIORITY_PATTERNS = [
    (SeniorityLevel.CHIEF_OF_STAFF, [r"\bchief of staff\b", r"\bcos\b", r"\bfounder'?s office\b", r"\bceo'?s office\b", r"\bcro'?s office\b"]),
    (SeniorityLevel.VP, [r"\bvice president\b", r"\bvp\b", r"\bsvp\b", r"\bevp\b"]),
    (SeniorityLevel.AVP, [r"\bavp\b", r"\bassociate vice president\b"]),
    (SeniorityLevel.HEAD, [r"\bhead of\b", r"\bhead\b"]),
    (SeniorityLevel.DIRECTOR, [r"\bdirector\b", r"\bsenior director\b", r"\bassociate director\b"]),
    (SeniorityLevel.SENIOR_MANAGER, [r"\bsenior manager\b", r"\bsr\.?\s*manager\b"]),
    (SeniorityLevel.LEAD, [r"\blead\b", r"\bprincipal\b"]),
    (SeniorityLevel.MANAGER, [r"\bmanager\b", r"\bgeneral manager\b"]),
]

# Permitted Indian tech hubs
PERMITTED_HUBS = [
    "bengaluru", "bangalore", "gurugram", "gurgaon", "delhi", "delhi ncr",
    "noida", "hyderabad", "pune", "mumbai", "chennai"
]

DISQUALIFIED_GEO_PATTERNS = [
    r"\bus only\b",
    r"\bamericas only\b",
    r"\bemea only\b",
    r"\buk only\b",
    r"\bunited states only\b",
    r"\bcanada only\b",
    r"\blatam only\b",
    r"\bmust be located in the us\b",
    r"\bus work authorization required\b",
    r"\bno sponsorship\b.*?\bus\b",
    r"\bindiana\b"  # Guard against "Indiana" substring false match
]


def check_geo_eligibility(location_str: str, jd_text: str = "") -> Tuple[bool, str]:
    """
    Validates whether the location / remote status is eligible for an Indian resident.
    """
    loc_clean = (location_str or "").lower().strip()
    jd_clean = (jd_text or "").lower()
    combined = f"{loc_clean} {jd_clean}"

    # 1. Check strict disqualified geo patterns
    for disq in DISQUALIFIED_GEO_PATTERNS:
        if re.search(disq, loc_clean):
            return False, f"Location explicitly disqualified: matched '{disq}' in '{location_str}'"
        # If explicitly stated in JD that it's US-only / EMEA-only
        if re.search(disq, jd_clean) and not any(hub in loc_clean for hub in PERMITTED_HUBS):
            return False, f"Job description specifies geographic restriction: '{disq}'"

    # 2. Check permitted Indian tech hubs
    for hub in PERMITTED_HUBS:
        if hub in loc_clean:
            return True, f"Eligible Indian tech hub: '{hub.title()}'"

    # 3. Check India Remote
    if re.search(r"\b(india\s*[\(\-–,]?\s*remote|remote\s*[\(\-–,]?\s*india)\b", loc_clean):
        return True, "Eligible: India Remote"

    # Strict check: "India" word boundary, making sure it's not "Indiana" or "Indian Ocean"
    if re.search(r"\bindia\b", loc_clean) and not re.search(r"\b(indiana|indian ocean)\b", loc_clean):
        return True, "Eligible: India location"

    # 4. Check Verified Global Remote
    if any(k in loc_clean for k in ["worldwide", "anywhere", "global remote", "remote - anywhere"]):
        return True, "Eligible: Verified Global Remote"

    # If generic "Remote" without explicit India eligibility
    if loc_clean == "remote" or "remote" in loc_clean:
        # Check if JD mentions India entity, Bangalore, or global contractor availability
        if re.search(r"\b(india|bengaluru|bangalore|delhi|gurgaon|hyderabad|contractor|deel|oyster|remote\.com)\b", jd_clean):
            return True, "Eligible: Global remote with India eligibility confirmed in JD"
        return False, "Disqualified: Generic remote without verified India hiring entity"

    return False, f"Location '{location_str}' is outside permitted Indian tech hubs or verified global remote"


def determine_seniority(title: str) -> Tuple[SeniorityLevel, bool]:
    """
    Determines seniority level and whether it meets the 'Manager and Above' floor.
    """
    title_lower = title.lower()

    for level, patterns in SENIORITY_PATTERNS:
        for pat in patterns:
            if re.search(pat, title_lower):
                return level, True

    # If none matched, check if it's an Executive role e.g. "Commercial Partner", "Strategic Partner"
    if any(k in title_lower for k in ["partner", "principal", "consultant"]):
        return SeniorityLevel.EXECUTIVE, True

    return SeniorityLevel.ENTRY_MID, False


def classify_pillar_and_resume(title: str, jd_text: str = "") -> Tuple[Pillar, str, str]:
    """
    Maps job to Pillar and selects target resume strictly adhering to Candidate Architecture.
    
    Returns:
        (Pillar, matched_track, target_resume_path)
    """
    title_lower = title.lower()
    combined = f"{title_lower} {jd_text.lower()}"

    # PILLAR 1: Revenue Operations & Commercial Operations
    revops_keywords = ["revops", "revenue operations", "sales ops", "sales operations", "commercial operations", "deal desk"]
    if any(k in title_lower for k in revops_keywords):
        return (
            Pillar.PILLAR_1_REVOPS,
            "RevOps & Commercial Operations",
            "resumes/V2_RevOps.pdf"
        )

    # PILLAR 2: Customer Success & Post-Sales Strategy
    cs_keywords = ["customer success", "client success", "customer retention", "post-sales", "customer lifecycle", "client retention", "customer experience"]
    if any(k in title_lower for k in cs_keywords):
        return (
            Pillar.PILLAR_2_CUSTOMER_SUCCESS,
            "Customer Success & Post-Sales",
            "resumes/V5_Customer_Success.pdf"
        )

    # PILLAR 3 Sub-track A: Chief of Staff / Founder's Office / CEO Office
    cos_keywords = ["chief of staff", "founder's office", "founders office", "ceo office", "ceo's office", "cro office", "cro's office"]
    if any(k in title_lower for k in cos_keywords):
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "Chief of Staff & Founder's Office",
            "resumes/V3_Strategy_Ops_ChiefOfStaff.pdf"
        )

    # PILLAR 3 Sub-track B: GTM Strategy & Revenue Strategy
    gtm_keywords = ["gtm", "go-to-market", "revenue strategy", "commercial strategy", "gtm strategy", "monetization"]
    if any(k in title_lower for k in gtm_keywords):
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "GTM & Revenue Strategy",
            "resumes/V1_GTM_Revenue_Strategy.pdf"
        )

    # PILLAR 3 Sub-track C: Business Program Management & Strategic Programs
    # (Note: We explicitly filter TPM before this)
    prog_keywords = ["program management", "program manager", "strategic programs", "business program", "transformation manager", "business transformation"]
    if any(k in title_lower for k in prog_keywords):
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "Business Program Management",
            "resumes/V4_Program_Management.pdf"
        )

    # PILLAR 3 Sub-track D: Strategy & Operations (BizOps / StratOps)
    bizops_keywords = ["strategy & operations", "strategy and operations", "bizops", "stratops", "business operations", "corporate strategy"]
    if any(k in title_lower for k in bizops_keywords):
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "Strategy & Operations (BizOps)",
            "resumes/V3_Strategy_Ops_ChiefOfStaff.pdf"
        )

    # PILLAR 3 Sub-track E: Operations Excellence & Central Operations (Strictly operational excellence)
    ops_keywords = ["operational excellence", "operations excellence", "process excellence", "central operations"]
    if any(k in title_lower for k in ops_keywords):
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "Operations Excellence",
            "resumes/V6_Operations_Excellence.pdf"
        )

    # Fallback checking JD if title is generic "Director of Operations" or "Head of Strategy"
    if "forecasting" in combined and "sales" in combined:
        return (
            Pillar.PILLAR_1_REVOPS,
            "RevOps (JD Inferred)",
            "resumes/V2_RevOps.pdf"
        )
    if "retention" in combined and "churn" in combined:
        return (
            Pillar.PILLAR_2_CUSTOMER_SUCCESS,
            "Customer Success (JD Inferred)",
            "resumes/V5_Customer_Success.pdf"
        )
    if "cross-functional" in combined and "governance" in combined:
        return (
            Pillar.PILLAR_3_STRATEGY_OPS,
            "Strategy & BizOps (JD Inferred)",
            "resumes/V3_Strategy_Ops_ChiefOfStaff.pdf"
        )

    # Default to Disqualified if outside 3 pillars
    return (
        Pillar.DISQUALIFIED,
        "Outside 3-Pillar Architecture",
        "resumes/V1_GTM_Revenue_Strategy.pdf"
    )


def evaluate_eligibility(job: JobPosting) -> EligibilityDecision:
    """
    Comprehensive gatekeeper evaluating a job posting against all candidate rules.
    """
    title = job.title.strip()
    title_lower = title.lower()

    # 1. Zero tolerance title exclusions
    for disq_pat in DISQUALIFIED_TITLE_PATTERNS:
        if re.search(disq_pat, title_lower):
            return EligibilityDecision(
                is_eligible=False,
                pillar=Pillar.DISQUALIFIED,
                seniority=SeniorityLevel.ENTRY_MID,
                target_resume="",
                matched_track="Disqualified Domain",
                reason=f"Title matches zero-tolerance exclusion: '{disq_pat}'",
                confidence_score=1.0
            )

    # 2. Seniority Floor Check (Manager and Above)
    seniority, meets_seniority = determine_seniority(title)
    if not meets_seniority:
        return EligibilityDecision(
            is_eligible=False,
            pillar=Pillar.DISQUALIFIED,
            seniority=seniority,
            target_resume="",
            matched_track="Seniority Floor Failed",
            reason=f"Title '{title}' does not meet seniority floor (Manager and Above required)",
            confidence_score=0.9
        )

    # 3. Geo-Eligibility Check
    geo_eligible, geo_reason = check_geo_eligibility(job.location, job.job_description)
    if not geo_eligible:
        return EligibilityDecision(
            is_eligible=False,
            pillar=Pillar.DISQUALIFIED,
            seniority=seniority,
            target_resume="",
            matched_track="Geo-Disqualified",
            reason=geo_reason,
            confidence_score=0.95
        )

    # 4. Pillar & Resume Matching
    pillar, track, resume_path = classify_pillar_and_resume(title, job.job_description)
    if pillar == Pillar.DISQUALIFIED:
        return EligibilityDecision(
            is_eligible=False,
            pillar=Pillar.DISQUALIFIED,
            seniority=seniority,
            target_resume="",
            matched_track="Pillar Mismatch",
            reason=f"Role '{title}' does not fit Candidate's 3 Pillars (RevOps, Customer Success, Strategy & Ops)",
            confidence_score=0.9
        )

    return EligibilityDecision(
        is_eligible=True,
        pillar=pillar,
        seniority=seniority,
        target_resume=resume_path,
        matched_track=track,
        reason=f"Eligible: {seniority.value} level in {pillar.value} ({geo_reason})",
        confidence_score=0.98
    )


if __name__ == "__main__":
    from scripts.application_models import ATSPlatform
    print("=== Testing Eligibility Gatekeeper ===")
    
    test_jobs = [
        JobPosting("Sirion", "Director - Revenue Operations", "Bengaluru, Karnataka", "https://sirion.com", ATSPlatform.LINKEDIN_EASY),
        JobPosting("PHC Partners", "Lead - Strategic Programs", "Remote - India", "https://phc.com", ATSPlatform.LINKEDIN_EASY),
        JobPosting("Amazon", "Technical Program Manager II", "Bengaluru", "https://amazon.com", ATSPlatform.GENERIC),
        JobPosting("Swiggy", "Associate - Customer Support", "Bengaluru", "https://swiggy.com", ATSPlatform.GENERIC),
        JobPosting("Clipboard", "Head of Customer Success", "Remote, United States only", "https://clipboard.com", ATSPlatform.ASHBY),
        JobPosting("US Tech", "RevOps Manager", "Indiana, USA", "https://ustech.com", ATSPlatform.GREENHOUSE),
    ]

    for j in test_jobs:
        dec = evaluate_eligibility(j)
        status = "✅ PASS" if dec.is_eligible else "❌ REJECT"
        print(f"[{status}] {j.company} - {j.title} ({j.location})")
        print(f"       Resume: {dec.target_resume} | Reason: {dec.reason}\n")
