

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
GREEN = "\033[32m"

QUEUE_SUBCOMMANDS = {"add", "list", "ls", "remove", "rm", "clear", "run", "stop", "status"}


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
