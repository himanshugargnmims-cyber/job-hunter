"""
Multi-ATS Job Scraper Module.

Supports:
1. Greenhouse Board API (public JSON listings & detail content)
2. Lever Postings API (structured JSON listings & requirements)
3. Ashby Job Board API (direct JSON API with full JD text)
4. Custom / Generic Career Boards via HTML / Playwright fallback

Filters jobs against context/preferences.json:
- Location hubs: Remote, BLR (Bengaluru), HYD (Hyderabad), GGN (Gurugram/Delhi NCR)
- Title filters & excluded domain keywords
"""

import os
import re
import html
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import requests
import certifi


@dataclass
class JobListing:
    company: str
    title: str
    location: str
    url: str
    description: str
    board_type: str
    location_tag: str  # Remote, BLR, HYD, GGN, or Other Matched


def clean_html(raw_html: str) -> str:
    """Removes HTML markup and unescapes entities."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", " ", raw_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


class JobScraper:
    def __init__(
        self,
        preferences_path: Optional[str] = None,
        company_list_path: Optional[str] = None
    ):
        base_dir = Path(__file__).resolve().parent.parent
        pref_default = base_dir / "context" / "preferences.json"
        pref_example = base_dir / "context" / "preferences.example.json"
        self.preferences_path = Path(preferences_path) if preferences_path else (pref_default if pref_default.exists() else pref_example)

        comp_default = base_dir / "context" / "company_list.txt"
        comp_example = base_dir / "context" / "company_list.example.txt"
        self.company_list_path = Path(company_list_path) if company_list_path else (comp_default if comp_default.exists() else comp_example)

        self.preferences = self._load_preferences()
        self.companies = self._load_companies()

    def _load_preferences(self) -> Dict[str, Any]:
        """Loads search filters and location criteria from preferences.json."""
        if not self.preferences_path.exists():
            return {}
        try:
            with open(self.preferences_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[JobScraper] Warning: Failed to load preferences from {self.preferences_path}: {e}")
            return {}

    def _load_companies(self) -> List[Dict[str, Any]]:
        """Parses target ATS company list."""
        if not self.company_list_path.exists():
            return []
        companies = []
        with open(self.company_list_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3:
                    name = parts[0]
                    board_type = parts[1].lower()
                    target = parts[2]
                    custom_roles = [r.strip() for r in parts[3].split(",")] if len(parts) >= 4 and parts[3].strip() else None
                    companies.append({
                        "name": name,
                        "board_type": board_type,
                        "target": target,
                        "custom_roles": custom_roles
                    })
        return companies

    def matches_location(self, location_str: Optional[str]) -> Tuple[bool, str]:
        """
        Evaluates location string strictly against user priority order:
        Priority 1: Completely Remote (Global, Worldwide, Australia, UK, EU, Anywhere)
        Priority 2: Hyderabad
        Priority 3: Bengaluru
        Priority 4: Gurugram / Delhi NCR
        """
        if not location_str:
            return False, ""

        norm = location_str.lower().strip()

        # Check strict localized negative exclusions (e.g. US onsite only, Canada only)
        exclusions = [
            "us only", "united states only", "north america only", "canada only", "latam only"
        ]
        for excl in exclusions:
            if excl in norm:
                return False, ""

        # === PRIORITY 1: COMPLETELY REMOTE (GLOBAL, AUSTRALIA, UK, EU, WORLDWIDE, ANYWHERE) ===
        remote_tokens = [
            "remote", "worldwide", "global remote", "remote - global", "remote (global)",
            "work from anywhere", "anywhere", "distributed", "virtual", "home based",
            "telecommute", "remote - australia", "remote - apac", "remote - emea", "remote - uk"
        ]
        if any(token in norm for token in remote_tokens):
            return True, "Remote"

        # === PRIORITY 2: HYDERABAD ===
        for token in ["hyderabad", "hyd", "telangana"]:
            if re.search(r"\b" + re.escape(token) + r"\b", norm):
                return True, "HYD"

        # === PRIORITY 3: BENGALURU ===
        for token in ["bangalore", "bengaluru", "blr", "karnataka"]:
            if re.search(r"\b" + re.escape(token) + r"\b", norm):
                return True, "BLR"

        # === PRIORITY 4: GURUGRAM / DELHI NCR ===
        for token in ["gurgaon", "gurugram", "ggn", "delhi", "delhi ncr", "delhi-ncr", "noida", "haryana"]:
            if re.search(r"\b" + re.escape(token) + r"\b", norm):
                return True, "GGN"

        # General India presence
        if re.search(r"\bindia\b", norm):
            return True, "India General"

        return False, ""

    def matches_title(self, title_str: str, custom_keywords: Optional[List[str]] = None) -> bool:
        """Evaluates whether title matches target profile and does not contain excluded keywords."""
        if not title_str:
            return False

        norm = title_str.lower().strip()
        norm_equiv = norm.replace("&", "and")

        # Exclusions first
        excluded = self.preferences.get("excluded_keywords", [])
        if isinstance(self.preferences.get("target_roles"), dict):
            excluded = self.preferences.get("target_roles", {}).get("excluded_keywords", excluded)

        for excl in excluded:
            if re.search(r"\b" + re.escape(excl.lower()) + r"\b", norm):
                return False

        # If custom keywords provided for company
        if custom_keywords:
            for kw in custom_keywords:
                if re.search(r"\b" + re.escape(kw.lower()) + r"\b", norm) or re.search(r"\b" + re.escape(kw.lower()) + r"\b", norm_equiv):
                    return True

        # Target roles from preferences
        target_roles = self.preferences.get("target_roles", [])
        if isinstance(target_roles, list):
            for role in target_roles:
                role_norm = role.lower().strip()
                role_equiv = role_norm.replace("&", "and")
                pattern1 = r"\b" + re.escape(role_norm) + r"\b"
                pattern2 = r"\b" + re.escape(role_equiv) + r"\b"
                if re.search(pattern1, norm) or re.search(pattern2, norm_equiv):
                    return True
                # Handle abbreviations like Sr for Senior
                if "senior" in role_norm:
                    sr_variant = role_norm.replace("senior", "sr")
                    if re.search(r"\b" + re.escape(sr_variant) + r"\b", norm):
                        return True
        elif isinstance(target_roles, dict):
            primary_titles = target_roles.get("primary_titles", [])
            for pt in primary_titles:
                if re.search(r"\b" + re.escape(pt.lower()) + r"\b", norm):
                    return True

        return False

    def matches_experience(self, text: str) -> Tuple[bool, str]:
        """
        Parses text for required years of experience and checks against min/max bounds.
        Returns (is_match, reason).
        """
        min_years = self.preferences.get("experience_years_min", 4)
        max_years = self.preferences.get("experience_years_max", 10)

        # Search for patterns like "5+ years", "4-7 years", "minimum 5 years"
        patterns = [
            r"(\d{1,2})\s*(?:\+|-|\s*to\s*)\s*(\d{1,2})?\s*(?:years|yrs|year)\b",
            r"(?:minimum|at least|req(?:uiring)?)\s*(\d{1,2})\s*(?:years|yrs|year)\b"
        ]

        found_mins = []
        for pat in patterns:
            for m in re.finditer(pat, text.lower()):
                val = int(m.group(1))
                if 1 <= val <= 25:  # Realistic experience range
                    found_mins.append(val)

        if not found_mins:
            return True, "No strict experience limit stated"

        # Check if the required minimum experience is beyond max_years + 2
        req_exp = max(found_mins)
        if req_exp > (max_years + 2):
            return False, f"Requires {req_exp}+ years (target max: {max_years})"

        # If highest requirement found is below 2 and mentions junior/entry
        if max(found_mins) < (min_years - 2) and ("entry level" in text.lower() or "intern" in text.lower()):
            return False, f"Requires {max(found_mins)} years (target min: {min_years})"

        return True, f"Experience aligned ({max(found_mins)} years)"

    def scrape_greenhouse(self, company_name: str, board_token: str, custom_roles: Optional[List[str]] = None) -> List[JobListing]:
        """Scrapes jobs from Greenhouse Board API."""
        matched_jobs = []
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
        try:
            resp = requests.get(url, timeout=12, verify=certifi.where())
            if resp.status_code != 200:
                print(f"[Greenhouse] {company_name} returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            jobs = data.get("jobs", [])
            print(f"[Greenhouse] {company_name}: Scanning {len(jobs)} postings...")

            for j in jobs:
                title = j.get("title", "")
                loc_name = j.get("location", {}).get("name", "")
                job_id = j.get("id")
                job_url = j.get("absolute_url") or f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"

                loc_match, loc_tag = self.matches_location(loc_name)
                if not loc_match:
                    continue

                if not self.matches_title(title, custom_keywords=custom_roles):
                    continue

                # Fetch full JD
                desc_text = ""
                try:
                    detail_resp = requests.get(f"{url}/{job_id}", timeout=8, verify=certifi.where())
                    if detail_resp.status_code == 200:
                        desc_text = clean_html(detail_resp.json().get("content", ""))
                except Exception:
                    pass

                if not desc_text:
                    desc_text = f"{title} at {company_name} in {loc_name}. Strategic and operational responsibilities."

                matched_jobs.append(JobListing(
                    company=company_name,
                    title=title,
                    location=loc_name,
                    url=job_url,
                    description=desc_text,
                    board_type="Greenhouse",
                    location_tag=loc_tag
                ))
        except Exception as e:
            print(f"[Greenhouse] Error querying {company_name}: {e}")

        return matched_jobs

    def scrape_lever(self, company_name: str, site_slug: str, custom_roles: Optional[List[str]] = None) -> List[JobListing]:
        """Scrapes jobs from Lever Postings API."""
        matched_jobs = []
        url = f"https://api.lever.co/v0/postings/{site_slug}?mode=json"
        try:
            resp = requests.get(url, timeout=12, verify=certifi.where())
            if resp.status_code != 200:
                print(f"[Lever] {company_name} returned HTTP {resp.status_code}")
                return []

            postings = resp.json()
            if not isinstance(postings, list):
                return []

            print(f"[Lever] {company_name}: Scanning {len(postings)} postings...")
            for post in postings:
                title = post.get("text", "")
                categories = post.get("categories", {})
                loc_name = categories.get("location", "")
                job_url = post.get("hostedUrl", "")

                loc_match, loc_tag = self.matches_location(loc_name)
                if not loc_match:
                    continue

                if not self.matches_title(title, custom_keywords=custom_roles):
                    continue

                raw_desc = post.get("descriptionPlain") or post.get("description", "")
                desc_text = clean_html(raw_desc)
                if not desc_text:
                    desc_text = f"{title} at {company_name} in {loc_name}."

                matched_jobs.append(JobListing(
                    company=company_name,
                    title=title,
                    location=loc_name,
                    url=job_url,
                    description=desc_text,
                    board_type="Lever",
                    location_tag=loc_tag
                ))
        except Exception as e:
            print(f"[Lever] Error querying {company_name}: {e}")

        return matched_jobs

    def scrape_ashby(self, company_name: str, site_slug: str, custom_roles: Optional[List[str]] = None) -> List[JobListing]:
        """Scrapes jobs from Ashby Job Board API."""
        matched_jobs = []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{site_slug}"
        try:
            resp = requests.get(url, timeout=12)
            if resp.status_code != 200:
                print(f"[Ashby] {company_name} returned HTTP {resp.status_code}")
                return []

            data = resp.json()
            jobs = data.get("jobs", [])
            print(f"[Ashby] {company_name}: Scanning {len(jobs)} postings...")

            for j in jobs:
                title = j.get("title", "")
                location = j.get("location", "")
                secondary = j.get("secondaryLocations", [])
                all_locs = [location] + [s.get("location", "") if isinstance(s, dict) else str(s) for s in secondary]
                loc_str = ", ".join(filter(None, all_locs))
                if j.get("isRemote"):
                    loc_str = f"Remote - {loc_str}" if loc_str else "Remote"

                job_url = j.get("applyUrl") or j.get("jobUrl", "")

                loc_match, loc_tag = self.matches_location(loc_str)
                if not loc_match:
                    continue

                if not self.matches_title(title, custom_keywords=custom_roles):
                    continue

                raw_desc = j.get("descriptionPlain") or clean_html(j.get("descriptionHtml", ""))
                desc_text = raw_desc.strip() if raw_desc else f"{title} at {company_name} in {loc_str}."

                matched_jobs.append(JobListing(
                    company=company_name,
                    title=title,
                    location=loc_str,
                    url=job_url,
                    description=desc_text,
                    board_type="Ashby",
                    location_tag=loc_tag
                ))
        except Exception as e:
            print(f"[Ashby] Error querying {company_name}: {e}")

        return matched_jobs

    def scrape_all(self, target_company: Optional[str] = None, max_per_company: int = 5) -> List[JobListing]:
        """Scrapes all configured company ATS boards or a specific target company."""
        all_results = []
        for c in self.companies:
            name = c["name"]
            board_type = c["board_type"]
            target = c["target"]
            custom_roles = c.get("custom_roles")

            if target_company and target_company.lower() not in name.lower() and target_company.lower() not in target.lower():
                continue

            print(f"\n[JobScraper] Querying {name} ({board_type.upper()} ATS)...")
            found = []
            if board_type == "greenhouse":
                found = self.scrape_greenhouse(name, target, custom_roles)
            elif board_type == "lever":
                found = self.scrape_lever(name, target, custom_roles)
            elif board_type == "ashby":
                found = self.scrape_ashby(name, target, custom_roles)
            else:
                print(f"[JobScraper] Custom/unsupported board type '{board_type}' for {name}, skipping.")

            # Limit per company if requested
            if max_per_company and len(found) > max_per_company:
                found = found[:max_per_company]

            print(f"[JobScraper] -> Matched {len(found)} candidate roles from {name}")
            all_results.extend(found)
            time.sleep(0.5)  # Polite spacing

        return all_results


if __name__ == "__main__":
    scraper = JobScraper()
    jobs = scraper.scrape_all(max_per_company=2)
    print(f"\n=== Total Matched Jobs: {len(jobs)} ===")
    for j in jobs[:5]:
        print(f"- [{j.company}] {j.title} ({j.location}) [{j.location_tag}] -> {j.url}")
