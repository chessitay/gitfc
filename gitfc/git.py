import os
import subprocess


def is_git_repo():
    result = subprocess.run(["git", "rev-parse", "--git-dir"], capture_output=True)
    return result.returncode == 0


def get_current_branch():
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def create_commit(message, date, amend=False, stage_all=False):
    if stage_all:
        subprocess.run(["git", "add", "-A"])

    # we need to set both author and committer dates
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

    hash_result = subprocess.run(
        ["git", "log", "-1", "--format=%H"],
        capture_output=True, text=True,
    )
    return hash_result.stdout.strip()


def do_push():
    result = subprocess.run(["git", "push"])
    return result.returncode
