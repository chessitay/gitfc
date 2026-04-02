import os
import sqlite3
from datetime import datetime
from unittest.mock import patch, MagicMock, call

import pytest

from tests.conftest import make_args, insert_row, FakeDatetime


class TestGetDbPath:
    def test_returns_correct_path(self):
        mock_result = MagicMock(stdout="/repo/.git\n")
        with patch("gitfc.queue.subprocess.run", return_value=mock_result), \
             patch("gitfc.queue.os.makedirs"):
            from gitfc.queue import get_db_path
            assert get_db_path() == "/repo/.git/future-commit/queue.db"

    def test_creates_directory(self, tmp_path):
        git_dir = str(tmp_path / ".git")
        os.makedirs(git_dir, exist_ok=True)
        mock_result = MagicMock(stdout=git_dir + "\n")
        with patch("gitfc.queue.subprocess.run", return_value=mock_result):
            from gitfc.queue import get_db_path
            get_db_path()
            assert os.path.isdir(os.path.join(git_dir, "future-commit"))

    def test_existing_directory_no_error(self, tmp_path):
        git_dir = str(tmp_path / ".git")
        os.makedirs(os.path.join(git_dir, "future-commit"), exist_ok=True)
        mock_result = MagicMock(stdout=git_dir + "\n")
        with patch("gitfc.queue.subprocess.run", return_value=mock_result):
            from gitfc.queue import get_db_path
            result = get_db_path()
            assert result == os.path.join(git_dir, "future-commit", "queue.db")


class TestGetDb:
    def test_returns_connection_with_row_factory(self, tmp_path):
        db_path = str(tmp_path / "queue.db")
        with patch("gitfc.queue.get_db_path", return_value=db_path):
            from gitfc.queue import get_db
            conn = get_db()
            assert conn.row_factory is sqlite3.Row
            conn.close()

    def test_creates_queue_table(self, tmp_path):
        db_path = str(tmp_path / "queue.db")
        with patch("gitfc.queue.get_db_path", return_value=db_path):
            from gitfc.queue import get_db
            conn = get_db()
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='queue'"
            ).fetchall()
            assert len(tables) == 1

            cols = [row[1] for row in conn.execute("PRAGMA table_info(queue)").fetchall()]
            expected = [
                "id", "message", "commit_date", "push_at", "jitter_sec",
                "branch", "commit_hash", "status", "error", "created_at",
                "pushed_at", "stage_all", "amend",
            ]
            assert cols == expected
            conn.close()

    def test_enables_wal_mode(self, tmp_path):
        db_path = str(tmp_path / "queue.db")
        with patch("gitfc.queue.get_db_path", return_value=db_path):
            from gitfc.queue import get_db
            conn = get_db()
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            conn.close()


class TestQueueAdd:
    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value="a1b2c3d4e5f6a1b2c3d4")
    def test_success(self, mock_commit, mock_branch, mock_parse, mock_db, capsys):
        from gitfc.queue import queue_add
        args = make_args(message="my commit", date="+15m")
        queue_add(args)

        row = mock_db.execute("SELECT * FROM queue WHERE id = 1").fetchone()
        assert row["message"] == "my commit"
        assert row["commit_date"] == "2026-01-15 10:00:00"
        assert row["branch"] == "main"
        assert row["commit_hash"] == "a1b2c3d4e5f6a1b2c3d4"
        assert row["status"] == "committed"
        assert row["stage_all"] == 1
        assert row["amend"] == 0

        out = capsys.readouterr().out
        assert "Queued #1" in out

    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value="a1b2c3d4e5f6a1b2c3d4")
    def test_prints_short_hash(self, mock_commit, mock_branch, mock_parse, mock_db, capsys):
        from gitfc.queue import queue_add
        queue_add(make_args(message="test"))
        out = capsys.readouterr().out
        assert "a1b2c3d" in out

    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value="a1b2c3d4e5f6a1b2c3d4")
    def test_amend_without_message(self, mock_commit, mock_branch, mock_parse, mock_db, capsys):
        from gitfc.queue import queue_add
        args = make_args(message=None, amend=True)
        queue_add(args)

        row = mock_db.execute("SELECT * FROM queue WHERE id = 1").fetchone()
        assert row["message"] == "(amend)"
        assert row["amend"] == 1

    def test_no_message_no_amend_exits(self, mock_db, capsys):
        from gitfc.queue import queue_add
        args = make_args(message=None, amend=False)
        with pytest.raises(SystemExit) as exc_info:
            queue_add(args)
        assert exc_info.value.code == 1
        assert "message is required" in capsys.readouterr().err

    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value=None)
    def test_commit_fails_exits(self, mock_commit, mock_branch, mock_parse, mock_db, capsys):
        from gitfc.queue import queue_add
        with pytest.raises(SystemExit) as exc_info:
            queue_add(make_args())
        assert exc_info.value.code == 1
        assert "commit failed" in capsys.readouterr().err
        assert mock_db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0

    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value="abc123")
    def test_passes_correct_args_to_create_commit(self, mock_commit, mock_branch, mock_parse, mock_db):
        from gitfc.queue import queue_add
        args = make_args(message="hello", date="+1h", amend=True)
        queue_add(args)
        mock_commit.assert_called_once_with("hello", "2026-01-15 10:00:00", amend=True, stage_all=True)

    @patch("gitfc.queue.parse_date", return_value="2026-01-15 10:00:00")
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.create_commit", return_value="abc123")
    def test_date_is_parsed(self, mock_commit, mock_branch, mock_parse, mock_db):
        from gitfc.queue import queue_add
        queue_add(make_args(date="+2h"))
        mock_parse.assert_called_once_with("+2h")
        row = mock_db.execute("SELECT commit_date FROM queue WHERE id = 1").fetchone()
        assert row["commit_date"] == "2026-01-15 10:00:00"


class TestQueueList:
    def test_empty(self, mock_db, capsys):
        from gitfc.queue import queue_list
        queue_list(make_args())
        assert "Queue is empty." in capsys.readouterr().out

    def test_single_committed_item(self, mock_db, capsys):
        insert_row(mock_db, message="fix bug", status="committed")
        with patch("gitfc.queue.format_relative", return_value="in 2h"):
            from gitfc.queue import queue_list
            queue_list(make_args())
        out = capsys.readouterr().out
        assert "fix bug" in out
        assert "committed" in out
        assert "1 item(s) queued." in out

    def test_message_truncation(self, mock_db, capsys):
        long_msg = "A" * 50
        insert_row(mock_db, message=long_msg, status="committed")
        with patch("gitfc.queue.format_relative", return_value="in 2h"):
            from gitfc.queue import queue_list
            queue_list(make_args())
        out = capsys.readouterr().out
        assert "..." in out
        # The truncated message should not contain the full 50-char string
        assert long_msg not in out

    @patch("gitfc.queue.format_relative", return_value="in 2h")
    def test_push_at_display(self, mock_fmt, mock_db, capsys):
        insert_row(mock_db, push_at="2026-01-15 14:00:00")
        from gitfc.queue import queue_list
        queue_list(make_args())
        out = capsys.readouterr().out
        assert "2026-01-15 14:00" in out
        assert "in 2h" in out

    def test_mixed_statuses_ordering(self, mock_db, capsys):
        insert_row(mock_db, message="pushed one", status="pushed", created_at="2026-01-15 08:00:00")
        insert_row(mock_db, message="committed one", status="committed", created_at="2026-01-15 09:00:00")
        insert_row(mock_db, message="failed one", status="failed", created_at="2026-01-15 07:00:00")
        with patch("gitfc.queue.format_relative", return_value="in 2h"):
            from gitfc.queue import queue_list
            queue_list(make_args())
        out = capsys.readouterr().out
        lines = [l for l in out.split("\n") if l.strip() and not l.startswith("--") and not l.startswith("ID")]
        # Find lines containing the messages
        committed_line = next(i for i, l in enumerate(lines) if "committed one" in l)
        pushed_line = next(i for i, l in enumerate(lines) if "pushed one" in l)
        failed_line = next(i for i, l in enumerate(lines) if "failed one" in l)
        assert committed_line < pushed_line < failed_line
        assert "1 item(s) queued." in out

    def test_no_pending_items(self, mock_db, capsys):
        insert_row(mock_db, message="done", status="pushed")
        with patch("gitfc.queue.format_relative", return_value="2h ago"):
            from gitfc.queue import queue_list
            queue_list(make_args())
        out = capsys.readouterr().out
        assert "No pending items." in out


class TestQueueRemove:
    def test_success(self, mock_db, capsys):
        row_id = insert_row(mock_db, status="committed")
        from gitfc.queue import queue_remove
        queue_remove(make_args(id=row_id))
        assert mock_db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0
        assert "Removed item #" in capsys.readouterr().out

    def test_nonexistent_id_exits(self, mock_db, capsys):
        from gitfc.queue import queue_remove
        with pytest.raises(SystemExit) as exc_info:
            queue_remove(make_args(id=999))
        assert exc_info.value.code == 1
        assert "not found" in capsys.readouterr().err

    def test_pushed_item_exits(self, mock_db, capsys):
        row_id = insert_row(mock_db, status="pushed")
        from gitfc.queue import queue_remove
        with pytest.raises(SystemExit) as exc_info:
            queue_remove(make_args(id=row_id))
        assert exc_info.value.code == 1
        assert "already pushed" in capsys.readouterr().err

    def test_failed_item_succeeds(self, mock_db, capsys):
        row_id = insert_row(mock_db, status="failed")
        from gitfc.queue import queue_remove
        queue_remove(make_args(id=row_id))
        assert mock_db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 0


class TestQueueClear:
    def test_no_pending(self, mock_db, capsys):
        insert_row(mock_db, status="pushed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=True))
        out = capsys.readouterr().out
        assert "No pending items to clear." in out

    def test_with_force(self, mock_db, capsys):
        for _ in range(3):
            insert_row(mock_db, status="committed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=True))
        assert mock_db.execute("SELECT COUNT(*) FROM queue WHERE status='committed'").fetchone()[0] == 0
        assert "Cleared 3 item(s)" in capsys.readouterr().out

    @patch("builtins.input", return_value="y")
    def test_confirm_yes(self, mock_input, mock_db, capsys):
        insert_row(mock_db, status="committed")
        insert_row(mock_db, status="committed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=False))
        assert mock_db.execute("SELECT COUNT(*) FROM queue WHERE status='committed'").fetchone()[0] == 0
        mock_input.assert_called_once()
        assert "Cleared 2 item(s)" in capsys.readouterr().out

    @patch("builtins.input", return_value="n")
    def test_confirm_no(self, mock_input, mock_db, capsys):
        insert_row(mock_db, status="committed")
        insert_row(mock_db, status="committed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=False))
        assert mock_db.execute("SELECT COUNT(*) FROM queue WHERE status='committed'").fetchone()[0] == 2
        assert "Cancelled." in capsys.readouterr().out

    @patch("builtins.input", return_value="y")
    def test_preserves_pushed_items(self, mock_input, mock_db, capsys):
        insert_row(mock_db, status="committed")
        insert_row(mock_db, status="committed")
        pushed_id = insert_row(mock_db, status="pushed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=True))
        assert mock_db.execute("SELECT COUNT(*) FROM queue").fetchone()[0] == 1
        assert mock_db.execute("SELECT id FROM queue").fetchone()[0] == pushed_id

    @patch("builtins.input", return_value="y")
    def test_confirm_prompt_includes_count(self, mock_input, mock_db, capsys):
        for _ in range(5):
            insert_row(mock_db, status="committed")
        from gitfc.queue import queue_clear
        queue_clear(make_args(force=False))
        prompt_str = mock_input.call_args[0][0]
        assert "5" in prompt_str


class TestProcessDueItems:
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_no_items(self, mock_db):
        from gitfc.queue import process_due_items
        assert process_due_items() == 0

    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_no_due_items(self, mock_db):
        insert_row(mock_db, push_at="2026-01-15 14:00:00", status="committed")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0
        row = mock_db.execute("SELECT status FROM queue WHERE id = 1").fetchone()
        assert row["status"] == "committed"

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=0)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_pushes_due_item(self, mock_rand, mock_branch, mock_subprocess, mock_push, mock_db, capsys):
        insert_row(mock_db, push_at="2026-01-15 11:00:00", status="committed", branch="main")
        from gitfc.queue import process_due_items
        assert process_due_items() == 1
        row = mock_db.execute("SELECT status, pushed_at FROM queue WHERE id = 1").fetchone()
        assert row["status"] == "pushed"
        assert row["pushed_at"] is not None
        assert "done" in capsys.readouterr().out

    @patch("gitfc.queue.get_current_branch", return_value="develop")
    @patch("gitfc.queue.random.randint", return_value=0)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_branch_mismatch_fails_and_breaks(self, mock_rand, mock_branch, mock_db, capsys):
        insert_row(mock_db, push_at="2026-01-15 11:00:00", status="committed", branch="main")
        insert_row(mock_db, push_at="2026-01-15 11:30:00", status="committed", branch="main",
                   created_at="2026-01-15 09:30:00")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0
        row1 = mock_db.execute("SELECT status, error FROM queue WHERE id = 1").fetchone()
        assert row1["status"] == "failed"
        assert "Branch mismatch" in row1["error"]
        # Second item untouched because loop breaks
        row2 = mock_db.execute("SELECT status FROM queue WHERE id = 2").fetchone()
        assert row2["status"] == "committed"

    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=1))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=0)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_commit_not_found_fails(self, mock_rand, mock_branch, mock_subprocess, mock_db, capsys):
        insert_row(mock_db, push_at="2026-01-15 11:00:00", status="committed", branch="main")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0
        row = mock_db.execute("SELECT status, error FROM queue WHERE id = 1").fetchone()
        assert row["status"] == "failed"
        assert "no longer exists" in row["error"]

    @patch("gitfc.queue.do_push", return_value=1)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=0)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_push_fails(self, mock_rand, mock_branch, mock_subprocess, mock_push, mock_db, capsys):
        insert_row(mock_db, push_at="2026-01-15 11:00:00", status="committed", branch="main")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0
        row = mock_db.execute("SELECT status, error FROM queue WHERE id = 1").fetchone()
        assert row["status"] == "failed"
        assert "git push exited with code 1" in row["error"]
        assert "FAILED" in capsys.readouterr().out

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=0)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_multiple_items_pushed(self, mock_rand, mock_branch, mock_subprocess, mock_push, mock_db):
        for i in range(3):
            insert_row(mock_db, push_at=f"2026-01-15 {10 + i}:00:00", status="committed",
                       branch="main", created_at=f"2026-01-15 {8 + i:02d}:00:00")
        from gitfc.queue import process_due_items
        assert process_due_items() == 3
        for row in mock_db.execute("SELECT status FROM queue").fetchall():
            assert row["status"] == "pushed"

    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=31)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_jitter_delays_push(self, mock_rand, mock_branch, mock_db):
        # push_at 11:59:30 + jitter 31s = 12:00:01 > now (12:00:00) → skipped
        insert_row(mock_db, push_at="2026-01-15 11:59:30", jitter_sec=60,
                   status="committed", branch="main")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0
        row = mock_db.execute("SELECT status FROM queue WHERE id = 1").fetchone()
        assert row["status"] == "committed"

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.random.randint", return_value=-60)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_jitter_advances_push(self, mock_rand, mock_branch, mock_subprocess, mock_push, mock_db):
        # push_at 11:59:30 + jitter -60s = 11:58:30 < now (12:00:00) → pushed
        insert_row(mock_db, push_at="2026-01-15 11:59:30", jitter_sec=60,
                   status="committed", branch="main")
        from gitfc.queue import process_due_items
        assert process_due_items() == 1

    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_skips_items_without_push_at(self, mock_db):
        insert_row(mock_db, push_at=None, status="committed")
        from gitfc.queue import process_due_items
        assert process_due_items() == 0


class TestQueueRun:
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_no_pending_items(self, mock_db, capsys):
        from gitfc.queue import queue_run
        queue_run(make_args(ids=None))
        assert "No pending items to run." in capsys.readouterr().out

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.parse_duration", return_value=1800)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_schedules_all_items(self, mock_duration, mock_branch, mock_subproc, mock_push, mock_db, capsys):
        for i in range(3):
            insert_row(mock_db, status="committed", created_at=f"2026-01-15 {8 + i:02d}:00:00")
        from gitfc.queue import queue_run
        queue_run(make_args(ids=None, jitter=None, at=None))

        rows = mock_db.execute("SELECT push_at FROM queue ORDER BY id").fetchall()
        assert rows[0]["push_at"] == "2026-01-15 12:00:00"
        assert rows[1]["push_at"] == "2026-01-15 12:30:00"
        assert rows[2]["push_at"] == "2026-01-15 13:00:00"

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.parse_duration", side_effect=lambda v: {"30m": 1800, "5m": 300}[v])
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_with_jitter(self, mock_duration, mock_branch, mock_subproc, mock_push, mock_db):
        insert_row(mock_db, status="committed")
        from gitfc.queue import queue_run
        queue_run(make_args(jitter="5m", ids=None, at=None))
        row = mock_db.execute("SELECT jitter_sec FROM queue WHERE id = 1").fetchone()
        assert row["jitter_sec"] == 300

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.parse_duration", return_value=1800)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_with_ids_filter(self, mock_duration, mock_branch, mock_subproc, mock_push, mock_db):
        id1 = insert_row(mock_db, status="committed", created_at="2026-01-15 08:00:00")
        id2 = insert_row(mock_db, status="committed", created_at="2026-01-15 09:00:00")
        id3 = insert_row(mock_db, status="committed", created_at="2026-01-15 10:00:00")
        from gitfc.queue import queue_run
        queue_run(make_args(ids=f"{id3},{id1}", jitter=None, at=None))

        row3 = mock_db.execute("SELECT push_at FROM queue WHERE id = ?", (id3,)).fetchone()
        row1 = mock_db.execute("SELECT push_at FROM queue WHERE id = ?", (id1,)).fetchone()
        row2 = mock_db.execute("SELECT push_at FROM queue WHERE id = ?", (id2,)).fetchone()
        assert row3["push_at"] == "2026-01-15 12:00:00"  # first in specified order
        assert row1["push_at"] == "2026-01-15 12:30:00"  # second
        assert row2["push_at"] is None  # not included

    @patch("gitfc.queue.parse_duration", return_value=1800)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_invalid_id_exits(self, mock_duration, mock_db, capsys):
        from gitfc.queue import queue_run
        with pytest.raises(SystemExit) as exc_info:
            queue_run(make_args(ids="999"))
        assert exc_info.value.code == 1
        assert "not found or not pending" in capsys.readouterr().err

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.parse_date", return_value="2026-01-15 14:00:00")
    @patch("gitfc.queue.parse_duration", return_value=1800)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_with_at_flag(self, mock_duration, mock_parse, mock_branch, mock_subproc, mock_push, mock_db):
        insert_row(mock_db, status="committed")
        from gitfc.queue import queue_run
        queue_run(make_args(at="14:00", ids=None, jitter=None))
        row = mock_db.execute("SELECT push_at FROM queue WHERE id = 1").fetchone()
        assert row["push_at"] == "2026-01-15 14:00:00"

    @patch("gitfc.queue.do_push", return_value=0)
    @patch("gitfc.queue.subprocess.run", return_value=MagicMock(returncode=0))
    @patch("gitfc.queue.get_current_branch", return_value="main")
    @patch("gitfc.queue.parse_duration", return_value=1800)
    @patch("gitfc.queue.datetime", FakeDatetime)
    def test_prints_schedule_summary(self, mock_duration, mock_branch, mock_subproc, mock_push, mock_db, capsys):
        insert_row(mock_db, status="committed")
        insert_row(mock_db, status="committed", created_at="2026-01-15 09:30:00")
        from gitfc.queue import queue_run
        queue_run(make_args(ids=None, jitter=None, at=None))
        out = capsys.readouterr().out
        assert "Timestamps:" in out
        assert "12:00" in out
        assert "12:30" in out
        assert "30m apart" in out


class TestHandleQueue:
    @patch("gitfc.queue.queue_add")
    def test_dispatches_add(self, mock_fn, mock_db):
        from gitfc.queue import handle_queue
        args = make_args(queue_action="add")
        handle_queue(args)
        mock_fn.assert_called_once_with(args)

    @patch("gitfc.queue.queue_list")
    def test_dispatches_list(self, mock_fn, mock_db):
        from gitfc.queue import handle_queue
        args = make_args(queue_action="list")
        handle_queue(args)
        mock_fn.assert_called_once_with(args)

    @patch("gitfc.queue.queue_list")
    def test_alias_ls(self, mock_fn, mock_db):
        from gitfc.queue import handle_queue
        args = make_args(queue_action="ls")
        handle_queue(args)
        mock_fn.assert_called_once_with(args)

    @patch("gitfc.queue.queue_remove")
    def test_alias_rm(self, mock_fn, mock_db):
        from gitfc.queue import handle_queue
        args = make_args(queue_action="rm")
        handle_queue(args)
        mock_fn.assert_called_once_with(args)

    def test_none_action_exits(self, mock_db, capsys):
        from gitfc.queue import handle_queue
        with pytest.raises(SystemExit) as exc_info:
            handle_queue(make_args(queue_action=None))
        assert exc_info.value.code == 1
        assert "Usage:" in capsys.readouterr().err

    def test_unknown_action_exits(self, mock_db, capsys):
        from gitfc.queue import handle_queue
        with pytest.raises(SystemExit) as exc_info:
            handle_queue(make_args(queue_action="bogus"))
        assert exc_info.value.code == 1
        assert "Unknown queue action" in capsys.readouterr().err
