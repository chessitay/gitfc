import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


def parse_date(value):
    now = datetime.now()

    if value is None:
        return now.strftime("%Y-%m-%d %H:%M:%S")

    # Relative offset: +15m, -2h, +3d
    match = re.fullmatch(r"([+-]\d+)([mhd])", value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
        return (now + delta).strftime("%Y-%m-%d %H:%M:%S")

    # Time only: "14:30" or "14:30:00" → today at that time
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", value):
        return f"{now.strftime('%Y-%m-%d')} {value}"

    # Full datetime: pass through as-is
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Git commit with a custom date.",
        usage='gitfc "commit message" [date]',
    )
    parser.add_argument("message", help="Commit message")
    parser.add_argument("date", nargs="?", default=None, help='Optional date: "+15m", "-2d", "14:30", or "2026-04-01 14:30:00"')
    args = parser.parse_args()

    date = parse_date(args.date)

    env = os.environ.copy()
    env["GIT_COMMITTER_DATE"] = date

    result = subprocess.run(
        ["git", "commit", "--date", date, "-m", args.message],
        env=env,
    )
    sys.exit(result.returncode)
