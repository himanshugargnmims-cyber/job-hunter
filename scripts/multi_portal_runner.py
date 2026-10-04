#!/usr/bin/env python3
"""
multi_portal_runner.py - Parallel Multi-Portal Autonomous Application Orchestrator

Detects all authenticated sessions (Naukri, IIMjobs, Instahyre, LinkedIn, etc.)
and coordinates parallel application runs across all platforms concurrently.
"""

import sys
import subprocess
import time
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SESSIONS_DIR = BASE_DIR / "sessions"
VENV_PY = BASE_DIR.parent / ".venv" / "bin" / "python"
if not VENV_PY.exists():
    VENV_PY = Path(sys.executable)

PORTAL_SCRIPTS = {
    "iimjobs": {
        "name": "IIMjobs.com",
        "session": SESSIONS_DIR / "iimjobs_state.json",
        "script": BASE_DIR / "scripts" / "iimjobs_applier.py",
        "default_target": 30
    },
    "naukri": {
        "name": "Naukri.com",
        "session": SESSIONS_DIR / "naukri_state.json",
        "script": BASE_DIR / "scripts" / "naukri_applier.py",
        "default_target": 30
    },
    "instahyre": {
        "name": "Instahyre.com",
        "session": SESSIONS_DIR / "instahyre_state.json",
        "script": BASE_DIR / "scripts" / "instahyre_applier.py",
        "default_target": 25
    }
}


def get_available_portals():
    available = []
    for key, cfg in PORTAL_SCRIPTS.items():
        if cfg["session"].exists() and cfg["session"].stat().st_size > 50:
            available.append(key)
    return available


def run_parallel(portals_to_run=None, target_per_portal: int = 25, min_score: float = 70.0):
    available = get_available_portals()
    if portals_to_run:
        target_keys = [k for k in portals_to_run if k in available]
    else:
        target_keys = available

    print("\n" + "=" * 70)
    print("      MULTI-PORTAL PARALLEL APPLICATION ORCHESTRATOR")
    print("=" * 70)
    print(f"Authenticated Portals Ready: {', '.join(target_keys) if target_keys else 'None'}")
    print(f"Target Submissions Per Portal: {target_per_portal}")
    print(f"Min Fit Score Threshold:       {min_score}%")
    print("=" * 70)

    if not target_keys:
        print("\n[Notice] No active non-LinkedIn portal sessions found!")
        print("Please log into portals first using:")
        print("  ./.venv/bin/python job-hunter/scripts/login_portal.py --portal <name>\n")
        return

    processes = {}
    for key in target_keys:
        cfg = PORTAL_SCRIPTS[key]
        cmd = [
            str(VENV_PY),
            str(cfg["script"]),
            "--target", str(target_per_portal),
            "--min-score", str(min_score)
        ]
        print(f"[*] Launching parallel engine for {cfg['name']}...")
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        processes[key] = p

    print("\nAll target portal engines launched in parallel. Monitoring output...\n")

    # Monitor processes until finished
    while processes:
        for key in list(processes.keys()):
            proc = processes[key]
            line = proc.stdout.readline()
            if line:
                print(f"[{PORTAL_SCRIPTS[key]['name']}] {line.strip()}")
            if proc.poll() is not None:
                # Flush remaining lines
                for rem in proc.stdout.readlines():
                    print(f"[{PORTAL_SCRIPTS[key]['name']}] {rem.strip()}")
                print(f"[Done] Engine for {PORTAL_SCRIPTS[key]['name']} exited with code {proc.returncode}.\n")
                del processes[key]
        time.sleep(0.5)

    print("=" * 70)
    print("PARALLEL MULTI-PORTAL RUN FINISHED")
    print(f"View cumulative submissions in: {BASE_DIR / 'data' / 'tracker.csv'}")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Multi-Portal Parallel Application Runner")
    parser.add_argument("--portals", nargs="+", help="Specific portals to run (default: all authenticated)")
    parser.add_argument("--target-each", type=int, default=25, help="Submissions target per portal (default: 25)")
    parser.add_argument("--min-score", type=float, default=70.0, help="Minimum fit score (default: 70)")
    args = parser.parse_args()

    run_parallel(portals_to_run=args.portals, target_per_portal=args.target_each, min_score=args.min_score)


if __name__ == "__main__":
    main()
