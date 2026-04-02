import os
import random
import re
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta

from main import create_commit, do_push, get_current_branch, parse_date


def get_db_path():
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    git_dir = result.stdout.strip()
    fc_dir = os.path.join(git_dir, "future-commit")
    os.makedirs(fc_dir, exist_ok=True)
    return os.path.join(fc_dir, "queue.db")


def get_db():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            message     TEXT NOT NULL,
            commit_date TEXT NOT NULL,
            push_at     TEXT,
            jitter_sec  INTEGER DEFAULT 0,
            branch      TEXT NOT NULL,
            commit_hash TEXT,
            status      TEXT DEFAULT 'committed',
            error       TEXT,
            created_at  TEXT NOT NULL,
            pushed_at   TEXT,
            stage_all   INTEGER DEFAULT 0,
            amend       INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def parse_duration(value):
    """Convert '10m', '2h', '1d' to seconds."""
    match = re.fullmatch(r"(\d+)([mhd])", value)
    if not match:
        print(f'Error: invalid duration "{value}"', file=sys.stderr)
        print('Expected: "10m", "2h", "1d"', file=sys.stderr)
        sys.exit(1)
    amount = int(match.group(1))
    unit = match.group(2)
    return {"m": 60, "h": 3600, "d": 86400}[unit] * amount


def format_relative(dt_str):
    """Format a datetime string as relative time ('in 45m', '3m ago')."""
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    diff = dt - datetime.now()
    total_sec = int(diff.total_seconds())

    if abs(total_sec) < 60:
        return "now"

    future = total_sec > 0
    total_sec = abs(total_sec)

    if total_sec < 3600:
        val = total_sec // 60
        unit = "m"
    elif total_sec < 86400:
        val = total_sec // 3600
        unit = "h"
    else:
        val = total_sec // 86400
        unit = "d"

    return f"in {val}{unit}" if future else f"{val}{unit} ago"


def get_pid_path():
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True, text=True)
    return os.path.join(result.stdout.strip(), "future-commit", "daemon.pid")


def is_daemon_running():
    pid_path = get_pid_path()
    if not os.path.exists(pid_path):
        return False, None
    with open(pid_path) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 0)
        return True, pid
    except (OSError, ProcessLookupError):
        os.remove(pid_path)
        return False, None


def queue_add(args):
    conn = get_db()

    if not args.amend and not args.message:
        print("Error: message is required (unless using --amend)", file=sys.stderr)
        sys.exit(1)

    date = parse_date(args.date)
    branch = get_current_branch()

    commit_hash = create_commit(args.message, date, amend=args.amend, stage_all=True)
    if not commit_hash:
        print("Error: commit failed", file=sys.stderr)
        sys.exit(1)

    display_msg = args.message or "(amend)"
    conn.execute(
        """INSERT INTO queue (message, commit_date, branch, commit_hash, status, created_at, stage_all, amend)
           VALUES (?, ?, ?, ?, 'committed', ?, ?, ?)""",
        (
            display_msg,
            date,
            branch,
            commit_hash,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            1,
            int(args.amend),
        ),
    )
    conn.commit()
    item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()

    print(f'Queued #{item_id}: {commit_hash[:7]} "{display_msg}"  (dated {date})')


def queue_list(args):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM queue ORDER BY CASE status WHEN 'committed' THEN 0 WHEN 'pushed' THEN 1 WHEN 'failed' THEN 2 END, created_at"
    ).fetchall()
    conn.close()

    if not rows:
        print("Queue is empty.")
        return

    id_w = max(len(str(r["id"])) for r in rows)
    id_w = max(id_w, 2)

    print(f"{'ID':>{id_w}}  {'Message':<35} {'Commit Date':<20} {'Push At':<28} {'Status':<10}")
    print(f"{'--':>{id_w}}  {'-------':<35} {'-----------':<20} {'-------':<28} {'------':<10}")

    pending_count = 0
    for r in rows:
        msg = r["message"]
        if len(msg) > 33:
            msg = msg[:32] + "..."

        if r["push_at"]:
            rel = format_relative(r["push_at"])
            push_display = f"{r['push_at'][:16]} ({rel})"
        else:
            push_display = "-"

        status = r["status"]
        if status == "committed":
            pending_count += 1

        print(f"{r['id']:>{id_w}}  {msg:<35} {r['commit_date'][:16]:<20} {push_display:<28} {status:<10}")

    print()
    if pending_count:
        print(f"{pending_count} item(s) queued.")
    else:
        print("No pending items.")


def queue_remove(args):
    conn = get_db()
    row = conn.execute("SELECT status FROM queue WHERE id = ?", (args.id,)).fetchone()
    if not row:
        print(f"Error: item #{args.id} not found", file=sys.stderr)
        sys.exit(1)
    if row["status"] == "pushed":
        print(f"Error: item #{args.id} already pushed", file=sys.stderr)
        sys.exit(1)

    conn.execute("DELETE FROM queue WHERE id = ?", (args.id,))
    conn.commit()
    conn.close()
    print(f"Removed item #{args.id} from queue.")


def queue_clear(args):
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM queue WHERE status IN ('committed')").fetchone()[0]

    if count == 0:
        print("No pending items to clear.")
        conn.close()
        return

    if not args.force:
        answer = input(f"Remove {count} pending item(s) from queue? [y/N] ")
        if answer.lower() != "y":
            print("Cancelled.")
            conn.close()
            return

    conn.execute("DELETE FROM queue WHERE status IN ('committed')")
    conn.commit()
    conn.close()
    print(f"Cleared {count} item(s) from queue.")


def process_due_items():
    """Process all due items. Returns number of items pushed."""
    conn = get_db()
    now = datetime.now()

    rows = conn.execute(
        "SELECT * FROM queue WHERE status = 'committed' AND push_at IS NOT NULL ORDER BY push_at ASC"
    ).fetchall()

    pushed = 0
    for r in rows:
        push_dt = datetime.strptime(r["push_at"], "%Y-%m-%d %H:%M:%S")

        # apply jitter
        if r["jitter_sec"]:
            jitter = random.randint(-r["jitter_sec"], r["jitter_sec"])
            push_dt = push_dt + timedelta(seconds=jitter)

        if push_dt > now:
            continue

        # safety: verify branch
        current_branch = get_current_branch()
        if current_branch != r["branch"]:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Branch mismatch: expected '{r['branch']}', on '{current_branch}'", r["id"]),
            )
            conn.commit()
            print(f"[{now.strftime('%H:%M:%S')}] #{r['id']} FAILED: branch mismatch ({r['branch']} != {current_branch})")
            break

        # safety: verify commit exists
        check = subprocess.run(["git", "cat-file", "-t", r["commit_hash"]], capture_output=True)
        if check.returncode != 0:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Commit {r['commit_hash'][:7]} no longer exists", r["id"]),
            )
            conn.commit()
            print(f"[{now.strftime('%H:%M:%S')}] #{r['id']} FAILED: commit {r['commit_hash'][:7]} not found")
            break

        # push
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_short = r["message"][:40]
        print(f'[{timestamp}] Pushing #{r["id"]} "{msg_short}" ({r["commit_hash"][:7]})...', end=" ", flush=True)

        rc = do_push()
        if rc != 0:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"git push exited with code {rc}", r["id"]),
            )
            conn.commit()
            print("FAILED")
            break

        conn.execute(
            "UPDATE queue SET status = 'pushed', pushed_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), r["id"]),
        )
        conn.commit()
        pushed += 1
        print("done")

    conn.close()
    return pushed


def queue_run(args):
    conn = get_db()

    # determine item order
    if args.ids:
        id_list = [int(x.strip()) for x in args.ids.split(",")]
        rows = []
        for item_id in id_list:
            row = conn.execute("SELECT id FROM queue WHERE id = ? AND status = 'committed'", (item_id,)).fetchone()
            if not row:
                print(f"Error: item #{item_id} not found or not pending", file=sys.stderr)
                conn.close()
                sys.exit(1)
            rows.append(row)
    else:
        rows = conn.execute(
            "SELECT id FROM queue WHERE status = 'committed' ORDER BY created_at ASC"
        ).fetchall()

    if not rows:
        print("No pending items to run.")
        conn.close()
        return

    # schedule push times
    interval_sec = parse_duration(args.interval)
    jitter_sec = parse_duration(args.jitter) if args.jitter else 0

    if args.at:
        start = datetime.strptime(parse_date(args.at), "%Y-%m-%d %H:%M:%S")
    else:
        start = datetime.now()

    for i, row in enumerate(rows):
        push_at = start + timedelta(seconds=interval_sec * i)
        conn.execute(
            "UPDATE queue SET push_at = ?, jitter_sec = ? WHERE id = ?",
            (push_at.strftime("%Y-%m-%d %H:%M:%S"), jitter_sec, row["id"]),
        )

    conn.commit()
    conn.close()

    last_push = start + timedelta(seconds=interval_sec * (len(rows) - 1))
    jitter_str = f" +/-{args.jitter} jitter" if args.jitter else ""
    print(f"Scheduled {len(rows)} item(s) from {start.strftime('%H:%M')} to {last_push.strftime('%H:%M')}, {args.interval} apart{jitter_str}.")
    print()

    # start processing
    if args.daemon:
        _start_daemon(args.poll)
    else:
        _run_watch(args.poll)


def _run_watch(poll_interval):
    """Foreground poll loop."""
    stop = [False]

    def on_signal(sig, frame):
        stop[0] = True
        print("\nStopping...")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    print(f"Watching queue (checking every {poll_interval}s). Ctrl+C to stop.")
    while not stop[0]:
        process_due_items()

        conn = get_db()
        pending = conn.execute("SELECT COUNT(*) FROM queue WHERE status = 'committed' AND push_at IS NOT NULL").fetchone()[0]
        conn.close()

        if pending == 0:
            print("Queue empty. Stopping.")
            break

        for _ in range(poll_interval):
            if stop[0]:
                break
            time.sleep(1)

    pid_path = get_pid_path()
    if os.path.exists(pid_path):
        os.remove(pid_path)


def _start_daemon(poll_interval):
    """Fork to background."""
    pid_path = get_pid_path()

    running, pid = is_daemon_running()
    if running:
        print(f"Daemon already running (PID {pid}).")
        return

    cmd = [sys.executable, "-c",
           f"from fc_queue import _run_watch; _run_watch({poll_interval})"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    with open(pid_path, "w") as f:
        f.write(str(proc.pid))

    print(f"Daemon started (PID {proc.pid}). Checking every {poll_interval}s.")
    print("Stop with: gitfc queue stop")


def queue_stop(args):
    running, pid = is_daemon_running()
    if not running:
        print("No daemon running.")
        return

    os.kill(pid, signal.SIGTERM)
    pid_path = get_pid_path()
    if os.path.exists(pid_path):
        os.remove(pid_path)
    print(f"Daemon stopped (PID {pid}).")


def queue_status(args):
    running, pid = is_daemon_running()
    if running:
        print(f"Daemon: running (PID {pid})")
    else:
        print("Daemon: not running")

    conn = get_db()
    counts = {}
    for status in ("committed", "pushed", "failed"):
        counts[status] = conn.execute("SELECT COUNT(*) FROM queue WHERE status = ?", (status,)).fetchone()[0]
    conn.close()

    print(f"Pending: {counts['committed']}  Pushed: {counts['pushed']}  Failed: {counts['failed']}")


def handle_queue(args):
    action = args.queue_action
    if action is None:
        print("Usage: gitfc queue <add|list|remove|clear|run|stop|status>", file=sys.stderr)
        sys.exit(1)

    dispatch = {
        "add": queue_add,
        "list": queue_list,
        "ls": queue_list,
        "remove": queue_remove,
        "rm": queue_remove,
        "clear": queue_clear,
        "run": queue_run,
        "stop": queue_stop,
        "status": queue_status,
    }

    fn = dispatch.get(action)
    if fn:
        fn(args)
    else:
        print(f'Unknown queue action: "{action}"', file=sys.stderr)
        sys.exit(1)
