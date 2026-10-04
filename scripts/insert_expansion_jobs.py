#!/usr/bin/env python3
"""
insert_expansion_jobs.py - Inserts the 20 newly curated direct ATS roles across
Bengaluru, Gurugram, and Remote India into jobs.db with precise resume matches and fit scores.
"""

import sqlite3
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"

NEW_JOBS = [
    {
        'company': 'Celonis',
        'title': 'Chief of Staff - Engineering',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/celonis/jobs/7559351003',
        'board_type': 'Direct - Greenhouse',
        'description': 'Chief of Staff Engineering strategy, operations, executive alignment, operating cadence, organizational efficiency, cross-functional delivery.',
        'matched_resume': 'V3_Strategy_Ops_ChiefOfStaff.pdf',
        'fit_score': 95.5,
        'fit_rationale': 'Exceptional fit for Chief of Staff charter; aligns with executive alignment, operating cadence, and cross-functional leadership.'
    },
    {
        'company': 'Quince',
        'title': 'Principal Technical Program Manager',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://job-boards.greenhouse.io/quince/jobs/5435890008',
        'board_type': 'Direct - Greenhouse',
        'description': 'Principal Technical Program Manager TPM cross-functional engineering delivery, roadmap execution, governance, milestones, operating rhythm.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 98.0,
        'fit_rationale': 'Direct match for Program Management charter (V4) with deep technical roadmap execution and cross-functional governance.'
    },
    {
        'company': 'Fivetran',
        'title': 'Staff Technical Program Manager',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://job-boards.greenhouse.io/fivetran/jobs/7868539003',
        'board_type': 'Direct - Greenhouse',
        'description': 'Staff Technical Program Manager TPM leading cross-functional engineering initiatives, data pipeline operations, milestone tracking, PMO cadence.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 98.0,
        'fit_rationale': 'Direct match for Staff TPM charter with enterprise data integration and technical delivery.'
    },
    {
        'company': 'Flexport',
        'title': 'Assistant Manager, Air Operations (Gurugram)',
        'location': 'Gurugram, Haryana, India',
        'url': 'https://job-boards.greenhouse.io/flexport/jobs/7953626',
        'board_type': 'Direct - Greenhouse',
        'description': 'Assistant Manager Air Operations Gurugram logistics operations excellence, supply chain execution, service delivery, operational consistency.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 85.5,
        'fit_rationale': 'Strong alignment with Operations Excellence (V6) and process optimization in Gurugram tech hub.'
    },
    {
        'company': 'Navan',
        'title': 'Finance Operations Specialist',
        'location': 'Gurugram, Haryana, India',
        'url': 'https://job-boards.greenhouse.io/tripactions/jobs/8194356',
        'board_type': 'Direct - Greenhouse',
        'description': 'Finance Operations Specialist Gurugram commercial operations, FinTech billing, reconciliation, operational efficiency, financial process design.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 85.5,
        'fit_rationale': 'Aligns with FinTech operations, reconciliation, and commercial process design in Gurugram.'
    },
    {
        'company': 'Navan',
        'title': 'Sr. Partner Operations Analyst',
        'location': 'Delhi NCR, India',
        'url': 'https://job-boards.greenhouse.io/tripactions/jobs/7774094',
        'board_type': 'Direct - Greenhouse',
        'description': 'Senior Partner Operations Analyst partnerships operations, commercial enablement, partner ecosystem, vendor ops, cross-functional execution.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 82.0,
        'fit_rationale': 'Targeted partner ecosystem operations and commercial execution in Delhi NCR.'
    },
    {
        'company': 'Airbnb',
        'title': 'Supervisor - Investigations & Operations',
        'location': 'Gurugram, Haryana, India',
        'url': 'https://job-boards.greenhouse.io/airbnb/jobs/8245193',
        'board_type': 'Direct - Greenhouse',
        'description': 'Supervisor Investigations & Operations Gurugram central operations excellence, escalation management, team leadership, SLA delivery.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 85.5,
        'fit_rationale': 'Central operations, escalation workflows, and high-stakes service delivery in Gurugram.'
    },
    {
        'company': 'Ethos Life',
        'title': 'Staff Technical Program Manager',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/ethoslife/jobs/8294196002',
        'board_type': 'Direct - Greenhouse',
        'description': 'Staff Technical Program Manager TPM cross-functional program delivery, engineering roadmap, FinTech InsurTech systems.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 98.0,
        'fit_rationale': 'High-impact technical program leadership in modern FinTech/InsurTech systems.'
    },
    {
        'company': 'Ethos Life',
        'title': 'Sales Strategy & Operations Manager',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/ethoslife/jobs/8641258002',
        'board_type': 'Direct - Greenhouse',
        'description': 'Sales Strategy & Operations Manager RevOps, sales operations, forecasting, pipeline analytics, quota planning, commercial strategy.',
        'matched_resume': 'V3_Strategy_Ops_ChiefOfStaff.pdf',
        'fit_score': 88.5,
        'fit_rationale': 'Revenue operations and commercial strategy driving sales productivity and pipeline forecasting.'
    },
    {
        'company': 'Payoneer',
        'title': 'Commercial Program Manager',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/payoneer/jobs/8119225',
        'board_type': 'Direct - Greenhouse',
        'description': 'Commercial Program Manager GTM go-to-market strategy, revenue operations, FinTech payments commercialization, cross-functional execution.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 88.5,
        'fit_rationale': 'Cross-functional commercial launch management and FinTech payments expansion.'
    },
    {
        'company': 'Payoneer',
        'title': 'Customer Lifecycle Program Manager',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/payoneer/jobs/7935957',
        'board_type': 'Direct - Greenhouse',
        'description': 'Customer Lifecycle Program Manager customer success, retention, onboarding, client lifecycle management, time-to-value.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 88.5,
        'fit_rationale': 'Programmatic customer lifecycle execution and retention optimization in global FinTech.'
    },
    {
        'company': 'Datadog',
        'title': 'Commercial Account Executive',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/datadog/jobs/6512321',
        'board_type': 'Direct - Greenhouse',
        'description': 'Commercial Account Executive cloud enterprise sales, B2B SaaS GTM, revenue acquisition, pipeline generation.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 82.0,
        'fit_rationale': 'Commercial SaaS revenue acquisition and enterprise deal structuring.'
    },
    {
        'company': 'Toast',
        'title': 'Risk Analyst - Strategy & Capabilities',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/toast/jobs/8078687',
        'board_type': 'Direct - Greenhouse',
        'description': 'Risk Analyst Strategy & Capabilities FinTech risk strategy, business operations, payments data analytics, process improvement.',
        'matched_resume': 'V3_Strategy_Ops_ChiefOfStaff.pdf',
        'fit_score': 78.5,
        'fit_rationale': 'FinTech risk strategy and operational decisioning in restaurant payment systems.'
    },
    {
        'company': 'Toast',
        'title': 'Credit Risk Senior Analyst - Loss Forecasting',
        'location': 'Bangalore, India',
        'url': 'https://job-boards.greenhouse.io/toast/jobs/7519051',
        'board_type': 'Direct - Greenhouse',
        'description': 'Credit Risk Senior Analyst Loss Forecasting FinTech lending forecasting, risk modeling, credit strategy, portfolio performance.',
        'matched_resume': 'V2_RevOps.pdf',
        'fit_score': 78.5,
        'fit_rationale': 'Predictive modeling, financial loss forecasting, and commercial portfolio risk management.'
    },
    {
        'company': 'Apollo.io',
        'title': 'Account Executive / Account Manager, MM (India)',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://job-boards.greenhouse.io/apolloio/jobs/6205992004',
        'board_type': 'Direct - Greenhouse',
        'description': 'Account Manager MM India B2B SaaS commercial sales, deal structuring, customer acquisition, ARR growth.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 74.0,
        'fit_rationale': 'Mid-market client relationship management and SaaS commercial growth.'
    },
    {
        'company': 'Cursor',
        'title': 'Manager, Channels & Partnerships - India',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://jobs.ashbyhq.com/cursor/38036e7f-d699-4f45-b569-c8a3a5d4c3db/application',
        'board_type': 'Direct - Ashby',
        'description': 'Manager Channels & Partnerships India GTM partnership strategy, ecosystem expansion, developer platforms, commercial deals.',
        'matched_resume': 'V1_GTM_Revenue_Strategy.pdf',
        'fit_score': 85.0,
        'fit_rationale': 'High-impact AI code editor developer ecosystem partnerships and commercial expansion.'
    },
    {
        'company': 'Kong',
        'title': 'Senior Marketing Operations Analyst - India',
        'location': 'Bangalore, India',
        'url': 'https://jobs.ashbyhq.com/kong/a9ac1959-5046-401e-a236-53622069f40c/application',
        'board_type': 'Direct - Ashby',
        'description': 'Senior Marketing Operations Analyst RevOps marketing operations, funnel analytics, campaign execution, CRM marketing automation.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 78.5,
        'fit_rationale': 'Revenue operations analytics and API cloud infrastructure marketing enablement.'
    },
    {
        'company': 'G2',
        'title': 'Campaign Operations Specialist',
        'location': 'Bengaluru, Karnataka, India',
        'url': 'https://jobs.ashbyhq.com/g2/94b5b645-3b97-4109-84d7-a97803c4ab84/application',
        'board_type': 'Direct - Ashby',
        'description': 'Campaign Operations Specialist Bengaluru advertising operations, customer campaign delivery, process excellence, SLA tracking.',
        'matched_resume': 'V6_Operations_Excellence.pdf',
        'fit_score': 78.5,
        'fit_rationale': 'Operations excellence and enterprise campaign execution at G2 Bengaluru.'
    },
    {
        'company': 'Supabase',
        'title': 'Product Manager - Security & Trust',
        'location': 'Global Remote / India',
        'url': 'https://jobs.ashbyhq.com/supabase/b8010a28-109c-46a9-b8b7-c7f9b24077fa/application',
        'board_type': 'Direct - Ashby',
        'description': 'Product Manager Security & Trust open-source developer platforms, enterprise security, compliance, product roadmap.',
        'matched_resume': 'V3_Strategy_Ops_ChiefOfStaff.pdf',
        'fit_score': 75.0,
        'fit_rationale': 'Strategic product leadership and governance in open-source cloud infrastructure.'
    },
    {
        'company': 'Supabase',
        'title': 'Product Lead, Infrastructure',
        'location': 'Global Remote / India',
        'url': 'https://jobs.ashbyhq.com/supabase/47bcfdb8-b954-423e-8a9e-85256434575c/application',
        'board_type': 'Direct - Ashby',
        'description': 'Product Lead Infrastructure distributed systems, cloud platform scalability, technical program roadmap, engineering alignment.',
        'matched_resume': 'V4_Program_Management.pdf',
        'fit_score': 78.0,
        'fit_rationale': 'Technical program roadmap and infrastructure product leadership for developer cloud.'
    }
]

def insert_jobs():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Check max ID
    c.execute("SELECT max(id) FROM jobs")
    max_id = c.fetchone()[0] or 0
    
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    inserted = 0
    for j in NEW_JOBS:
        # Check if URL already exists
        c.execute("SELECT id, status FROM jobs WHERE url = ?", (j['url'],))
        row = c.fetchone()
        if row:
            print(f"Skipping already existing URL: {j['company']} - {j['title']} (ID {row[0]})")
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
            'Discovered via verified ATS expansion scan'
        ))
        inserted += 1
        print(f"Inserted Job #{max_id}: [{j['company']}] {j['title']} ({j['location']}) -> {j['matched_resume']}")
    
    conn.commit()
    conn.close()
    print(f"\nSuccessfully inserted {inserted} new roles into jobs.db!")

if __name__ == "__main__":
    insert_jobs()
