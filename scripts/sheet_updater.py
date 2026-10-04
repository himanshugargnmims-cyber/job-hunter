"""
Application Tracker & Sheet Updater Module.

Persists and syncs application lifecycle tracking across:
1. Local CSV spreadsheet (job-hunter/data/tracker.csv)
2. SQLite Database (job-hunter/data/jobs.db)
3. Google Sheets (via gspread / service account credentials)

Columns tracked:
Date, Company, Job Title, Location, URL, Selected Resume Variant, Fit Score, Status, Notes
"""

import os
import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dotenv import load_dotenv

load_dotenv()

HEADERS = [
    "Date",
    "Company",
    "Job Title",
    "Location",
    "URL",
    "Selected Resume Variant",
    "Fit Score",
    "Status",
    "Screenshot Path",
    "Notes"
]

VALID_STATUSES = {
    "Pending Approval",
    "Pre-filled - Ready for Review",
    "Found",
    "Pre-filled",
    "Submitted",
    "Interview",
    "Rejected",
    "Offer"
}


class SheetUpdater:
    def __init__(
        self,
        csv_path: Optional[str] = None,
        db_path: Optional[str] = None,
        google_sheet_name: Optional[str] = None
    ):
        base_dir = Path(__file__).resolve().parent.parent
        self.csv_path = Path(csv_path) if csv_path else (base_dir / "data" / "tracker.csv")
        self.db_path = Path(db_path) if db_path else (base_dir / "data" / "jobs.db")
        self.google_sheet_name = google_sheet_name or os.getenv("GOOGLE_SHEET_NAME", "Job Application Tracker")

        self.gspread_client = None
        self.worksheet = None

        self._init_csv()
        self._init_db()
        self._init_google_sheets()

    def _init_csv(self):
        """Ensure CSV file exists with standard headers."""
        if not self.csv_path.exists() or self.csv_path.stat().st_size == 0:
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(HEADERS)

    def _init_db(self):
        """Ensure SQLite schema exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                title TEXT NOT NULL,
                location TEXT NOT NULL,
                url TEXT UNIQUE NOT NULL,
                board_type TEXT,
                description TEXT,
                matched_resume TEXT,
                fit_score REAL,
                fit_rationale TEXT,
                status TEXT DEFAULT 'Found',
                date_scraped TEXT,
                date_updated TEXT,
                notes TEXT
            )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_jobs_url ON jobs (url)")
            conn.commit()

    def _init_google_sheets(self):
        """Initializes Google Sheets client if credentials exist."""
        creds_candidates = [
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            str(self.csv_path.parent.parent / "credentials.json"),
            "credentials.json",
            "service_account.json",
            os.path.expanduser("~/.config/gspread/service_account.json")
        ]

        cred_path = None
        for p in creds_candidates:
            if p and Path(p).exists():
                cred_path = p
                break

        if cred_path:
            try:
                import gspread
                self.gspread_client = gspread.service_account(filename=cred_path)
                try:
                    sheet = self.gspread_client.open(self.google_sheet_name)
                    self.worksheet = sheet.sheet1
                except gspread.SpreadsheetNotFound:
                    sheet = self.gspread_client.create(self.google_sheet_name)
                    self.worksheet = sheet.sheet1
                    self.worksheet.append_row(HEADERS)
                print(f"[SheetUpdater] Connected to Google Sheet '{self.google_sheet_name}'")
            except Exception as e:
                print(f"[SheetUpdater] Notice: Google Sheets connection unavailable ({e}). Using local CSV & SQLite.")
        else:
            print("[SheetUpdater] Notice: No Google Sheets credentials found. Operating in local CSV & SQLite mode.")

    def get_existing_urls(self) -> Set[str]:
        """Returns set of all job URLs already tracked."""
        urls = set()

        # From CSV
        if self.csv_path.exists():
            try:
                with open(self.csv_path, mode="r", newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        u = row.get("URL")
                        if u:
                            urls.add(u.strip())
            except Exception:
                pass

        # From DB
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT url FROM jobs")
                for (u,) in cursor.fetchall():
                    if u:
                        urls.add(u.strip())
        except Exception:
            pass

        return urls

    def get_submitted_urls(self) -> Set[str]:
        """Returns set of all job URLs that have already been genuinely submitted."""
        urls = set()
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT url FROM jobs WHERE status = 'Submitted'")
                for (u,) in cursor.fetchall():
                    if u:
                        urls.add(u.strip())
        except Exception:
            pass
        return urls

    def log_application(
        self,
        company: str,
        job_title: str,
        location: str,
        url: str,
        selected_resume: str,
        fit_score: float,
        rationale: str = "",
        board_type: str = "",
        description: str = "",
        status: str = "Found",
        notes: str = "",
        screenshot_path: str = ""
    ) -> bool:
        """
        Logs a newly discovered and matched job.
        Avoids duplicates based on URL, or updates existing record if it is now Submitted.
        """
        url = url.strip()
        existing = self.get_existing_urls()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if url in existing:
            # Check if this is an upgrade to Submitted or status update
            if status in ("Submitted", "Pre-filled"):
                self.update_status(url, status, notes=notes, screenshot_path=screenshot_path)
                return True
            return False

        # 1. Append to local CSV
        row = [
            today,
            company,
            job_title,
            location,
            url,
            selected_resume,
            f"{fit_score:.1f}",
            status,
            screenshot_path,
            notes or rationale[:120]
        ]
        with open(self.csv_path, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(row)

        # 2. Insert into SQLite DB
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO jobs (
                company, title, location, url, board_type,
                description, matched_resume, fit_score, fit_rationale,
                status, date_scraped, date_updated, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                company, job_title, location, url, board_type,
                description, selected_resume, fit_score, rationale,
                status, today, today, f"{notes} | Screenshot: {screenshot_path}" if screenshot_path else notes
            ))
            conn.commit()

        # 3. Append to Google Sheets if connected
        if self.worksheet:
            try:
                self.worksheet.append_row(row)
            except Exception as e:
                print(f"[SheetUpdater] Failed to append row to Google Sheet: {e}")

        return True

    def update_status(self, url: str, new_status: str, notes: Optional[str] = None, screenshot_path: Optional[str] = None) -> bool:
        """Updates the status, screenshot, and optional notes for a job application."""
        if new_status not in VALID_STATUSES and new_status not in ("Pending Authentication", "Pending Approval"):
            raise ValueError(f"Invalid status '{new_status}'. Must be one of {VALID_STATUSES}")

        url = url.strip()
        today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Update SQLite DB
        updated = False
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            notes_val = f"{notes} | Screenshot: {screenshot_path}" if (notes and screenshot_path) else (screenshot_path or notes)
            if notes_val is not None:
                cursor.execute("""
                UPDATE jobs SET status = ?, date_updated = ?, notes = ? WHERE url = ?
                """, (new_status, today, notes_val, url))
            else:
                cursor.execute("""
                UPDATE jobs SET status = ?, date_updated = ? WHERE url = ?
                """, (new_status, today, url))
            conn.commit()
            if cursor.rowcount > 0:
                updated = True

        # Rewrite CSV
        if self.csv_path.exists():
            rows = []
            with open(self.csv_path, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                if header:
                    rows.append(header)
                for r in reader:
                    if len(r) > 4 and r[4].strip() == url:
                        if len(r) > 7:
                            r[7] = new_status
                        if screenshot_path and len(r) > 8:
                            r[8] = screenshot_path
                        if notes is not None and len(r) > 9:
                            r[9] = notes
                        updated = True
                    rows.append(r)

            with open(self.csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerows(rows)

        return updated

    def get_summary_stats(self) -> Dict[str, Any]:
        """Returns statistics from the database."""
        stats = {
            "total_jobs": 0,
            "by_status": {},
            "by_company": {},
            "avg_fit_score": 0.0
        }
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), AVG(fit_score) FROM jobs")
            row = cursor.fetchone()
            if row:
                stats["total_jobs"] = row[0] or 0
                stats["avg_fit_score"] = round(row[1] or 0.0, 1)

            cursor.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
            for st, cnt in cursor.fetchall():
                stats["by_status"][st] = cnt

            cursor.execute("SELECT company, COUNT(*) FROM jobs GROUP BY company")
            for comp, cnt in cursor.fetchall():
                stats["by_company"][comp] = cnt

        return stats


if __name__ == "__main__":
    updater = SheetUpdater()
    stats = updater.get_summary_stats()
    print("=== SheetUpdater Stats ===")
    print(stats)
