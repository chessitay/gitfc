import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta


def is_git_repo():
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True)
    return result.returncode == 0


def get_current_branch():
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


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


def create_commit(message, date, amend=False, stage_all=False):
    if stage_all:
        subprocess.run(["git", "add", "-A"])

    env = os.environ.copy()
    env["GIT_COMMITTER_DATE"] = date

    cmd = ["git", "commit", "--date", date]
    if amend:
        cmd.append("--amend")
        if message:
            cmd += ["-m", message]
        else:
            cmd.append("--no-edit")
    else:
        cmd += ["-m", message]

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        return None

    hash_result = subprocess.run(["git", "log", "-1", "--format=%H"], capture_output=True, text=True)
    return hash_result.stdout.strip()


def do_push():
    result = subprocess.run(["git", "push"])
    return result.returncode


def _build_queue_parser():
    parser = argparse.ArgumentParser(prog="gitfc queue", description="Manage commit push queue")
    sub = parser.add_subparsers(dest="queue_action")

    # add
    add_p = sub.add_parser("add", help="Add a commit to the push queue")
    add_p.add_argument("-a", action="store_true", help="Stage all changes before committing")
    add_p.add_argument("--amend", action="store_true", help="Amend the previous commit")
    add_p.add_argument("--push-at", help='When to push (absolute): "2026-04-02 16:00"')
    add_p.add_argument("--push-in", help='When to push (relative): "2h", "30m"')
    add_p.add_argument("--jitter", help='Random offset: "10m", "1h"')
    add_p.add_argument("--after", choices=["last"], help="Schedule after last queued item")
    add_p.add_argument("message", nargs="?", default=None, help="Commit message")
    add_p.add_argument("date", nargs="?", default=None, help="Commit date")

    # list
    sub.add_parser("list", aliases=["ls"], help="Show queued items")

    # remove
    rm_p = sub.add_parser("remove", aliases=["rm"], help="Remove item by ID")
    rm_p.add_argument("id", type=int, help="Queue item ID")

    # clear
    clear_p = sub.add_parser("clear", help="Remove all pending items")
    clear_p.add_argument("--force", action="store_true", help="Skip confirmation")

    # run
    run_p = sub.add_parser("run", help="Process due items")
    run_p.add_argument("--watch", action="store_true", help="Keep running, check periodically")
    run_p.add_argument("--daemon", action="store_true", help="Run in background")
    run_p.add_argument("--poll", type=int, default=60, help="Seconds between checks (default: 60)")

    # batch
    batch_p = sub.add_parser("batch", help="Set push times for pending items")
    batch_p.add_argument("--interval", required=True, help='Time between pushes: "30m", "2h"')
    batch_p.add_argument("--jitter", help='Random offset per push: "10m"')
    batch_p.add_argument("--start-at", help="When first push happens (default: now)")

    # stop / status
    sub.add_parser("stop", help="Stop background daemon")
    sub.add_parser("status", help="Show daemon and queue summary")

    return parser


def main():
    if not is_git_repo():
        print("Error: not a git repository", file=sys.stderr)
        sys.exit(1)

    # route "queue" / "q" to the queue subsystem before argparse sees positional args
    if len(sys.argv) > 1 and sys.argv[1] in ("queue", "q"):
        queue_parser = _build_queue_parser()
        args = queue_parser.parse_args(sys.argv[2:])
        from fc_queue import handle_queue
        handle_queue(args)
        return

    # --- direct commit (original behavior) ---
    parser = argparse.ArgumentParser(
        description="Git commit with a custom date.",
        usage='gitfc "commit message" [date]',
    )
    parser.add_argument("-a", action="store_true", help="Stage all changes before committing")
    parser.add_argument("--amend", action="store_true", help="Amend the previous commit with a new date")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show commit details after committing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be committed without doing it")
    parser.add_argument("-p", "--push", action="store_true", help="Push to remote after committing")
    parser.add_argument("message", nargs="?", default=None, help="Commit message")
    parser.add_argument("date", nargs="?", default=None, help='Optional date: "+15m", "-2d", "14:30", or "2026-04-01 14:30:00"')
    args = parser.parse_args()

    if not args.amend and not args.message:
        parser.error("message is required (unless using --amend)")

    date = parse_date(args.date)

    if args.dry_run:
        cmd = ["git", "commit", "--date", date]
        if args.amend:
            cmd.append("--amend")
            if args.message:
                cmd += ["-m", args.message]
            else:
                cmd.append("--no-edit")
        else:
            cmd += ["-m", args.message]
        print(f"Command: {' '.join(cmd)}")
        print(f"Date:    {date}")
        sys.exit(0)

    commit_hash = create_commit(args.message, date, amend=args.amend, stage_all=args.a)

    if commit_hash is None:
        sys.exit(1)

    if args.verbose:
        subprocess.run(["git", "log", "--format=Hash:    %H%nAuthor:  %ai%nCommit:  %ci%nMessage: %s", "-1"])

    if args.push:
        rc = do_push()
        if rc != 0:
            sys.exit(rc)

    sys.exit(0)
