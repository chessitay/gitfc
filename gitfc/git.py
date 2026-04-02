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


def rewrite_commit_date(commit_hash, new_date, parent_remap=None):
    """Rewrite a commit with a new date, remapping parents if needed.
    Returns the new commit hash."""
    # get tree and parents from the original commit
    result = subprocess.run(
        ["git", "cat-file", "-p", commit_hash],
        capture_output=True, text=True,
    )
    tree = None
    parents = []
    for line in result.stdout.split("\n"):
        if line.startswith("tree "):
            tree = line.split()[1]
        elif line.startswith("parent "):
            parents.append(line.split()[1])
        elif line == "":
            break

    # get the original commit message
    msg_result = subprocess.run(
        ["git", "log", "-1", "--format=%B", commit_hash],
        capture_output=True, text=True,
    )
    message = msg_result.stdout.rstrip("\n")

    # remap parents if any were rewritten earlier in the chain
    if parent_remap:
        parents = [parent_remap.get(p, p) for p in parents]

    env = os.environ.copy()
    env["GIT_AUTHOR_DATE"] = new_date
    env["GIT_COMMITTER_DATE"] = new_date

    cmd = ["git", "commit-tree", tree]
    for p in parents:
        cmd += ["-p", p]
    cmd += ["-m", message]

    new = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return new.stdout.strip()


def do_push(commit_hash=None, branch=None):
    if commit_hash and branch:
        result = subprocess.run(["git", "push", "origin", f"{commit_hash}:refs/heads/{branch}"])
    else:
        result = subprocess.run(["git", "push"])
    return result.returncode
