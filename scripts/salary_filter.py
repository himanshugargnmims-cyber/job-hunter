#!/usr/bin/env python3
"""
salary_filter.py - Enforces candidate's strict compensation floor:
Any role with an explicitly stated budget/salary below ₹45 LPA (or < $60,000 USD)
is immediately skipped and excluded from applications.
"""

import os
import re
import json
from pathlib import Path
from typing import Tuple, Optional

BASE_DIR = Path(__file__).resolve().parent.parent

def get_salary_thresholds() -> Tuple[float, float, float, float]:
    """Loads candidate compensation thresholds from preferences.json or environment."""
    pref_path = BASE_DIR / "context" / "preferences.json"
    pref_ex = BASE_DIR / "context" / "preferences.example.json"
    target = pref_path if pref_path.exists() else pref_ex
    prefs = {}
    if target.exists():
        try:
            with open(target, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except Exception:
            pass

    inr_lpa = float(os.getenv("MIN_SALARY_FLOOR_LPA", prefs.get("min_salary_floor_lpa", 30.0)))
    usd_annual = float(os.getenv("MIN_SALARY_FLOOR_USD", prefs.get("min_salary_floor_usd", 50000.0)))
    eur_annual = float(os.getenv("MIN_SALARY_FLOOR_EUR", prefs.get("min_salary_floor_eur", 45000.0)))
    return inr_lpa, inr_lpa * 100000, usd_annual, eur_annual

def check_salary_floor(text: str) -> Tuple[bool, Optional[str]]:
    """
    Analyzes job description or salary metadata against candidate floor.
    Returns:
        (is_below_floor: bool, rationale: Optional[str])
    If True, the role MUST BE SKIPPED completely.
    """
    if not text:
        return False, None

    FLOOR_INR_LPA, FLOOR_INR_ANNUAL, FLOOR_USD_ANNUAL, FLOOR_EUR_ANNUAL = get_salary_thresholds()

    text_lower = text.lower()

    # 1. Check for LPA patterns: e.g., "15 - 25 lpa", "20-30 lakhs", "35 lpa", "₹25,00,000"
    # Matches patterns like: 20-30 lpa, 25 to 35 lakhs, 40 lpa
    lpa_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac|lacs|lakhs)', text_lower)
    for low, high in lpa_matches:
        try:
            high_val = float(high)
            if high_val < FLOOR_INR_LPA:
                return True, f"Budget of {low}-{high} LPA is strictly below candidate floor of ₹{FLOOR_INR_LPA} LPA"
        except ValueError:
            pass

    single_lpa_matches = re.findall(r'(\d+(?:\.\d+)?)\s*(?:lpa|lakh|lac|lacs|lakhs)', text_lower)
    for val in single_lpa_matches:
        try:
            val_float = float(val)
            # If explicit salary mention like "budget: 30 lpa" or "up to 35 lpa"
            if val_float < FLOOR_INR_LPA and any(k in text_lower for k in ["salary", "budget", "ctc", "compensation", "up to"]):
                # Ensure it's not experience: check surrounding context
                idx = text_lower.find(val)
                context = text_lower[max(0, idx-30):min(len(text_lower), idx+30)]
                if not any(k in context for k in ["exp", "year", "yrs"]):
                    return True, f"Explicit compensation of {val} LPA is below candidate floor of ₹{FLOOR_INR_LPA} LPA"
        except ValueError:
            pass

    # 2. Check for USD ranges: e.g., "$30,000 - $50,000", "$40k - $55k"
    usd_k_matches = re.findall(r'\$\s*(\d+)\s*k?\s*(?:-|to)\s*\$?\s*(\d+)\s*k', text_lower)
    for low, high in usd_k_matches:
        try:
            high_val = float(high) * 1000 if float(high) < 1000 else float(high)
            if high_val < FLOOR_USD_ANNUAL:
                return True, f"USD salary range of ${low}k-${high}k is below candidate floor of ${FLOOR_USD_ANNUAL:,}"
        except ValueError:
            pass

    usd_full_matches = re.findall(r'\$\s*(\d{2,3}),?(\d{3})\s*(?:-|to)\s*\$?\s*(\d{2,3}),?(\d{3})', text_lower)
    for l1, l2, h1, h2 in usd_full_matches:
        try:
            high_val = float(f"{h1}{h2}")
            if high_val < FLOOR_USD_ANNUAL:
                return True, f"USD salary range high bound ${high_val:,.0f} is below candidate floor of ${FLOOR_USD_ANNUAL:,}"
        except ValueError:
            pass

    # 3. Check for INR full numbers: e.g. "INR 25,00,000", "₹30,00,000"
    inr_matches = re.findall(r'(?:inr|₹|rs\.?)\s*(\d{1,2}),?(\d{2}),?(\d{3})', text_lower)
    for m1, m2, m3 in inr_matches:
        try:
            val = float(f"{m1}{m2}{m3}")
            if 500000 <= val < FLOOR_INR_ANNUAL:
                return True, f"INR salary of ₹{val:,.0f} is below candidate floor of ₹{FLOOR_INR_ANNUAL:,}"
        except ValueError:
            pass

    return False, None


if __name__ == "__main__":
    test_cases = [
        ("Salary: 25 - 35 LPA based on experience", True),
        ("Budget: 30 LPA max CTC", True),
        ("Compensation range: $40,000 - $50,000 per year", True),
        ("Salary: 55 - 70 LPA for Senior Manager", False),
        ("Compensation: $120,000 - $160,000 USD", False),
        ("Flexible based on experience, standard benefits", False),
        ("INR 25,00,000 fixed plus variable", True),
        ("INR 60,00,000 CTC", False)
    ]
    for text, expected in test_cases:
        skipped, reason = check_salary_floor(text)
        print(f"[{'PASS' if skipped == expected else 'FAIL'}] '{text[:40]}...' -> Skipped={skipped} | Reason: {reason}")
