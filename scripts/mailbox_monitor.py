#!/usr/bin/env python3
"""
mailbox_monitor.py - Automated Recruiter Response & Interview Invitation Monitor

Connects to candidate mailbox (Gmail SSL IMAP) using credentials in `job-hunter/.env`:
- Scans recent messages for application confirmations, recruiter outreach, and interview invitations.
- Classifies responses using intelligent pattern detection.
- Cross-references with `jobs.db` and updates application tracking status.
- Syncs the updated data directly to the Desktop Excel workbook.
"""

import os
import re
import sys
import email
import imaplib
import sqlite3
from email.header import decode_header
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "data" / "jobs.db"
SCRIPT_DIR = BASE_DIR / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from export_excel import export_tracker_to_excel
except ImportError:
    export_tracker_to_excel = None


def clean_header_text(header_val: str) -> str:
    if not header_val:
        return ""
    try:
        decoded_parts = decode_header(header_val)
        parts = []
        for text, enc in decoded_parts:
            if isinstance(text, bytes):
                parts.append(text.decode(enc or "utf-8", errors="ignore"))
            else:
                parts.append(str(text))
        return " ".join(parts).strip()
    except Exception:
        return str(header_val)


class MailboxMonitor:
    def __init__(self, email_user: str = None, email_pass: str = None):
        self.email_user = email_user or os.getenv("GMAIL_USER") or os.getenv("EMAIL_USER")
        self.email_pass = email_pass or os.getenv("GMAIL_APP_PASSWORD") or os.getenv("EMAIL_APP_PASSWORD")

    def is_configured(self) -> bool:
        return bool(self.email_user and self.email_pass)

    def scan_inbox(self, max_recent: int = 150):
        if not self.is_configured():
            print("\n[Mailbox Monitor] Mailbox credentials not yet configured.")
            print("Please ensure GMAIL_USER and GMAIL_APP_PASSWORD exist in job-hunter/.env\n")
            return []

        print(f"\nConnecting to {self.email_user} via SSL IMAP...")
        try:
            # Strip spaces from app password if present
            clean_pass = self.email_pass.replace(" ", "")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(self.email_user, clean_pass)
            mail.select("inbox")
            print("[Connected] Fetching recent messages...")

            status, search_data = mail.search(None, "ALL")
            mail_ids = search_data[0].split()
            total_msgs = len(mail_ids)
            print(f"Total messages in inbox: {total_msgs}. Inspecting last {min(max_recent, total_msgs)} messages...")

            target_ids = mail_ids[-max_recent:]
            responses_found = []

            # Keywords indicative of hiring/job responses
            job_keywords = [
                "greenhouse", "lever", "ashby", "iimjobs", "linkedin", "talent500",
                "interview", "application", "applied", "candidate", "recruiter",
                "chief of staff", "program manager", "strategy", "gmeet", "round",
                "hiring", "careers", "talent", "assessment", "invitation", "turing"
            ]

            # Batch fetch headers for high performance
            id_set = b",".join(target_ids)
            status, batch_data = mail.fetch(id_set, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")

            for item in batch_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw_bytes = item[1]
                msg = email.message_from_bytes(raw_bytes)

                subject = clean_header_text(msg.get("Subject", ""))
                from_addr = clean_header_text(msg.get("From", ""))
                date_str = clean_header_text(msg.get("Date", ""))

                combined_text = f"{from_addr} {subject}".lower()

                # Filter for job relevance
                if not any(k in combined_text for k in job_keywords):
                    continue

                # Categorize email
                category = "APPLICATION_CONFIRMED"
                if any(k in combined_text for k in ["interview", "invitation", "schedule a call", "next steps", "chat with", "phone screen", "gmeet", "rd 1", "round 1", "round 2"]):
                    category = "INTERVIEW_INVITE"
                elif any(k in combined_text for k in ["thank you for applying", "application received", "we received your application", "security code", "application status", "talent500"]):
                    category = "APPLICATION_CONFIRMED"
                elif any(k in combined_text for k in ["not moving forward", "other candidates", "unfortunately"]):
                    category = "REJECTION"

                responses_found.append({
                    "from": from_addr,
                    "subject": subject,
                    "date": date_str,
                    "category": category
                })

            mail.close()
            mail.logout()

            # Print Report
            print("\n" + "=" * 80)
            print("                 LIVE RECRUITER & APPLICATION RESPONSE REPORT")
            print("=" * 80)
            print(f"{'CATEGORY':<24} | {'SENDER':<25} | {'SUBJECT':<30}")
            print("-" * 80)

            for resp in responses_found:
                badge = f"[{resp['category']}]"
                print(f"{badge:<24} | {resp['from'][:25]:<25} | {resp['subject'][:30]}")

            print("=" * 80)
            print(f"Total Relevant Responses Identified: {len(responses_found)}\n")

            # Update database if matching company found
            if DB_PATH.exists() and responses_found:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                for resp in responses_found:
                    cat = resp["category"]
                    subj = resp["subject"]
                    for token in re.findall(r'\b[A-Za-z0-9]{3,}\b', subj):
                        cursor.execute("""
                            UPDATE jobs
                            SET notes = notes || ' | Recruiter Email: ' || ?
                            WHERE company LIKE ? AND notes NOT LIKE ?
                        """, (f"{cat} ({subj[:40]})", f"%{token}%", f"%{token}%"))
                conn.commit()
                conn.close()

            # Refresh Excel file
            if export_tracker_to_excel:
                print("Refreshing Desktop Excel spreadsheet with mailbox updates...")
                export_tracker_to_excel()

            return responses_found

        except Exception as e:
            print(f"[Mailbox Error] Exception while checking mailbox: {e}")
            return []


if __name__ == "__main__":
    monitor = MailboxMonitor()
    monitor.scan_inbox()
