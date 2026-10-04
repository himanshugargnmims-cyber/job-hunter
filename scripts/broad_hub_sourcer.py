#!/usr/bin/env python3
"""
broad_hub_sourcer.py - Discovers open positions on Greenhouse and Ashby for
Bengaluru, Gurugram/NCR, Hyderabad, and India Remote.
Strictly checks that the company has < 2 applications in jobs.db!
"""

import requests
import sqlite3
import json
from pathlib import Path
from typing import Dict, List, Any

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"

# Broad candidate board lists
CANDIDATE_GH_BOARDS = [
    'asana', 'braze', 'brex', 'carta', 'checkr', 'cloudflare', 'cockroachlabs',
    'coursera', 'databricks', 'dataiku', 'dropbox', 'druva', 'duolingo',
    'gusto', 'inmobi', 'instacart', 'intercom', 'justworks', 'kargo',
    'klaviyo', 'launchdarkly', 'lyft', 'mattermost', 'mixpanel', 'monzo',
    'motional', 'newrelic', 'nextdoor', 'okta', 'pagerduty', 'peloton',
    'pendo', 'pinterest', 'purestorage', 'qualtrics', 'reddit', 'robinhood',
    'smartbear', 'sofi', 'starburst', 'sumologic', 'tanium', 'twitch',
    'verkada', 'workato', 'yext', 'yugabyte', 'zoominfo', 'airmeet',
    'branch', 'branchmetrics', 'branchinternational', 'browserstack',
    'c3ai', 'chargebee', 'clevertap', 'contentful', 'criteo', 'cultureamp',
    'dremio', 'elastic', 'exotel', 'flywire', 'freshworks', 'front',
    'gong', 'grafana', 'harness', 'hasura', 'heap', 'hightouch', 'hopper',
    'ironclad', 'jumpcloud', 'khatabook', 'leenaai', 'liftoff', 'lucid',
    'medallia', 'moengage', 'mulesoft', 'mural', 'ninjacart', 'nutanix',
    'onepassword', 'outreach', 'paloaltonetworks', 'perimeterx', 'postman',
    'rapid7', 'razorpay', 'resemble', 'ripple', 'segment', 'sentry',
    'shiprocket', 'singlepass', 'slack', 'snyk', 'sprinklr', 'thoughtspot',
    'udaan', 'unity', 'urbancompany', 'veritas', 'vimeo', 'vymo',
    'whatfix', 'yellowai', 'zepto', 'zerodha', 'appliedintuition', 'dremio',
    'cloudera', 'talend', 'snowflake', 'crowdstrike', 'sentinelone'
]

CANDIDATE_ASHBY_BOARDS = [
    'character', 'cohere', 'deepgram', 'hex', 'langchain', 'modal',
    'notion', 'pinecone', 'runway', 'unstructured', 'valon', 'vapi',
    'warp', 'weaviate', 'writer', 'zapier', 'anthropic', 'glean',
    'harvey', 'linear', 'openai', 'perplexity', 'ramp', 'replit',
    'sarvam', 'sentry', 'synthesia', 'g2', 'kong', 'supabase', 'cursor',
    'resend', 'pydantic', 'qdrant', 'scaleapi', 'together', 'weightsandbiases'
]

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
    'account management', 'deal desk', 'partnerships', 'enablement', 'escalations',
    'account executive', 'business development', 'growth', 'specialist', 'lead'
]

EXCLUDE_TITLE_KEYWORDS = [
    'software engineer', 'backend engineer', 'frontend engineer', 'ios engineer',
    'android engineer', 'machine learning engineer', 'ml engineer', 'data engineer',
    'security engineer', 'qa engineer', 'sre', 'devops engineer', 'site reliability',
    'legal counsel', 'recruiter', 'talent acquisition', 'payroll specialist',
    'graphic designer', 'intern', 'internship', 'undergraduate', 'phd',
    'tax', 'audit', 'hardware', 'mechanical', 'chemical', 'biotech'
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

def scan():
    existing_counts = get_existing_company_counts()
    headers = {"User-Agent": "Mozilla/5.0"}
    
    discovered = []
    print("--- Scanning Greenhouse Boards ---")
    for b in CANDIDATE_GH_BOARDS:
        # Check count in DB
        c_count = existing_counts.get(b.lower(), 0)
        if c_count >= 2:
            continue
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{b}/jobs"
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code != 200:
                continue
            jobs = r.json().get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", {}).get("name", "")
                job_url = j.get("absolute_url", "")
                if not job_url:
                    continue
                if "job-boards.greenhouse.io" not in job_url and "boards.greenhouse.io" in job_url:
                    job_url = job_url.replace("boards.greenhouse.io", "job-boards.greenhouse.io")
                
                if is_target_location(loc) and is_matching_title(title):
                    discovered.append({
                        "company": b.capitalize(),
                        "board_token": b,
                        "title": title,
                        "location": loc,
                        "url": job_url,
                        "board_type": "Direct - Greenhouse"
                    })
        except Exception:
            pass

    print(f"Discovered {len(discovered)} Greenhouse candidate roles.")

    print("\n--- Scanning Ashby Boards ---")
    ashby_disc = []
    for a in CANDIDATE_ASHBY_BOARDS:
        c_count = existing_counts.get(a.lower(), 0)
        if c_count >= 2:
            continue
        try:
            url = f"https://api.ashbyhq.com/posting-api/job-board/{a}"
            r = requests.get(url, headers=headers, timeout=4)
            if r.status_code != 200:
                continue
            jobs = r.json().get("jobs", [])
            for j in jobs:
                title = j.get("title", "")
                loc = j.get("location", "")
                job_id = j.get("id", "")
                job_url = f"https://jobs.ashbyhq.com/{a}/{job_id}/application"
                
                locs_list = [loc]
                for sec in j.get("secondaryLocations", []):
                    if isinstance(sec, dict) and "location" in sec:
                        locs_list.append(sec["location"])
                    elif isinstance(sec, str):
                        locs_list.append(sec)
                
                if any(is_target_location(l) for l in locs_list) and is_matching_title(title):
                    ashby_disc.append({
                        "company": a.capitalize(),
                        "board_token": a,
                        "title": title,
                        "location": loc if is_target_location(loc) else "India / Remote",
                        "url": job_url,
                        "board_type": "Direct - Ashby"
                    })
        except Exception:
            pass

    print(f"Discovered {len(ashby_disc)} Ashby candidate roles.")
    
    with open(BASE_DIR / "data" / "fresh_discovered_roles.json", "w") as f:
        json.dump(discovered + ashby_disc, f, indent=2)

    print(f"Total discovered roles written to data/fresh_discovered_roles.json: {len(discovered) + len(ashby_disc)}")

if __name__ == "__main__":
    scan()
