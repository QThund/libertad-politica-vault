"""
Stage all changes, commit, and push to the remote repository.

Usage:
    python git_push.py "commit message"
    python git_push.py          # uses a default message
"""

import argparse
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402
from git_checks import check_ready  # noqa: E402

log = get_logger()

REPO_ROOT = _HERE.parent


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=check)


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage all, commit, and push.")
    parser.add_argument("message", nargs="?", default="Update", help="Commit message")
    args = parser.parse_args()
    check_ready()

    # Check if there is anything to commit
    status = run(["git", "status", "--porcelain"])
    if not status.stdout.strip():
        log.trace("Nothing to commit, working tree clean.")
        push = run(["git", "push"], check=False)
        if push.returncode != 0:
            log.error("Push failed:")
            if push.stderr.strip():
                log.error(push.stderr.strip())
            sys.exit(push.returncode)
        log.trace(push.stdout.strip() or "Already up to date with remote.")
        return

    log.trace("Staging all changes...")
    run(["git", "add", "--all"])

    log.trace(f"Committing: {args.message!r}")
    commit = run(["git", "commit", "-m", args.message], check=False)
    if commit.returncode != 0:
        log.error("Commit failed:")
        if commit.stderr.strip():
            log.error(commit.stderr.strip())
        sys.exit(commit.returncode)
    if commit.stdout.strip():
        log.trace(commit.stdout.strip())

    log.trace("Pushing...")
    push = run(["git", "push"], check=False)
    if push.returncode != 0:
        log.error("Push failed:")
        if push.stderr.strip():
            log.error(push.stderr.strip())
        sys.exit(push.returncode)
    log.trace(push.stdout.strip() or "Push successful.")


if __name__ == "__main__":
    main()
