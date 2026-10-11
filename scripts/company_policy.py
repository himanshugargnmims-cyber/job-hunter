#!/usr/bin/env python3
"""
company_policy.py - Company Policy & Cooloff Ledger

Enforces:
1. Strict maximum cap of 2 active applications per company across the entire database.
2. Portal-specific cooloff tracking (e.g., Ashby 60-day cooloff, Workday session lockouts).
3. Geo-restriction / Recruiter blacklists (e.g., Clipboard).
"""

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "jobs.db"


def normalize_company(company_name: str) -> str:
    """Normalizes company name for robust deduplication and policy matching."""
    if not company_name:
        return ""
    name = company_name.lower().strip()
    # Strip common corporate suffixes
    name = re.sub(r"\b(pvt\.?|ltd\.?|private limited|limited|inc\.?|llc|technologies|solutions|corp\.?|corporation)\b", "", name)
    name = re.sub(r"[^a-z0-9]", "", name)
    return name


class CompanyPolicyManager:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _init_db(self):
        """Ensures the company_policies table exists in jobs.db."""
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
        with sqlite3.connect(self.db_path, timeout=30.0) as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS company_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_normalized TEXT UNIQUE,
                    company_display TEXT,
                    platform TEXT,
                    cooloff_until TEXT,
                    cooloff_reason TEXT,
                    is_blacklisted INTEGER DEFAULT 0,
                    blacklist_reason TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_submitted_count(self, company: str) -> int:
        """Returns number of confirmed submitted applications for this company in jobs.db."""
        norm = normalize_company(company)
        if not norm or norm in ['company', 'confidential', 'stealth']:
            return 0
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cur = conn.cursor()
                # Check using exact and like matching
                cur.execute("SELECT company, status FROM jobs WHERE status = 'Submitted'")
                rows = cur.fetchall()
                count = sum(1 for r_comp, _ in rows if normalize_company(r_comp) == norm)
                return count
        except Exception as e:
            print(f"[CompanyPolicy] Error reading submitted count for {company}: {e}")
            return 0

    def can_apply(self, company: str, platform: str = "") -> Tuple[bool, str]:
        """
        Determines whether an application can proceed for this company.
        
        Returns:
            (True, "Eligible") if allowed.
            (False, "<Reason>") if blocked by cap, cooloff, or blacklist.
        """
        norm = normalize_company(company)
        if not norm:
            return True, "Eligible"

        # Disregard generic placeholders
        if norm in ['company', 'confidential', 'stealth']:
            return True, "Eligible"

        # 1. Check database policy table
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT is_blacklisted, blacklist_reason, cooloff_until, cooloff_reason
                    FROM company_policies WHERE company_normalized = ?
                """, (norm,))
                row = cur.fetchone()
                if row:
                    is_blacklisted, bl_reason, cooloff_until, co_reason = row
                    if is_blacklisted:
                        return False, f"Company is blacklisted: {bl_reason or 'Geo-restriction policy'}"

                    if cooloff_until:
                        try:
                            co_dt = datetime.fromisoformat(cooloff_until)
                            if datetime.now() < co_dt:
                                return False, f"Company in cooloff until {co_dt.strftime('%Y-%m-%d')} ({co_reason or 'Platform cooloff'})"
                        except Exception:
                            pass
        except Exception as e:
            print(f"[CompanyPolicy] Policy lookup note: {e}")

        # 2. Check strict company application cap (<= 2 per company)
        submitted_count = self.get_submitted_count(company)
        if submitted_count >= 2:
            return False, f"Maximum company cap reached: {submitted_count} submitted applications already recorded"

        return True, "Eligible"

    def record_cooloff(self, company: str, platform: str, duration_days: int, reason: str):
        """Records a cooldown period for a company (e.g. Ashby 60-day cooloff limit)."""
        norm = normalize_company(company)
        if not norm:
            return
        cooloff_until = (datetime.now() + timedelta(days=duration_days)).isoformat()
        now_str = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO company_policies (company_normalized, company_display, platform, cooloff_until, cooloff_reason, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(company_normalized) DO UPDATE SET
                        platform=excluded.platform,
                        cooloff_until=excluded.cooloff_until,
                        cooloff_reason=excluded.cooloff_reason,
                        updated_at=excluded.updated_at
                """, (norm, company, platform, cooloff_until, reason, now_str))
                conn.commit()
                print(f"[CompanyPolicy] Recorded {duration_days}-day cooloff for {company} ({reason})")
        except Exception as e:
            print(f"[CompanyPolicy] Error recording cooloff for {company}: {e}")

    def record_blacklist(self, company: str, reason: str):
        """Records a permanent blacklist for a company (e.g. strict US-only / geo-restriction)."""
        norm = normalize_company(company)
        if not norm:
            return
        now_str = datetime.now().isoformat()
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO company_policies (company_normalized, company_display, is_blacklisted, blacklist_reason, updated_at)
                    VALUES (?, ?, 1, ?, ?)
                    ON CONFLICT(company_normalized) DO UPDATE SET
                        is_blacklisted=1,
                        blacklist_reason=excluded.blacklist_reason,
                        updated_at=excluded.updated_at
                """, (norm, company, reason, now_str))
                conn.commit()
                print(f"[CompanyPolicy] Recorded blacklist for {company}: {reason}")
        except Exception as e:
            print(f"[CompanyPolicy] Error recording blacklist for {company}: {e}")


# Initialize pre-known policies
def init_known_policies():
    mgr = CompanyPolicyManager()
    # 1. Clipboard: US/Americas geo-restriction rejection received
    mgr.record_blacklist("Clipboard", "Rejection: Role requires US/Americas residency / No APAC remote")
    # 2. Sarvam AI: Ashby 60-day application limit encountered on 2026-10-09
    mgr.record_cooloff("Sarvam AI", "Ashby", 60, "Ashby 60-day application throttling limit")


if __name__ == "__main__":
    init_known_policies()
    mgr = CompanyPolicyManager()
    print("=== Testing Company Policy Manager ===")
    can_hero, reason_hero = mgr.can_apply("Hero Vired")
    print(f"Hero Vired (1 app): can_apply={can_hero}, reason={reason_hero}")
    
    can_sarvam, reason_sarvam = mgr.can_apply("Sarvam AI")
    print(f"Sarvam AI (Ashby 60d cooloff): can_apply={can_sarvam}, reason={reason_sarvam}")
    
    can_clip, reason_clip = mgr.can_apply("Clipboard")
    print(f"Clipboard (Blacklisted): can_apply={can_clip}, reason={reason_clip}")
