#!/usr/bin/env python3
"""
index_global_remote_universe.py - Aggregates and indexes 500+ established global
remote-first companies that hire worldwide / allow remote work from India.
"""

import requests
import re
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    "https://raw.githubusercontent.com/lukasz-madon/awesome-remote-job/master/README.md",
    "https://raw.githubusercontent.com/yanirs/established-remote/master/README.md"
]

def build_remote_company_index():
    all_companies = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    # Known high-paying remote companies to seed
    seed_companies = [
        {"name": "Clipboard Health", "url": "https://clipboardhealth.com", "ats_slug": "clipboard", "ats_type": "Ashby"},
        {"name": "Automattic", "url": "https://automattic.com", "ats_slug": "automattic", "ats_type": "Direct"},
        {"name": "Sourcegraph", "url": "https://sourcegraph.com", "ats_slug": "sourcegraph91", "ats_type": "Greenhouse"},
        {"name": "DuckDuckGo", "url": "https://duckduckgo.com", "ats_slug": "duckduckgo", "ats_type": "Direct"},
        {"name": "SafetyWing", "url": "https://safetywing.com", "ats_slug": "safetywing", "ats_type": "Direct"},
        {"name": "PostHog", "url": "https://posthog.com", "ats_slug": "posthog", "ats_type": "Ashby"},
        {"name": "Zapier", "url": "https://zapier.com", "ats_slug": "zapier", "ats_type": "Ashby"},
        {"name": "Customer.io", "url": "https://customer.io", "ats_slug": "customerio", "ats_type": "Greenhouse"},
        {"name": "Webflow", "url": "https://webflow.com", "ats_slug": "webflow", "ats_type": "Greenhouse"},
        {"name": "Netlify", "url": "https://netlify.com", "ats_slug": "netlify", "ats_type": "Greenhouse"},
        {"name": "Close", "url": "https://close.com", "ats_slug": "close", "ats_type": "Ashby"},
        {"name": "Kit", "url": "https://kit.com", "ats_slug": "kit", "ats_type": "Ashby"},
        {"name": "Buffer", "url": "https://buffer.com", "ats_slug": "buffer", "ats_type": "Direct"},
        {"name": "Modern Treasury", "url": "https://moderntreasury.com", "ats_slug": "moderntreasury", "ats_type": "Ashby"},
        {"name": "GitBook", "url": "https://gitbook.com", "ats_slug": "gitbook", "ats_type": "Ashby"},
        {"name": "Ghost", "url": "https://ghost.org", "ats_slug": "ghost", "ats_type": "Ashby"},
        {"name": "Contra", "url": "https://contra.com", "ats_slug": "contra", "ats_type": "Ashby"},
        {"name": "ConsenSys", "url": "https://consensys.io", "ats_slug": "consensys", "ats_type": "Greenhouse"},
        {"name": "Mattermost", "url": "https://mattermost.com", "ats_slug": "mattermost", "ats_type": "Greenhouse"},
        {"name": "Atlassian", "url": "https://atlassian.com", "ats_slug": "atlassian", "ats_type": "Direct"},
        {"name": "Postman", "url": "https://postman.com", "ats_slug": "postman", "ats_type": "Direct"},
        {"name": "Kinsta", "url": "https://kinsta.com", "ats_slug": "kinsta", "ats_type": "Direct"},
        {"name": "Recharge Payments", "url": "https://rechargepayments.com", "ats_slug": "recharge", "ats_type": "Direct"},
        {"name": "Basecamp", "url": "https://37signals.com", "ats_slug": "37signals", "ats_type": "Direct"},
        {"name": "Deel", "url": "https://deel.com", "ats_slug": "deel", "ats_type": "Ashby"},
        {"name": "Remote.com", "url": "https://remote.com", "ats_slug": "remote", "ats_type": "Greenhouse"},
        {"name": "Affirm", "url": "https://affirm.com", "ats_slug": "affirm", "ats_type": "Greenhouse"}
    ]

    for s in seed_companies:
        all_companies[s["name"].lower()] = s

    # Parse open-source markdown sources
    for src in SOURCES:
        try:
            r = requests.get(src, headers=headers, timeout=10)
            if r.status_code == 200:
                matches = re.findall(r'\[([^\]]+)\]\((https?://[^)]+)\)', r.text)
                for name, url in matches:
                    name_clean = name.strip()
                    name_lower = name_clean.lower()
                    # Filter out non-company markdown links
                    if any(skip in name_lower for skip in ['tips', 'guide', 'blog', 'article', 'book', 'talk', 'video', 'glassdoor', 'jobs', 'careers', 'visit', 'list', 'consult']):
                        continue
                    if len(name_clean) > 30 or len(name_clean) < 2:
                        continue
                    if name_lower not in all_companies:
                        slug = re.sub(r'[^a-z0-9]', '', name_lower)
                        all_companies[name_lower] = {
                            "name": name_clean,
                            "url": url,
                            "ats_slug": slug,
                            "ats_type": "Unknown"
                        }
        except Exception as e:
            print(f"Error parsing {src}: {e}")

    output_file = DATA_DIR / "global_remote_companies_universe.json"
    with open(output_file, "w") as f:
        json.dump(list(all_companies.values()), f, indent=2)

    print(f"Successfully indexed {len(all_companies)} global remote companies into {output_file}!")

if __name__ == "__main__":
    build_remote_company_index()
