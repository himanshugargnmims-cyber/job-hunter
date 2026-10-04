#!/usr/bin/env python3
"""
discover_ats_jobs.py - Scans verified Greenhouse and Ashby boards for relevant jobs in
Bengaluru, Gurugram/NCR, Hyderabad, and India Remote.
Strictly respects candidate fit and the maximum 2 jobs per company constraint.
"""

import sqlite3
import requests
import re
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"

# Verified active boards from scan
GH_BOARDS = {
    'affirm': 'Affirm', 'airbnb': 'Airbnb', 'apolloio': 'Apollo.io', 'asana': 'Asana',
    'braze': 'Braze', 'brex': 'Brex', 'carta': 'Carta', 'celonis': 'Celonis',
    'checkr': 'Checkr', 'cloudflare': 'Cloudflare', 'cockroachlabs': 'Cockroach Labs',
    'coinbase': 'Coinbase', 'coursera': 'Coursera', 'datadog': 'Datadog',
    'databricks': 'Databricks', 'dataiku': 'Dataiku', 'devrev': 'DevRev',
    'dremio': 'Dremio', 'dropbox': 'Dropbox', 'druva': 'Druva', 'duolingo': 'Duolingo',
    'elastic': 'Elastic', 'ethoslife': 'Ethos Life', 'fivetran': 'Fivetran',
    'flexport': 'Flexport', 'gitlab': 'GitLab', 'gusto': 'Gusto',
    'highradius': 'HighRadius', 'inmobi': 'InMobi', 'instacart': 'Instacart',
    'instawork': 'Instawork', 'intercom': 'Intercom', 'justworks': 'Justworks',
    'klaviyo': 'Klaviyo', 'launchdarkly': 'LaunchDarkly', 'lyft': 'Lyft',
    'mattermost': 'Mattermost', 'mixpanel': 'Mixpanel', 'mongodb': 'MongoDB',
    'monzo': 'Monzo', 'motional': 'Motional', 'netskope': 'Netskope',
    'newrelic': 'New Relic', 'nextdoor': 'Nextdoor', 'okta': 'Okta',
    'pagerduty': 'PagerDuty', 'payoneer': 'Payoneer', 'peloton': 'Peloton',
    'pendo': 'Pendo', 'pinterest': 'Pinterest', 'pubmatic': 'PubMatic',
    'purestorage': 'Pure Storage', 'qualtrics': 'Qualtrics', 'quince': 'Quince',
    'reddit': 'Reddit', 'roblox': 'Roblox', 'robinhood': 'Robinhood',
    'rubrik': 'Rubrik', 'samsara': 'Samsara', 'smartbear': 'SmartBear',
    'sofi': 'SoFi', 'starburst': 'Starburst', 'stripe': 'Stripe',
    'sumologic': 'Sumo Logic', 'tanium': 'Tanium', 'toast': 'Toast',
    'tripactions': 'Navan (TripActions)', 'twilio': 'Twilio', 'twitch': 'Twitch',
    'verkada': 'Verkada', 'workato': 'Workato', 'yext': 'Yext',
    'yugabyte': 'Yugabyte', 'zenoti': 'Zenoti', 'zoominfo': 'ZoomInfo',
    'zscaler': 'Zscaler'
}

ASHBY_BOARDS = {
    'character': 'Character.AI', 'cohere': 'Cohere', 'cursor': 'Cursor (Anysphere)',
    'deepgram': 'Deepgram', 'harvey': 'Harvey', 'hex': 'Hex', 'kong': 'Kong',
    'langchain': 'LangChain', 'linear': 'Linear', 'modal': 'Modal',
    'notion': 'Notion', 'openai': 'OpenAI', 'perplexity': 'Perplexity AI',
    'pinecone': 'Pinecone', 'ramp': 'Ramp', 'replit': 'Replit',
    'resend': 'Resend', 'runway': 'Runway', 'sarvam': 'Sarvam AI',
    'sentry': 'Sentry', 'supabase': 'Supabase', 'synthesia': 'Synthesia',
    'unstructured': 'Unstructured', 'valon': 'Valon', 'vapi': 'Vapi',
    'warp': 'Warp', 'weaviate': 'Weaviate', 'writer': 'Writer',
    'zapier': 'Zapier', 'g2': 'G2'
}

TARGET_LOCATIONS = [
    'bangalore', 'bengaluru', 'hyderabad', 'gurgaon', 'gurugram', 'noida', 'delhi',
    'india', 'remote - india', 'india - remote', 'india, remote', 'remote, india'
]

TITLE_KEYWORDS = [
    'gtm', 'go-to-market', 'go to market', 'revenue', 'revops', 'sales operations',
    'sales ops', 'commercial', 'strategy', 'bizops', 'business operations',
    'chief of staff', 'founders office', "founder's office", 'ceo office', "ceo's office",
    'program manager', 'technical program manager', 'tpm', 'operations',
    'operational excellence', 'customer success', 'customer operations',
    'account management', 'deal desk', 'partnerships', 'enablement', 'escalations'
]

EXCLUDE_TITLE_KEYWORDS = [
    'software engineer', 'backend engineer', 'frontend engineer', 'ios engineer',
    'android engineer', 'machine learning engineer', 'ml engineer', 'data engineer',
    'security engineer', 'qa engineer', 'sre', 'devops engineer', 'site reliability',
    'legal counsel', 'recruiter', 'talent acquisition', 'payroll specialist',
    'graphic designer', 'intern', 'internship', 'undergraduate', 'phd'
]

def get_existing_company_counts() -> Dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT company, count(*) FROM jobs GROUP BY company")
    counts = {row[0].strip().lower(): row[1] for row in c.fetchall()}
    conn.close()
    return counts

def is_target_location(loc_str: str) -> bool:
    if not loc_str:
        return False
    loc = loc_str.lower()
    return any(t in loc for t in TARGET_LOCATIONS)

def is_matching_title(title_str: str) -> bool:
    if not title_str:
        return False
    title = title_str.lower()
    if any(ex in title for ex in EXCLUDE_TITLE_KEYWORDS):
        return False
    return any(k in title for k in TITLE_KEYWORDS)

def scan_greenhouse(existing_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for board_token, company_name in GH_BOARDS.items():
        comp_key = company_name.lower()
        curr_count = existing_counts.get(comp_key, 0)
        # Check alias / token match too
        token_count = existing_counts.get(board_token.lower(), 0)
        total_for_company = max(curr_count, token_count)
        if total_for_company >= 2:
            continue
        
        remaining_slots = 2 - total_for_company
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            data = r.json()
            jobs = data.get("jobs", [])
            matched_for_comp = 0
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                job_url = j.get("absolute_url", "")
                if not job_url:
                    continue
                # Canonicalize URL to direct boards URL
                if "job-boards.greenhouse.io" not in job_url and "boards.greenhouse.io" in job_url:
                    job_url = job_url.replace("boards.greenhouse.io", "job-boards.greenhouse.io")
                
                if is_target_location(loc) and is_matching_title(title):
                    results.append({
                        "company": company_name,
                        "board_token": board_token,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "board_type": "Direct - Greenhouse"
                    })
                    matched_for_comp += 1
                    if matched_for_comp >= remaining_slots:
                        break
        except Exception as e:
            pass
    return results

def scan_ashby(existing_counts: Dict[str, int]) -> List[Dict[str, Any]]:
    results = []
    headers = {"User-Agent": "Mozilla/5.0"}
    for org_name, company_name in ASHBY_BOARDS.items():
        comp_key = company_name.lower()
        curr_count = existing_counts.get(comp_key, 0)
        org_count = existing_counts.get(org_name.lower(), 0)
        total_for_company = max(curr_count, org_count)
        if total_for_company >= 2:
            continue
        
        remaining_slots = 2 - total_for_company
        try:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{org_name}"
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code != 200:
                continue
            data = r.json()
            jobs = data.get("jobs", [])
            matched_for_comp = 0
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", "")
                job_id = j.get("id", "")
                job_url = f"https://jobs.ashbyhq.com/{org_name}/{job_id}/application"
                
                # Check secondary locations
                locs_list = [loc]
                for sec in j.get("secondaryLocations", []):
                    if isinstance(sec, dict) and "location" in sec:
                        locs_list.append(sec["location"])
                    elif isinstance(sec, str):
                        locs_list.append(sec)
                
                is_loc = any(is_target_location(l) for l in locs_list)
                if is_loc and is_matching_title(title):
                    results.append({
                        "company": company_name,
                        "board_token": org_name,
                        "title": title,
                        "location": loc if is_target_location(loc) else "India / Remote",
                        "url": job_url,
                        "board_type": "Direct - Ashby"
                    })
                    matched_for_comp += 1
                    if matched_for_comp >= remaining_slots:
                        break
        except Exception as e:
            pass
    return results

if __name__ == "__main__":
    existing = get_existing_company_counts()
    print(f"Existing companies in DB with counts: {len(existing)}")
    gh_matches = scan_greenhouse(existing)
    ashby_matches = scan_ashby(existing)
    print(f"\n--- Discovered Greenhouse Roles ({len(gh_matches)}) ---")
    for m in gh_matches:
        print(f"[{m['company']}] {m['title']} | {m['location']} | {m['url']}")
    
    print(f"\n--- Discovered Ashby Roles ({len(ashby_matches)}) ---")
    for m in ashby_matches:
        print(f"[{m['company']}] {m['title']} | {m['location']} | {m['url']}")
