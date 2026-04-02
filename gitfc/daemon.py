import os
import signal
import subprocess
import sys
import time
from datetime import datetime

from gitfc.queue import get_db, process_due_items


def get_pid_path():
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True, text=True,
    )
    return os.path.join(result.stdout.strip(), "future-commit", "daemon.pid")


def is_daemon_running():
    pid_path = get_pid_path()
    if not os.path.exists(pid_path):
        return False, None
    with open(pid_path) as f:
        pid = int(f.read().strip())
    try:
        os.kill(pid, 0)  # doesn't actually kill - just checks if it's alive
        return True, pid
    except (OSError, ProcessLookupError):
        os.remove(pid_path)  # stale pid file, clean it up
        return False, None


def run_watch(poll_interval):
    stop = [False]

    def on_signal(sig, frame):
        stop[0] = True
        print("\nStopping...")

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    print(f"Watching queue (checking every {poll_interval}s). Ctrl+C to stop.")
    while not stop[0]:
        process_due_items()

        # check if theres anything left to do
        conn = get_db()
        pending = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status = 'committed' AND push_at IS NOT NULL"
        ).fetchone()[0]
        conn.close()

        if pending == 0:
            print("Queue empty. Stopping.")
            break

        # sleep in 1s chunks so we can respond to signals quickly
        for _ in range(poll_interval):
            if stop[0]:
                break
            time.sleep(1)

    pid_path = get_pid_path()
    if os.path.exists(pid_path):
        os.remove(pid_path)


def start_daemon(poll_interval):
    pid_path = get_pid_path()

    running, pid = is_daemon_running()
    if running:
        print(f"Daemon already running (PID {pid}).")
        return

    cmd = [
        sys.executable, "-c",
        f"from gitfc.daemon import run_watch; run_watch({poll_interval})",
    ]
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


# kill the background daemon
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
        counts[status] = conn.execute(
            "SELECT COUNT(*) FROM queue WHERE status = ?", (status,)
        ).fetchone()[0]
    conn.close()

    print(f"Pending: {counts['committed']}  Pushed: {counts['pushed']}  Failed: {counts['failed']}")
