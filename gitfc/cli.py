import argparse
import subprocess
import sys

from gitfc.git import is_git_repo, create_commit, do_push
from gitfc.dates import parse_date
from gitfc.help import (
    _print_main_help, _print_queue_help,
    QUEUE_SUBCOMMANDS, BOLD, RESET, GREEN
)

def _build_queue_parser():
    parser = argparse.ArgumentParser(prog="gitfc queue", add_help=False)
    sub = parser.add_subparsers(dest="queue_action")

    add_p = sub.add_parser("add")
    add_p.add_argument("--amend", action="store_true")
    add_p.add_argument("message", nargs="?", default=None)
    add_p.add_argument("date", nargs="?", default=None)

    sub.add_parser("list", aliases=["ls"])

    rm_p = sub.add_parser("remove", aliases=["rm"])
    rm_p.add_argument("id", type=int)

    clear_p = sub.add_parser("clear")
    clear_p.add_argument("--force", action="store_true")

    run_p = sub.add_parser("run")
    run_p.add_argument("interval", nargs="?", default=None)
    run_p.add_argument("jitter", nargs="?", default=None)
    run_p.add_argument("--at")
    run_p.add_argument("--ids")

    sub.add_parser("stop")
    sub.add_parser("status")

    return parser


def main():
    if not is_git_repo():
        print("Error: not a git repository", file=sys.stderr)
        sys.exit(1)

    # "queue" and "q" get routed to the queue subsystem
    if len(sys.argv) > 1 and sys.argv[1] in ("queue", "q"):
        queue_args = sys.argv[2:]

        if not queue_args or queue_args[0] in ("-h", "--help"):
            _print_queue_help()
            sys.exit(0)

        if queue_args[0] not in QUEUE_SUBCOMMANDS:
            queue_args = ["add"] + queue_args

        queue_parser = _build_queue_parser()
        args = queue_parser.parse_args(queue_args)

        from gitfc.queue import handle_queue
        handle_queue(args)
        return

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
