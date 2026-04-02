import os
import random
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta

from gitfc.git import create_commit, do_push, get_current_branch, rewrite_commit_date
from gitfc.dates import parse_date, parse_duration, format_relative
from gitfc.help import DIM, RESET


def get_db_path():
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True, text=True,
    )
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
        "SELECT * FROM queue ORDER BY CASE status "
        "WHEN 'committed' THEN 0 WHEN 'pushed' THEN 1 WHEN 'failed' THEN 2 END, created_at"
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

        line = f"{r['id']:>{id_w}}  {msg:<35} {r['commit_date'][:16]:<20} {push_display:<28} {status:<10}"
        if status in ("pushed", "failed"):
            print(f"{DIM}{line}{RESET}")
        else:
            print(line)

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
    count = conn.execute(
        "SELECT COUNT(*) FROM queue WHERE status IN ('committed')"
    ).fetchone()[0]

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
    conn = get_db()
    now = datetime.now()

    rows = conn.execute(
        "SELECT * FROM queue WHERE status = 'committed' AND push_at IS NOT NULL "
        "ORDER BY push_at ASC"
    ).fetchall()

    pushed = 0
    for r in rows:
        push_dt = datetime.strptime(r["push_at"], "%Y-%m-%d %H:%M:%S")

        if r["jitter_sec"]:
            jitter = random.randint(-r["jitter_sec"], r["jitter_sec"])
            push_dt = push_dt + timedelta(seconds=jitter)

        if push_dt > now:
            continue

        current_branch = get_current_branch()
        if current_branch != r["branch"]:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Branch mismatch: expected '{r['branch']}', on '{current_branch}'", r["id"]),
            )
            conn.commit()
            print(f"[{now.strftime('%H:%M:%S')}] #{r['id']} FAILED: branch mismatch ({r['branch']} != {current_branch})")
            break

        check = subprocess.run(
            ["git", "cat-file", "-t", r["commit_hash"]],
            capture_output=True,
        )
        if check.returncode != 0:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Commit {r['commit_hash'][:7]} no longer exists", r["id"]),
            )
            conn.commit()
            print(f"[{now.strftime('%H:%M:%S')}] #{r['id']} FAILED: commit {r['commit_hash'][:7]} not found")
            break

        timestamp = datetime.now().strftime("%H:%M:%S")
        msg_short = r["message"][:40]
        print(f'[{timestamp}] Pushing #{r["id"]} "{msg_short}" ({r["commit_hash"][:7]})...', end=" ", flush=True)

        rc = do_push(commit_hash=r["commit_hash"], branch=r["branch"])
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

    if args.ids:
        id_list = [int(x.strip()) for x in args.ids.split(",")]
        rows = []
        for item_id in id_list:
            row = conn.execute(
                "SELECT * FROM queue WHERE id = ? AND status = 'committed'",
                (item_id,),
            ).fetchone()
            if not row:
                print(f"Error: item #{item_id} not found or not pending", file=sys.stderr)
                conn.close()
                sys.exit(1)
            rows.append(row)
    else:
        rows = conn.execute(
            "SELECT * FROM queue WHERE status = 'committed' ORDER BY created_at ASC"
        ).fetchall()

    if not rows:
        print("No pending items to run.")
        conn.close()
        return

    # Store push_at timestamps as metadata
    if args.interval:
        interval_sec = parse_duration(args.interval)
        jitter_sec = parse_duration(args.jitter) if args.jitter else 0

        if args.at:
            start = datetime.strptime(parse_date(args.at), "%Y-%m-%d %H:%M:%S")
        else:
            start = datetime.now()

        for i, row in enumerate(rows):
            push_at = start + timedelta(seconds=interval_sec * i)
            if jitter_sec:
                jitter = random.randint(-jitter_sec, jitter_sec)
                push_at = push_at + timedelta(seconds=jitter)
            conn.execute(
                "UPDATE queue SET push_at = ?, jitter_sec = ? WHERE id = ?",
                (push_at.strftime("%Y-%m-%d %H:%M:%S"), jitter_sec, row["id"]),
            )
        conn.commit()

        last_push = start + timedelta(seconds=interval_sec * (len(rows) - 1))
        jitter_str = f" +/-{args.jitter} jitter" if args.jitter else ""
        print(f"Timestamps: {start.strftime('%H:%M')} to {last_push.strftime('%H:%M')}, {args.interval} apart{jitter_str}.")
    else:
        now = datetime.now()
        for row in rows:
            conn.execute(
                "UPDATE queue SET push_at = ? WHERE id = ?",
                (now.strftime("%Y-%m-%d %H:%M:%S"), row["id"]),
            )
        conn.commit()

    # Rewrite commit dates to match push_at schedule
    if args.interval:
        hash_remap = {}
        for row in rows:
            item = conn.execute("SELECT * FROM queue WHERE id = ?", (row["id"],)).fetchone()
            new_hash = rewrite_commit_date(
                item["commit_hash"], item["push_at"], parent_remap=hash_remap
            )
            hash_remap[item["commit_hash"]] = new_hash
            conn.execute(
                "UPDATE queue SET commit_hash = ?, commit_date = ? WHERE id = ?",
                (new_hash, item["push_at"], item["id"]),
            )
        conn.commit()

        # update branch to point to the last rewritten commit
        last_old = rows[-1]["commit_hash"]
        last_new = hash_remap[last_old]
        branch = rows[-1]["branch"]
        subprocess.run(["git", "update-ref", f"refs/heads/{branch}", last_new])

        # re-fetch rows with updated hashes
        if args.ids:
            id_list = [int(x.strip()) for x in args.ids.split(",")]
            rows = [conn.execute("SELECT * FROM queue WHERE id = ?", (i,)).fetchone() for i in id_list]
        else:
            rows = conn.execute(
                "SELECT * FROM queue WHERE status = 'committed' ORDER BY created_at ASC"
            ).fetchall()

    # Push all items immediately
    current_branch = get_current_branch()
    pushed = 0
    for r in rows:
        item = conn.execute("SELECT * FROM queue WHERE id = ?", (r["id"],)).fetchone()

        if current_branch != item["branch"]:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Branch mismatch: expected '{item['branch']}', on '{current_branch}'", item["id"]),
            )
            conn.commit()
            print(f"#{item['id']} FAILED: branch mismatch ({item['branch']} != {current_branch})")
            break

        check = subprocess.run(
            ["git", "cat-file", "-t", item["commit_hash"]],
            capture_output=True,
        )
        if check.returncode != 0:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"Commit {item['commit_hash'][:7]} no longer exists", item["id"]),
            )
            conn.commit()
            print(f"#{item['id']} FAILED: commit {item['commit_hash'][:7]} not found")
            break

        msg_short = item["message"][:40]
        print(f'Pushing #{item["id"]} "{msg_short}" ({item["commit_hash"][:7]})...', end=" ", flush=True)

        rc = do_push(commit_hash=item["commit_hash"], branch=item["branch"])
        if rc != 0:
            conn.execute(
                "UPDATE queue SET status = 'failed', error = ? WHERE id = ?",
                (f"git push exited with code {rc}", item["id"]),
            )
            conn.commit()
            print("FAILED")
            break

        conn.execute(
            "UPDATE queue SET status = 'pushed', pushed_at = ? WHERE id = ?",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), item["id"]),
        )
        conn.commit()
        pushed += 1
        print("done")

    conn.close()

    if pushed == len(rows):
        print(f"\nAll {pushed} item(s) pushed.")
    else:
        print(f"\n{pushed}/{len(rows)} item(s) pushed.")


def handle_queue(args):
    action = args.queue_action
    if action is None:
        print("Usage: gitfc queue <add|list|remove|clear|run|stop|status>", file=sys.stderr)
        sys.exit(1)

    from gitfc.daemon import queue_stop, queue_status

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
