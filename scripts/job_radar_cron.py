#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "job_radar.py"
TRACKING = ROOT / "tracking" / "job-radar"
CRON_DIR = TRACKING / "cron"
PYTHON = TRACKING / ".venv" / "bin" / "python"


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def run_radar(limit_per_query: int, agentmail_days: int, no_getonboard: bool) -> dict:
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(PYTHON if PYTHON.exists() else sys.executable),
        str(RUNNER),
        "--limit-per-query",
        str(limit_per_query),
        "--agentmail-days",
        str(agentmail_days),
    ]
    if no_getonboard:
        cmd.append("--no-getonboard")
    started_at = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=900)
    finished_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "returncode": proc.returncode,
        "cmd": cmd,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }
    path = CRON_DIR / f"job-radar-cron-{now_stamp()}.json"
    latest = CRON_DIR / "job-radar-cron-latest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    latest.write_bytes(path.read_bytes())
    return {"path": str(path), "latest": str(latest), **payload}


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Job Radar cron wrapper. Does not send Telegram by itself.")
    parser.add_argument("--limit-per-query", type=int, default=10)
    parser.add_argument("--agentmail-days", type=int, default=14)
    parser.add_argument("--no-getonboard", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "would_run": [
                        str(PYTHON if PYTHON.exists() else sys.executable),
                        str(RUNNER),
                        "--limit-per-query",
                        str(args.limit_per_query),
                        "--agentmail-days",
                        str(args.agentmail_days),
                    ],
                    "cron_example_lima": "0 7 * * 1-5 cd /home/ubuntu/.openclaw/workspace && scripts/job_radar_cron.py",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    result = run_radar(args.limit_per_query, args.agentmail_days, args.no_getonboard)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["returncode"])


if __name__ == "__main__":
    raise SystemExit(main())
