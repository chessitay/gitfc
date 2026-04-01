import argparse
import os
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(
        description="Git commit with a custom date.",
        usage='gitfc "commit message" "YYYY-MM-DD HH:MM:SS"',
    )
    parser.add_argument("message", help="Commit message")
    parser.add_argument("date", help='Date and time, for example "2026-04-01 14:30:00"')
    args = parser.parse_args()

    env = os.environ.copy()
    env["GIT_COMMITTER_DATE"] = args.date

    result = subprocess.run(
        ["git", "commit", "--date", args.date, "-m", args.message],
        env=env,
    )
    sys.exit(result.returncode)
