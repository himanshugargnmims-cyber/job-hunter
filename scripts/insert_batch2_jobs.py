#!/usr/bin/env python3
"""
insert_batch2_jobs.py - Inserts the 15 newly discovered tier-1 roles across
Bengaluru, Hyderabad, and Remote India into jobs.db.
"""

import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"

BATCH2_JOBS = [
    {
        'company': 'Databricks',
        'title': 'Account Executive',
        'location': 'Bengaluru, India',
        'url': 'https://job-boards.greenhouse.io/databricks/jobs/6918763002',
        'board_type': 'Direct - Greenhouse',
        'description': 'Account Executive enterprise software sales, data intelligence platform, commercial deal structuring, customer acquisition, ARR expansion.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 70.5,
        'fit_rationale': 'Commercial enterprise SaaS sales and deal structuring for data cloud platforms.'
    },
    {
        'company': 'InMobi',
        'title': 'Account Manager - Microsoft Advertising',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/inmobi/jobs/7959734',
        'board_type': 'Direct - Greenhouse',
        'description': 'Account Manager Microsoft Advertising adtech commercial partnerships, revenue growth, client strategy, campaign performance.',
        'matched_resume': 'V5_Customer_Success.pdf',
        'fit_score': 63.5,
        'fit_rationale': 'Client relationship management, expansion, and commercial partner retention.'
    },
    {
        'company': 'Glance',
        'title': 'Lead - Business Finance',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/glance/jobs/7956010',
        'board_type': 'Direct - Greenhouse',
        'description': 'Lead Business Finance commercial finance, P&L management, business operations, forecasting, financial modeling, cross-functional strategic decisioning.',
        'matched_resume': 'V3_Strategy_Ops_ChiefOfStaff.pdf',
        'fit_score': 70.5,
        'fit_rationale': 'P&L management, business operations, and financial operating cadence in mobile consumer tech.'
    },
    {
        'company': 'Mixpanel',
        'title': 'Senior Account Executive, India',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://job-boards.greenhouse.io/mixpanel/jobs/8078652',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Account Executive product analytics B2B SaaS commercial sales, deal closing, pipeline generation, market expansion.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 67.0,
        'fit_rationale': 'Product analytics SaaS commercial expansion and enterprise deal closing in India.'
    },
    {
        'company': 'New Relic',
        'title': 'Senior Account Executive - Enterprise Sales',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/newrelic/jobs/8094628',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Account Executive enterprise observability platform sales, GTM execution, revenue growth, customer acquisition.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 67.0,
        'fit_rationale': 'Enterprise observability software sales and commercial revenue execution.'
    },
    {
        'company': 'Pure Storage',
        'title': 'Senior Program Manager, Strategic Initiatives',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/purestorage/jobs/8172901',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Program Manager Strategic Initiatives startups and ecosystem, PMO cadence, cross-functional delivery, business governance.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 98.0,
        'fit_rationale': 'Exceptional fit for strategic program leadership and startup ecosystem governance.'
    },
    {
        'company': 'Pure Storage',
        'title': 'Senior Technical Program Manager',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/purestorage/jobs/8185498',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Technical Program Manager TPM enterprise infrastructure delivery, roadmap execution, technical dependency management, agile delivery.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 98.0,
        'fit_rationale': 'Direct match for technical program leadership and enterprise infrastructure delivery.'
    },
    {
        'company': 'Elastic',
        'title': 'Partner Sales Specialist - Hyperscalers & Cloud',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/elastic/jobs/8138062',
        'board_type': 'Direct - Greenhouse',
        'description': 'Partner Sales Specialist cloud marketplace hyperscalers, GTM partnerships, commercial alliance, co-selling, revenue acceleration.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 63.5,
        'fit_rationale': 'Hyperscaler cloud marketplace alliances and co-selling commercial strategy.'
    },
    {
        'company': 'Elastic',
        'title': 'Coordinator, Marketing Operations',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/elastic/jobs/8161139',
        'board_type': 'Direct - Greenhouse',
        'description': 'Marketing Operations Coordinator RevOps lead lifecycle, campaign operations, CRM marketing automation, operational excellence.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 82.0,
        'fit_rationale': 'Campaign operations, funnel execution, and process design in enterprise open source software.'
    },
    {
        'company': 'Cloudflare',
        'title': 'Senior Manager, Customer Engineering, India',
        'location': 'Remote India',
        'url': 'https://job-boards.greenhouse.io/cloudflare/jobs/8020043',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Manager Customer Engineering solutions architecture, customer success operations, technical leadership, client onboarding, retention.',
        'matched_resume': 'V5_Customer_Success.pdf',
        'fit_score': 70.5,
        'fit_rationale': 'Customer engineering operations and enterprise client technical retention.'
    },
    {
        'company': 'Workato',
        'title': 'Customer Centric Engineer (US Market)',
        'location': 'Hyderabad, India',
        'url': 'https://job-boards.greenhouse.io/workato/jobs/8570123002',
        'board_type': 'Direct - Greenhouse',
        'description': 'Customer Centric Engineer enterprise integration platform, customer operations, solutions delivery, technical account health.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 67.0,
        'fit_rationale': 'Customer operations excellence and enterprise integration delivery in Hyderabad hub.'
    },
    {
        'company': 'ZoomInfo',
        'title': 'GTM Technical Solutions Analyst II',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://job-boards.greenhouse.io/zoominfo/jobs/8834178002',
        'board_type': 'Direct - Greenhouse',
        'description': 'GTM Technical Solutions Analyst RevOps, revenue data architecture, sales enablement, integrations, business operations.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 92.0,
        'fit_rationale': 'Pristine alignment with RevOps, commercial architecture, and sales enablement.'
    },
    {
        'company': 'Writer',
        'title': 'Strategic Account Executive',
        'location': 'India / Remote',
        'url': 'https://jobs.ashbyhq.com/writer/faa65b0b-6b4a-4c5b-9501-4ebdcfe61543/application',
        'board_type': 'Direct - Ashby',
        'description': 'Strategic Account Executive enterprise generative AI platform sales, commercial deal negotiation, ARR growth, strategic accounts.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 63.5,
        'fit_rationale': 'Generative AI enterprise commercial expansion and deal negotiation.'
    },
    {
        'company': 'Kong',
        'title': 'Enterprise Account Executive',
        'location': 'Bangalore, India',
        'url': 'https://jobs.ashbyhq.com/kong/eb2774d0-e928-44f1-9d96-96a616b48526/application',
        'board_type': 'Direct - Ashby',
        'description': 'Enterprise Account Executive API platform cloud enterprise sales, commercial territory management, revenue expansion.',
        'matched_resume': 'V5_Customer_Success.pdf',
        'fit_score': 63.5,
        'fit_rationale': 'Enterprise API platform commercial sales and account growth.'
    },
    {
        'company': 'Cursor',
        'title': 'Strategic Enterprise Account Executive - India',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://jobs.ashbyhq.com/cursor/919b3d00-fef8-4038-8b71-165fae5d54e7/application',
        'board_type': 'Direct - Ashby',
        'description': 'Strategic Enterprise Account Executive AI developer tools commercial deals, enterprise customer acquisition, ARR acceleration.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 67.0,
        'fit_rationale': 'AI developer tools commercial enterprise accounts and revenue scaling.'
    }
]

def insert_batch2():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT max(id) FROM jobs")
    max_id = c.fetchone()[0] or 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0

    for j in BATCH2_JOBS:
        c.execute("SELECT id FROM jobs WHERE url = ?", (j['url'],))
        row = c.fetchone()
        if row:
            print(f"Skipping existing: {j['company']} - {j['title']} (ID {row[0]})")
            continue
        max_id += 1
        c.execute("""
            INSERT INTO jobs (
                id, company, title, location, url, board_type, description,
                matched_resume, fit_score, fit_rationale, status, date_scraped, date_updated, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Found', ?, ?, ?)
        """, (
            max_id,
            j['company'],
            j['title'],
            j['location'],
            j['url'],
            j['board_type'],
            j['description'],
            j['matched_resume'],
            j['fit_score'],
            j['fit_rationale'],
            now,
            now,
            'Batch 2 - Expansion scan'
        ))
        inserted += 1
        print(f"Inserted #{max_id}: [{j['company']}] {j['title']} ({j['location']})")

    conn.commit()
    conn.close()
    print(f"\nInserted {inserted} jobs into jobs.db!")

if __name__ == "__main__":
    insert_batch2()
