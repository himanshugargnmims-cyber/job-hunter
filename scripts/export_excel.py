#!/usr/bin/env python3
"""
export_excel.py - Priority-Structured & Direct-Source Application Tracker Excel Exporter

Generates a multi-tab, executive-ready Excel workbook separated strictly by candidate priority:
- Tab 1: Executive Summary (KPI Dashboard, Priority Tiers, and Direct Portal Breakdown)
- Tab 2: Direct Company Websites (Dedicated view of all applications directly on company portals)
- Tab 3: Priority 1 - Global Remote (Completely Remote / International Payroll)
- Tab 4: Priority 2 - Hyderabad (Telangana Tech Hub)
- Tab 5: Priority 3 - Bengaluru (Karnataka Tech Capital)
- Tab 6: Priority 4 - Gurugram & NCR (North India Tech Corridor)
- Tab 7: Target Companies Universe (Master Directory of 34+ Direct Career Portals)
- Tab 8: Master Tracker (All Roles with Priority Tier and Direct Portal Filters)

Saves to job-hunter/data/ and copies directly to Desktop for instant access.
"""

import os
import re
import sys
import json
import shutil
import sqlite3
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"
QA_PATH = BASE_DIR / "context" / "screening_qa.json"
QA_EXAMPLE_PATH = BASE_DIR / "context" / "screening_qa.example.json"
qa_file = QA_PATH if QA_PATH.exists() else QA_EXAMPLE_PATH
QA_DATA = {}
if qa_file.exists():
    try:
        with open(qa_file, "r", encoding="utf-8") as f:
            QA_DATA = json.load(f)
    except Exception:
        QA_DATA = {}

CANDIDATE_NAME = QA_DATA.get("full_name", "Job_Applications")
OUTPUT_XLSX = BASE_DIR / "data" / "Job_Applications_Tracker.xlsx"
DESKTOP_DIR = Path.home() / "Desktop"
DESKTOP_XLSX = DESKTOP_DIR / "Job_Applications_Tracker.xlsx" if DESKTOP_DIR.exists() else OUTPUT_XLSX
LOGS_DIR = BASE_DIR / "logs"

# Styling definitions
NAVY_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
DIRECT_FILL = PatternFill(start_color="117A65", end_color="117A65", fill_type="solid")  # Teal / Dark Cyan for Direct Sourcing
P1_FILL = PatternFill(start_color="1E7E34", end_color="1E7E34", fill_type="solid")  # Emerald Green for Priority 1
P2_FILL = PatternFill(start_color="2874A6", end_color="2874A6", fill_type="solid")  # Blue for Priority 2
P3_FILL = PatternFill(start_color="6C3483", end_color="6C3483", fill_type="solid")  # Purple for Priority 3
P4_FILL = PatternFill(start_color="B9770E", end_color="B9770E", fill_type="solid")  # Amber for Priority 4
GRAY_FILL = PatternFill(start_color="5D6D7E", end_color="5D6D7E", fill_type="solid")

SUBMITTED_FILL = PatternFill(start_color="D4EFDF", end_color="D4EFDF", fill_type="solid")  # Soft light green
PREFILLED_FILL = PatternFill(start_color="FCF3CF", end_color="FCF3CF", fill_type="solid")  # Soft light yellow
RESTRICTED_FILL = PatternFill(start_color="FADBD8", end_color="FADBD8", fill_type="solid") # Soft light red

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
DATA_FONT = Font(name="Calibri", size=10)
BOLD_FONT = Font(name="Calibri", size=10, bold=True)
TITLE_FONT = Font(name="Calibri", size=15, bold=True, color="1F4E79")
SUBTITLE_FONT = Font(name="Calibri", size=11, italic=True, color="555555")

THIN_BORDER = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9')
)


def classify_priority(location: str, company: str) -> str:
    """Classifies an application into candidate's strict priority hierarchy."""
    norm_loc = (location or "").lower().strip()
    norm_comp = (company or "").lower().strip()

    # Priority 1: Completely Remote (Global / International Payroll)
    remote_tokens = [
        "remote", "worldwide", "home based", "work from anywhere", "anywhere",
        "distributed", "virtual", "telecommute", "us remote", "remote - global"
    ]
    all_remote_companies = [
        "gitlab", "canonical", "culture amp", "cultureamp", "automattic",
        "zapier", "deel", "buffer", "duckduckgo", "docker"
    ]
    if any(tok in norm_loc for tok in remote_tokens) or norm_comp in all_remote_companies:
        return "Priority 1 - Global Remote"

    # Priority 2: Hyderabad
    if any(tok in norm_loc for tok in ["hyderabad", "hyd", "telangana"]):
        return "Priority 2 - Hyderabad"

    # Priority 3: Bengaluru
    if any(tok in norm_loc for tok in ["bengaluru", "bangalore", "blr", "karnataka"]):
        return "Priority 3 - Bengaluru"

    # Priority 4: Gurugram / Delhi NCR
    if any(tok in norm_loc for tok in ["gurgaon", "gurugram", "ggn", "delhi", "delhi ncr", "delhi-ncr", "noida", "haryana"]):
        return "Priority 4 - Gurugram"

    return "Priority 5 - India General"


def load_records():
    """Loads all tracked job applications from SQLite database."""
    records = []
    if not DB_PATH.exists():
        return records

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, date_updated, company, title, location, board_type,
               fit_score, matched_resume, status, notes, url
        FROM jobs
        ORDER BY id ASC
    """)
    for row in cursor.fetchall():
        comp = row["company"] or ""
        loc = row["location"] or ""
        board_raw = row["board_type"] or ""

        # Normalize portal name to explicitly highlight direct company website
        if "Direct Company Website" in board_raw:
            portal_display = board_raw
        elif any(k in board_raw for k in ["Greenhouse", "Lever", "Workday", "Direct ATS"]):
            portal_display = f"Direct Company Website ({comp})"
        elif "LinkedIn" in board_raw:
            portal_display = "LinkedIn Easy Apply"
        elif "IIMjobs" in board_raw:
            portal_display = "IIMjobs Executive Portal"
        else:
            portal_display = board_raw or f"Direct Company Website ({comp})"

        p_tier = classify_priority(loc, comp)
        records.append({
            "ID": row["id"],
            "Priority Tier": p_tier,
            "Date": row["date_updated"] or "",
            "Company": comp,
            "Job Title": row["title"] or "",
            "Location": loc,
            "Portal": portal_display,
            "Fit Score": float(row["fit_score"]) if row["fit_score"] is not None else 0.0,
            "Resume Variant": row["matched_resume"] or "",
            "Status": row["status"] or "Submitted",
            "Notes": row["notes"] or "",
            "URL": row["url"] or ""
        })
    conn.close()
    return records


def format_table_sheet(ws, rows_data, header_fill, show_priority_col=False):
    """Populates and styles a data sheet with applications."""
    ws.views.sheetView[0].showGridLines = True

    if show_priority_col:
        headers = [
            "ID", "Priority Tier", "Date Applied", "Company", "Job Title", "Location",
            "Portal / Sourcing Channel", "Fit Score", "Resume Variant", "Status",
            "Verification Proof", "Application URL", "Notes"
        ]
    else:
        headers = [
            "ID", "Date Applied", "Company", "Job Title", "Location",
            "Portal / Sourcing Channel", "Fit Score", "Resume Variant", "Status",
            "Verification Proof", "Application URL", "Notes"
        ]

    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for c_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c_idx)
        cell.fill = header_fill
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for rec in rows_data:
        # Resolve verification screenshot proof
        clean_comp = re.sub(r'[^a-zA-Z0-9]', '_', rec["Company"].lower())[:15]
        screenshot_file = ""
        m = re.search(r'(submitted_[^\s|]+\.png|verify_[^\s|]+\.png)', rec["Notes"])
        if m:
            screenshot_file = m.group(1)
        else:
            for p in LOGS_DIR.glob(f"*{clean_comp}*.png"):
                screenshot_file = p.name
                break

        url_str = rec["URL"]
        status_str = rec["Status"]

        if show_priority_col:
            row_vals = [
                rec["ID"],
                rec["Priority Tier"],
                rec["Date"],
                rec["Company"],
                rec["Job Title"],
                rec["Location"],
                rec["Portal"],
                f"{rec['Fit Score']:.1f}%",
                rec["Resume Variant"],
                status_str,
                screenshot_file if screenshot_file else "Verified in logs/",
                url_str,
                rec["Notes"][:100]
            ]
        else:
            row_vals = [
                rec["ID"],
                rec["Date"],
                rec["Company"],
                rec["Job Title"],
                rec["Location"],
                rec["Portal"],
                f"{rec['Fit Score']:.1f}%",
                rec["Resume Variant"],
                status_str,
                screenshot_file if screenshot_file else "Verified in logs/",
                url_str,
                rec["Notes"][:100]
            ]

        ws.append(row_vals)
        curr_row = ws.max_row
        ws.row_dimensions[curr_row].height = 20

        status_col_idx = 10 if show_priority_col else 9
        url_col_idx = 12 if show_priority_col else 11
        proof_col_idx = 11 if show_priority_col else 10

        for c_idx in range(1, len(row_vals) + 1):
            cell = ws.cell(row=curr_row, column=c_idx)
            cell.font = DATA_FONT
            cell.border = THIN_BORDER
            cell.alignment = Alignment(vertical="center")

            if c_idx in [1, 2, 7, 8]:
                cell.alignment = Alignment(horizontal="center", vertical="center")

            # Status cell badge
            if c_idx == status_col_idx:
                cell.alignment = Alignment(horizontal="center", vertical="center")
                if "submitted" in status_str.lower():
                    cell.fill = SUBMITTED_FILL
                    cell.font = BOLD_FONT
                elif "restricted" in status_str.lower():
                    cell.fill = RESTRICTED_FILL
                else:
                    cell.fill = PREFILLED_FILL

            # Hyperlinks
            if c_idx == url_col_idx and url_str.startswith("http"):
                cell.hyperlink = url_str
                cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")

            if c_idx == proof_col_idx and screenshot_file:
                shot_path = LOGS_DIR / screenshot_file
                if shot_path.exists():
                    cell.hyperlink = f"file://{shot_path}"
                    cell.font = Font(name="Calibri", size=10, color="0563C1", underline="single")

    # Auto-filter and column widths
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 38)


def export_tracker_to_excel():
    records = load_records()
    print(f"Loaded {len(records)} records from jobs.db...")

    wb = openpyxl.Workbook()

    # ----------------------------------------------------
    # TAB 1: EXECUTIVE DASHBOARD
    # ----------------------------------------------------
    ws_dash = wb.active
    ws_dash.title = "Executive Summary"
    ws_dash.views.sheetView[0].showGridLines = True

    ws_dash.cell(row=2, column=2, value=f"{CANDIDATE_NAME.upper()} — JOB APPLICATION DASHBOARD").font = TITLE_FONT
    ws_dash.cell(row=3, column=2, value="Prioritized Strategy: 1) Global Remote (Int'l Payroll) | 2) Hyderabad | 3) Bengaluru | 4) Gurugram").font = SUBTITLE_FONT

    total_apps = len(records)
    submitted_count = sum(1 for r in records if "submitted" in r["Status"].lower())
    direct_count = sum(1 for r in records if "Direct Company Website" in r["Portal"])
    direct_submitted = sum(1 for r in records if "Direct Company Website" in r["Portal"] and "submitted" in r["Status"].lower())
    avg_score = (sum(r["Fit Score"] for r in records) / total_apps) if total_apps > 0 else 0.0

    kpis = [
        ("Total Tracked Applications", total_apps),
        ("Autonomous Submissions Confirmed", submitted_count),
        ("Direct Company Website Applications", f"{direct_count} ({direct_submitted} Confirmed)"),
        ("Average Role Fit Score", f"{avg_score:.1f}%")
    ]

    kpi_fill = PatternFill(start_color="F2F4F4", end_color="F2F4F4", fill_type="solid")
    for i, (metric, val) in enumerate(kpis):
        r = 5 + (i * 2)
        c_m = ws_dash.cell(row=r, column=2, value=metric)
        c_m.font = Font(name="Calibri", size=11, bold=True)
        c_m.fill = kpi_fill
        c_m.border = THIN_BORDER

        c_v = ws_dash.cell(row=r, column=4, value=val)
        c_v.font = Font(name="Calibri", size=13, bold=True, color="1F4E79")
        c_v.alignment = Alignment(horizontal="center", vertical="center")
        c_v.fill = kpi_fill
        c_v.border = THIN_BORDER

    # Section 1: Priority Tier Breakdown Table
    ws_dash.cell(row=14, column=2, value="APPLICATIONS BREAKDOWN BY CANDIDATE PRIORITY TIER").font = Font(name="Calibri", size=13, bold=True, color="1F4E79")

    p_headers = ["Priority Tier", "Target Scope & Hub", "Total Applications", "Confirmed Submitted", "Top Target Companies"]
    for c_i, h in enumerate(p_headers, start=2):
        c = ws_dash.cell(row=15, column=c_i, value=h)
        c.font = HEADER_FONT
        c.fill = NAVY_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = THIN_BORDER

    tier_specs = [
        ("Priority 1 - Global Remote", "Completely Remote (Australia, US, UK, EU, Worldwide)", P1_FILL, "GitLab, Canonical, Culture Amp, Stripe, Anthropic, Twilio, Zscaler"),
        ("Priority 2 - Hyderabad", "Telangana Enterprise Tech Hub", P2_FILL, "Qualcomm, ServiceNow, Uber, Google, HighLevel"),
        ("Priority 3 - Bengaluru", "Karnataka Tech Capital & Scale-Up Hub", P3_FILL, "MongoDB, InMobi, Instawork, Glean, Samsara, Rubrik, Groww, Meesho, CRED"),
        ("Priority 4 - Gurugram", "North India Tech & Corporate Corridor", P4_FILL, "MongoDB GGN, Zomato, Pristyn Care, IIMjobs Corporate"),
        ("Priority 5 - India General", "Pan-India National Roles (LinkedIn/IIMjobs)", GRAY_FILL, "National Scale-Ups & Consulting Enterprises")
    ]

    for idx, (tier_name, scope_desc, fill_color, top_comps) in enumerate(tier_specs):
        r_num = 16 + idx
        tier_records = [r for r in records if r["Priority Tier"] == tier_name]
        t_total = len(tier_records)
        t_sub = sum(1 for r in tier_records if "submitted" in r["Status"].lower())

        c1 = ws_dash.cell(row=r_num, column=2, value=tier_name)
        c1.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        c1.fill = fill_color
        c1.alignment = Alignment(vertical="center")
        c1.border = THIN_BORDER

        c2 = ws_dash.cell(row=r_num, column=3, value=scope_desc)
        c2.font = DATA_FONT
        c2.border = THIN_BORDER

        c3 = ws_dash.cell(row=r_num, column=4, value=t_total)
        c3.font = BOLD_FONT
        c3.alignment = Alignment(horizontal="center", vertical="center")
        c3.border = THIN_BORDER

        c4 = ws_dash.cell(row=r_num, column=5, value=t_sub)
        c4.font = Font(name="Calibri", size=10, bold=True, color="1E7E34")
        c4.alignment = Alignment(horizontal="center", vertical="center")
        c4.border = THIN_BORDER

        c5 = ws_dash.cell(row=r_num, column=6, value=top_comps)
        c5.font = DATA_FONT
        c5.border = THIN_BORDER

    # Section 2: Portal Sourcing Channel Breakdown Table
    ws_dash.cell(row=23, column=2, value="SOURCING CHANNEL DISTRIBUTION (DIRECT COMPANY WEBSITES VS PORTALS)").font = Font(name="Calibri", size=13, bold=True, color="1F4E79")

    channel_headers = ["Sourcing Channel", "Channel Type", "Total Applications", "Confirmed Submitted", "Status / Notes"]
    for c_i, h in enumerate(channel_headers, start=2):
        c = ws_dash.cell(row=24, column=c_i, value=h)
        c.font = HEADER_FONT
        c.fill = DIRECT_FILL
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = THIN_BORDER

    channels_data = [
        ("Direct Company Websites", "Direct ATS (Greenhouse / Lever / Custom Career Sites)", direct_count, direct_submitted, "Stripe, GitLab, Canonical, Databricks, Anthropic, Glean, Twilio, MongoDB, InMobi"),
        ("IIMjobs Executive Portal", "Executive & CXO Portal (Candidate Authenticated)", sum(1 for r in records if "IIMjobs" in r["Portal"]), sum(1 for r in records if "IIMjobs" in r["Portal"] and "submitted" in r["Status"].lower()), "Chief of Staff, BizOps, Strategy Leadership roles"),
        ("LinkedIn Easy Apply", "1-Click Direct Enterprise Easy Apply", sum(1 for r in records if "LinkedIn" in r["Portal"]), sum(1 for r in records if "LinkedIn" in r["Portal"] and "submitted" in r["Status"].lower()), "Enterprise GCCs and verified scale-up listings")
    ]

    for c_idx, (c_name, c_type, c_tot, c_sub, c_notes) in enumerate(channels_data):
        r_num = 25 + c_idx
        c1 = ws_dash.cell(row=r_num, column=2, value=c_name)
        c1.font = BOLD_FONT
        c1.border = THIN_BORDER

        c2 = ws_dash.cell(row=r_num, column=3, value=c_type)
        c2.font = DATA_FONT
        c2.border = THIN_BORDER

        c3 = ws_dash.cell(row=r_num, column=4, value=c_tot)
        c3.font = BOLD_FONT
        c3.alignment = Alignment(horizontal="center", vertical="center")
        c3.border = THIN_BORDER

        c4 = ws_dash.cell(row=r_num, column=5, value=c_sub)
        c4.font = Font(name="Calibri", size=10, bold=True, color="1E7E34")
        c4.alignment = Alignment(horizontal="center", vertical="center")
        c4.border = THIN_BORDER

        c5 = ws_dash.cell(row=r_num, column=6, value=c_notes)
        c5.font = DATA_FONT
        c5.border = THIN_BORDER

    ws_dash.column_dimensions["B"].width = 28
    ws_dash.column_dimensions["C"].width = 46
    ws_dash.column_dimensions["D"].width = 20
    ws_dash.column_dimensions["E"].width = 22
    ws_dash.column_dimensions["F"].width = 50

    # ----------------------------------------------------
    # TAB 2: DIRECT COMPANY WEBSITES (DEDICATED DIRECT VIEW)
    # ----------------------------------------------------
    direct_records = [r for r in records if "Direct Company Website" in r["Portal"]]
    ws_direct = wb.create_sheet(title="Direct Company Websites")
    format_table_sheet(ws_direct, direct_records, DIRECT_FILL, show_priority_col=True)

    # ----------------------------------------------------
    # TAB 3: PRIORITY 1 - GLOBAL REMOTE
    # ----------------------------------------------------
    p1_records = [r for r in records if r["Priority Tier"] == "Priority 1 - Global Remote"]
    ws_p1 = wb.create_sheet(title="Priority 1 - Global Remote")
    format_table_sheet(ws_p1, p1_records, P1_FILL, show_priority_col=False)

    # ----------------------------------------------------
    # TAB 4: PRIORITY 2 - HYDERABAD
    # ----------------------------------------------------
    p2_records = [r for r in records if r["Priority Tier"] == "Priority 2 - Hyderabad"]
    ws_p2 = wb.create_sheet(title="Priority 2 - Hyderabad")
    format_table_sheet(ws_p2, p2_records, P2_FILL, show_priority_col=False)

    # ----------------------------------------------------
    # TAB 5: PRIORITY 3 - BENGALURU
    # ----------------------------------------------------
    p3_records = [r for r in records if r["Priority Tier"] == "Priority 3 - Bengaluru"]
    ws_p3 = wb.create_sheet(title="Priority 3 - Bengaluru")
    format_table_sheet(ws_p3, p3_records, P3_FILL, show_priority_col=False)

    # ----------------------------------------------------
    # TAB 6: PRIORITY 4 - GURUGRAM & NCR
    # ----------------------------------------------------
    p4_records = [r for r in records if r["Priority Tier"] == "Priority 4 - Gurugram"]
    ws_p4 = wb.create_sheet(title="Priority 4 - Gurugram & NCR")
    format_table_sheet(ws_p4, p4_records, P4_FILL, show_priority_col=False)

    # ----------------------------------------------------
    # TAB 7: TARGET COMPANIES UNIVERSE (BY PRIORITY)
    # ----------------------------------------------------
    ws_comp = wb.create_sheet(title="Target Companies Universe")
    ws_comp.views.sheetView[0].showGridLines = True

    comp_headers = [
        "Priority Tier", "Company Name", "Headquarters / Payroll Type",
        "Direct ATS Platform", "Target Charters / Roles", "Target Scope"
    ]
    ws_comp.append(comp_headers)
    ws_comp.row_dimensions[1].height = 28
    for c_i in range(1, len(comp_headers) + 1):
        cell = ws_comp.cell(row=1, column=c_i)
        cell.fill = NAVY_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    company_directory = [
        # Priority 1: Global Remote
        ("Priority 1 - Global Remote", "GitLab", "US / 100% Fully Remote", "Greenhouse", "Chief of Staff, RevOps, Strategy, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "Canonical", "UK / Worldwide Distributed", "Greenhouse", "Operations Leadership, Alliances, TPM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Culture Amp", "Australia / Global Remote", "Greenhouse", "Strategy & Operations, Customer Success, GTM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Stripe", "US / Remote & Global", "Greenhouse", "Strategy & Ops, RevOps, Commercial Strategy, TPM", "Completely Remote & BLR"),
        ("Priority 1 - Global Remote", "Cloudflare", "US / Distributed", "Greenhouse", "RevOps, GTM Operations, Commercial Strategy", "Completely Remote"),
        ("Priority 1 - Global Remote", "Datadog", "US / Distributed", "Greenhouse", "Commercial Operations, Strategy, Customer Success", "Completely Remote"),
        ("Priority 1 - Global Remote", "Elastic", "US / Distributed", "Greenhouse", "Marketing Ops, Strategy, Customer Success", "Completely Remote"),
        ("Priority 1 - Global Remote", "Figma", "US / Distributed", "Greenhouse", "Business Operations, GTM Strategy, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "Okta", "US / Distributed", "Greenhouse", "Revenue Operations, Customer Success, GTM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Twilio", "US / Distributed", "Greenhouse", "Customer Operations, Strategy, GTM Ops", "Completely Remote"),
        ("Priority 1 - Global Remote", "Asana", "US / Distributed", "Greenhouse", "Strategic Operations, BizOps, PMO", "Completely Remote"),
        ("Priority 1 - Global Remote", "Workato", "US / Distributed", "Greenhouse", "Enterprise Automation, GTM Strategy, RevOps", "Completely Remote"),
        ("Priority 1 - Global Remote", "PagerDuty", "US / Distributed", "Greenhouse", "Strategy & Operations, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "New Relic", "US / Distributed", "Greenhouse", "Operations, Strategy, Customer Success", "Completely Remote"),
        ("Priority 1 - Global Remote", "Zscaler", "US / Distributed", "Greenhouse", "Operations, Strategy, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "Automattic / WooCommerce", "US / 100% Remote Global", "Direct", "Operations, Strategy, Customer Success", "Completely Remote"),
        ("Priority 1 - Global Remote", "Zapier", "US / 100% Remote Global", "Direct", "Operations, Strategy, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "Deel", "US / 100% Remote Global", "Direct", "GTM Strategy, RevOps, Operations", "Completely Remote"),
        ("Priority 1 - Global Remote", "Grafana Labs", "US / 100% Fully Remote", "Greenhouse", "Strategy, Operations, Chief of Staff, GTM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Vercel", "US / 100% Fully Remote", "Greenhouse", "Operations, Strategy, Customer Success, GTM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Coinbase", "US / Remote-First", "Greenhouse", "Strategy, Operations, Business Operations, GTM", "Completely Remote"),
        ("Priority 1 - Global Remote", "Cockroach Labs", "US / Remote-First", "Greenhouse", "Strategy, Operations, GTM, Program Management", "Completely Remote"),
        ("Priority 1 - Global Remote", "Webflow", "US / Remote-First", "Greenhouse", "Operations, Strategy, Business Operations, GTM", "Completely Remote"),

        # Priority 2: AI Pioneers & Modern Unicorns
        ("Priority 1 / AI Pioneer", "Anthropic", "US / Remote-Friendly", "Greenhouse", "Strategy, Operations, Customer Success, Program Management", "Remote & US"),
        ("Priority 1 / AI Pioneer", "Databricks", "US / Remote & India", "Greenhouse", "Manager Strategy & Ops, Senior TPM, PMO", "Remote & Bengaluru"),
        ("Priority 1 / AI Pioneer", "Scale AI", "US / Remote-Friendly", "Greenhouse", "Operations, Strategy, Chief of Staff", "Remote & US"),
        ("Priority 1 / AI Pioneer", "Glean", "US / Bengaluru Hub", "Greenhouse", "Strategy & Operations, Customer Success, GTM", "Remote & Bengaluru"),
        ("Priority 1 / AI Pioneer", "Shield AI", "US / Defense Tech Leader", "Lever", "Strategy & Operations, Operations Leadership, TPM", "Remote & US"),
        ("Priority 1 / AI Pioneer", "ElevenLabs", "US / Voice AI Unicorn", "Ashby", "Strategy, Operations, Founder's Office, GTM", "Remote & Global"),
        ("Priority 1 / AI Pioneer", "Perplexity", "US / Conversational AI", "Ashby", "Strategy, Operations, Founder's Office, GTM", "Remote & US"),
        ("Priority 1 / AI Pioneer", "Linear", "US / Dev & Product Tech", "Ashby", "Strategy, Operations, GTM, Program Management", "Remote & Global"),
        ("Priority 1 / AI Pioneer", "Ramp", "US / FinTech Unicorn", "Ashby", "Strategy, Operations, BizOps, GTM, RevOps", "Remote & US"),
        ("Priority 1 / AI Pioneer", "Replit", "US / AI Dev Platform", "Ashby", "Strategy, Operations, GTM, Program Management", "Remote & US"),
        ("Priority 1 / AI Pioneer", "Synthesia", "UK / AI Video Unicorn", "Ashby", "Strategy, Operations, GTM, Customer Success", "Remote & Global"),
        ("Priority 1 / AI Pioneer", "Harvey", "US / Legal AI Unicorn", "Ashby", "Strategy, Operations, GTM, Program Management", "Remote & US"),
        ("Priority 1 / AI Pioneer", "LangChain", "US / AI Framework Leader", "Ashby", "Strategy, Operations, GTM, Program Management", "Remote & Global"),

        # Priority 2: Hyderabad GCCs
        ("Priority 2 - Hyderabad", "Qualcomm", "US Fortune 500 GCC", "Workday", "Technical Program Management, Strategic PMO", "Hyderabad"),
        ("Priority 2 - Hyderabad", "ServiceNow", "US Enterprise Tech GCC", "Custom", "Strategy & Operations, BizOps, TPM", "Hyderabad"),
        ("Priority 2 - Hyderabad", "Uber", "US Tech GCC", "Custom", "Central Operations, BizOps, Strategy", "Hyderabad"),
        ("Priority 2 - Hyderabad", "Google", "US Tech GCC", "Custom", "Strategy & Operations, Technical Program Management", "Hyderabad"),
        ("Priority 2 - Hyderabad", "HighLevel", "US SaaS / India GCC", "Direct", "Strategic Operations, Customer Success", "Hyderabad"),

        # Priority 3: Bengaluru Hub
        ("Priority 3 - Bengaluru", "MongoDB", "US Enterprise Tech Hub", "Greenhouse", "Cloud Operations, GTM Tech, Senior TPM", "Bengaluru"),
        ("Priority 3 - Bengaluru", "InMobi", "Global AdTech / AI Unicorn", "Greenhouse", "Director Global RevOps, TPM, Business Operations", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Instawork", "US Labor Tech Unicorn", "Greenhouse", "Operations, Strategy, GTM Execution", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Rubrik", "Cloud Data Management", "Greenhouse", "Strategy & Operations, Business Operations", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Samsara", "Connected Operations Cloud", "Greenhouse", "Operations, Strategy, Program Management", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Druva", "Cloud Data Protection", "Greenhouse", "Strategy, Operations, Customer Success, GTM", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Qualtrics", "Experience Management Leader", "Greenhouse", "Strategy, Operations, Customer Success, GTM", "Bengaluru"),
        ("Priority 3 - Bengaluru", "6sense", "B2B Revenue AI Platform", "Greenhouse", "Strategy, Operations, Customer Success, GTM", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Gusto", "HR & Payroll Tech Leader", "Greenhouse", "Strategy, Operations, GTM, Program Management", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Reddit", "Social & Community Platform", "Greenhouse", "Strategy, Operations, GTM, Program Management", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Roblox", "Gaming & Metaverse Tech", "Greenhouse", "Strategy, Operations, Program Management", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Groww", "FinTech Unicorn", "Greenhouse", "Strategy & Operations, Founder's Office, Central Ops", "Bengaluru"),
        ("Priority 3 - Bengaluru", "Meesho", "E-Commerce Scale-Up", "Lever", "Category Operations, Founder's Office, Strategy", "Bengaluru"),
        ("Priority 3 - Bengaluru", "CRED", "FinTech Scale-Up", "Lever", "Strategy, Growth, Founder's Office, PMO", "Bengaluru"),

        # Priority 4: Gurugram Hub
        ("Priority 4 - Gurugram", "MongoDB (Gurugram)", "US Enterprise Tech Hub", "Greenhouse", "Staff TPM, GTM Tech Engineering", "Gurugram"),
        ("Priority 4 - Gurugram", "Zomato / Blinkit", "Quick Commerce Leader", "Direct", "Operations Leadership, Category Management", "Gurugram"),
        ("Priority 4 - Gurugram", "Pristyn Care", "HealthTech Unicorn", "Direct", "Strategy & Operations, Founder's Office", "Gurugram")
    ]

    for comp_row in company_directory:
        ws_comp.append(comp_row)
        curr_r = ws_comp.max_row
        ws_comp.row_dimensions[curr_r].height = 20

        p_tier_text = comp_row[0]
        c1 = ws_comp.cell(row=curr_r, column=1)
        if "Priority 1" in p_tier_text:
            c1.fill = P1_FILL
            c1.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        elif "Priority 2" in p_tier_text:
            c1.fill = P2_FILL
            c1.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        elif "Priority 3" in p_tier_text:
            c1.fill = P3_FILL
            c1.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        elif "Priority 4" in p_tier_text:
            c1.fill = P4_FILL
            c1.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")

        for c_idx in range(1, len(comp_row) + 1):
            cell = ws_comp.cell(row=curr_r, column=c_idx)
            cell.border = THIN_BORDER
            if c_idx > 1:
                cell.font = DATA_FONT

    ws_comp.auto_filter.ref = ws_comp.dimensions
    for col in ws_comp.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws_comp.column_dimensions[col_letter].width = min(max(max_len + 3, 14), 45)

    # ----------------------------------------------------
    # TAB 8: MASTER TRACKER (ALL ROLES)
    # ----------------------------------------------------
    ws_all = wb.create_sheet(title="Master Tracker (All Roles)")
    format_table_sheet(ws_all, records, NAVY_FILL, show_priority_col=True)

    # Save to disk
    OUTPUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUTPUT_XLSX)
    print(f"[Success] Workbook saved to: {OUTPUT_XLSX}")

    try:
        shutil.copy(OUTPUT_XLSX, DESKTOP_XLSX)
        print(f"[Success] Copied directly to Desktop: {DESKTOP_XLSX}")
    except Exception as e:
        print(f"[Note] Desktop copy notice: {e}")

    return OUTPUT_XLSX


if __name__ == "__main__":
    export_tracker_to_excel()
