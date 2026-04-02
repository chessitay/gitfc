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


QUEUE_SUBCOMMANDS = {"add", "list", "ls", "remove", "rm", "clear", "run", "stop", "status"}

# --- ANSI colors ---
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"


def _print_main_help():
    print(f"""
{BOLD}gitfc{RESET} — Git commit with a custom date.

{YELLOW}USAGE{RESET}
  gitfc [flags] {DIM}"message"{RESET} {DIM}[date]{RESET}

{YELLOW}FLAGS{RESET}
  {GREEN}-a{RESET}             Stage all changes before committing (git add -A)
  {GREEN}--amend{RESET}        Amend the previous commit instead of creating a new one
  {GREEN}-v, --verbose{RESET}  Print commit details (hash, date, message) after committing
  {GREEN}-p, --push{RESET}     Push to remote after committing
  {GREEN}--dry-run{RESET}      Show the command and resolved date without committing

{YELLOW}DATE FORMATS{RESET}
  {CYAN}(nothing){RESET}              Current date and time
  {CYAN}+15m{RESET}                   15 minutes from now
  {CYAN}-2h{RESET}                    2 hours ago
  {CYAN}+3d{RESET}                    3 days from now
  {CYAN}14:30{RESET}                  Today at 14:30
  {CYAN}2026-04-01{RESET}             That date at midnight
  {CYAN}2026-04-01 14:30:00{RESET}    Exact date and time

{YELLOW}EXAMPLES{RESET}
  {DIM}${RESET} gitfc "my message"
  {DIM}${RESET} gitfc "my message" "-2d"
  {DIM}${RESET} gitfc -a "my message" "2026-03-15 10:00:00"
  {DIM}${RESET} gitfc --amend "-1h"
  {DIM}${RESET} gitfc --amend "new message" "2026-04-01"
  {DIM}${RESET} gitfc -a -v -p "my message" "+30m"
  {DIM}${RESET} gitfc --dry-run "my message" "2026-04-01 09:00:00"

{YELLOW}QUEUE{RESET}
  Batch-create commits locally and push them on a schedule.
  Use {GREEN}gitfc queue --help{RESET} for details, or {GREEN}gitfc q{RESET} as shorthand.
""")


def _print_queue_help():
    print(f"""
{BOLD}gitfc queue{RESET} — Manage the commit push queue.

  Commits are created immediately (locally), but the {BOLD}push{RESET} happens on a schedule.
  Shorthand: {GREEN}gitfc q{RESET} instead of {GREEN}gitfc queue{RESET}.

{YELLOW}COMMANDS{RESET}
  {GREEN}add{RESET} "msg" [date]       Add a commit to the queue {DIM}(default when no subcommand){RESET}
  {GREEN}list{RESET} | {GREEN}ls{RESET}              Show all queued items
  {GREEN}remove{RESET} | {GREEN}rm{RESET} <id>       Remove an item by ID
  {GREEN}clear{RESET}                  Remove all pending items
  {GREEN}run{RESET} <interval> [jitter] Schedule and push pending items
  {GREEN}stop{RESET}                   Stop the background daemon
  {GREEN}status{RESET}                 Show daemon and queue summary

{YELLOW}ADD OPTIONS{RESET}
  {GREEN}--amend{RESET}                Amend the previous commit

{YELLOW}RUN OPTIONS{RESET}
  {GREEN}<interval>{RESET}             Time between pushes: {CYAN}30m{RESET}, {CYAN}2h{RESET}, {CYAN}1d{RESET}
  {GREEN}[jitter]{RESET}               Random offset per push: {CYAN}5m{RESET}, {CYAN}10m{RESET}
  {GREEN}--at{RESET} <time>            When the first push happens {DIM}(default: now){RESET}
  {GREEN}--ids{RESET} <ids>            Comma-separated IDs in push order: {CYAN}2,1,3{RESET}
  {GREEN}--daemon{RESET}               Run in the background
  {GREEN}--poll{RESET} <sec>           Seconds between checks {DIM}(default: 60){RESET}

{YELLOW}EXAMPLES{RESET}
  {DIM}${RESET} gitfc queue "add user authentication"
  {DIM}${RESET} gitfc queue "add input validation" "-1h"
  {DIM}${RESET} gitfc queue list
  {DIM}${RESET} gitfc queue run 30m 5m
  {DIM}${RESET} gitfc queue run 30m 5m --at 14:00
  {DIM}${RESET} gitfc queue run 30m --ids 3,1,2
  {DIM}${RESET} gitfc queue run 30m 5m --daemon
  {DIM}${RESET} gitfc queue status
  {DIM}${RESET} gitfc queue stop
""")


def _build_queue_parser():
    parser = argparse.ArgumentParser(prog="gitfc queue", add_help=False)
    sub = parser.add_subparsers(dest="queue_action")

    # add (always stages all changes)
    add_p = sub.add_parser("add")
    add_p.add_argument("--amend", action="store_true")
    add_p.add_argument("message", nargs="?", default=None)
    add_p.add_argument("date", nargs="?", default=None)

    # list
    sub.add_parser("list", aliases=["ls"])

    # remove
    rm_p = sub.add_parser("remove", aliases=["rm"])
    rm_p.add_argument("id", type=int)

    # clear
    clear_p = sub.add_parser("clear")
    clear_p.add_argument("--force", action="store_true")

    # run
    run_p = sub.add_parser("run")
    run_p.add_argument("interval")
    run_p.add_argument("jitter", nargs="?", default=None)
    run_p.add_argument("--at")
    run_p.add_argument("--ids")
    run_p.add_argument("--daemon", action="store_true")
    run_p.add_argument("--poll", type=int, default=60)

    # stop / status
    sub.add_parser("stop")
    sub.add_parser("status")

    return parser


def main():
    if not is_git_repo():
        print("Error: not a git repository", file=sys.stderr)
        sys.exit(1)

    # route "queue" / "q" to the queue subsystem before argparse sees positional args
    if len(sys.argv) > 1 and sys.argv[1] in ("queue", "q"):
        queue_args = sys.argv[2:]

        if not queue_args or queue_args[0] in ("-h", "--help"):
            _print_queue_help()
            sys.exit(0)

        # shorthand: "gitfc queue 'msg'" -> "gitfc queue add 'msg'"
        if queue_args[0] not in QUEUE_SUBCOMMANDS:
            queue_args = ["add"] + queue_args
        queue_parser = _build_queue_parser()
        args = queue_parser.parse_args(queue_args)
        from fc_queue import handle_queue
        handle_queue(args)
        return

    # intercept --help / -h for custom output
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        _print_main_help()
        sys.exit(0)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-a", action="store_true")
    parser.add_argument("--amend", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-p", "--push", action="store_true")
    parser.add_argument("message", nargs="?", default=None)
    parser.add_argument("date", nargs="?", default=None)
    args = parser.parse_args()

    if not args.amend and not args.message:
        print(f"{BOLD}Error:{RESET} message is required (unless using --amend)", file=sys.stderr)
        print(f"Run {GREEN}gitfc --help{RESET} for usage.", file=sys.stderr)
        sys.exit(2)

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
