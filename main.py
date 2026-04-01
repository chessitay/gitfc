import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


def is_git_repo():
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True)
    return result.returncode == 0


def validate_date(date_str):
    formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
    for fmt in formats:
        try:
            datetime.strptime(date_str, fmt)
            return True
        except ValueError:
            continue
    return False


def parse_date(value):
    now = datetime.now()

    if value is None:
        return now.strftime("%Y-%m-%d %H:%M:%S")

    # relative offset - +15m, -2h, +3d
    match = re.fullmatch(r"([+-]\d+)([mhd])", value)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"m": timedelta(minutes=amount), "h": timedelta(hours=amount), "d": timedelta(days=amount)}[unit]
        return (now + delta).strftime("%Y-%m-%d %H:%M:%S")

    # time only - "14:30" or "14:30:00" (today at that time)
    if re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", value):
        return f"{now.strftime('%Y-%m-%d')} {value}"

    if not validate_date(value):
        print(f'Error: invalid date format "{value}"', file=sys.stderr)
        print('Expected: "+15m", "-2d", "14:30", "2026-04-01", or "2026-04-01 14:30:00"', file=sys.stderr)
        sys.exit(1)

    return value


def main():
    parser = argparse.ArgumentParser(
        description="Git commit with a custom date.",
        usage='gitfc "commit message" [date]',
    )
    parser.add_argument("-a", action="store_true", help="Stage all changes before committing")
    parser.add_argument("--amend", action="store_true", help="Amend the previous commit with a new date")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show commit details after committing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be committed without doing it")
    parser.add_argument("message", nargs="?", default=None, help="Commit message")
    parser.add_argument("date", nargs="?", default=None, help='Optional date: "+15m", "-2d", "14:30", or "2026-04-01 14:30:00"')
    args = parser.parse_args()

    if not is_git_repo():
        print("Error: not a git repository", file=sys.stderr)
        sys.exit(1)

    if not args.amend and not args.message:
        parser.error("message is required (unless using --amend)")

    if args.a:
        subprocess.run(["git", "add", "-A"])

    date = parse_date(args.date)

    env = os.environ.copy()
    env["GIT_COMMITTER_DATE"] = date

    cmd = ["git", "commit", "--date", date]
    if args.amend:
        cmd.append("--amend")
        if args.message:
            cmd += ["-m", args.message]
        else:
            cmd.append("--no-edit")
    else:
        cmd += ["-m", args.message]

    if args.dry_run:
        print(f"Command: {' '.join(cmd)}")
        print(f"Date:    {date}")
        sys.exit(0)

    result = subprocess.run(cmd, env=env)

    if result.returncode == 0 and args.verbose:
        subprocess.run(["git", "log", "--format=Hash:    %H%nAuthor:  %ai%nCommit:  %ci%nMessage: %s", "-1"])

    sys.exit(result.returncode)
