"""
Pull from the remote git repository.
If there are merge conflicts, copies each conflicted file's local version
to <repo_root>/conflicts/ and accepts the incoming (remote) changes.

Usage:
    python git_pull.py
"""

import shutil
import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402

log = get_logger()

REPO_ROOT = _HERE.parent
CONFLICTS_DIR = REPO_ROOT / "conflicts"


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=check)


def get_conflicted_files() -> list[Path]:
    result = run(["git", "diff", "--name-only", "--diff-filter=U"])
    return [REPO_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]


def save_local_copy(path: Path) -> None:
    CONFLICTS_DIR.mkdir(exist_ok=True)
    relative = path.relative_to(REPO_ROOT)
    dest = CONFLICTS_DIR / str(relative).replace("/", "_").replace("\\", "_")
    shutil.copy2(path, dest)
    log.trace(f"  Saved local copy: {dest.relative_to(REPO_ROOT)}")


def resolve_with_theirs(path: Path) -> None:
    rel = path.relative_to(REPO_ROOT).as_posix()
    run(["git", "checkout", "--theirs", rel])
    run(["git", "add", rel])
    log.trace(f"  Accepted remote version: {rel}")


def main() -> None:
    log.trace("Pulling from remote...")
    result = run(["git", "pull"], check=False)

    if result.returncode == 0:
        log.trace(result.stdout.strip() or "Already up to date.")
        return

    # Check whether the failure is due to merge conflicts
    conflicted = get_conflicted_files()
    if not conflicted:
        log.error("Pull failed (non-conflict error):")
        if result.stderr.strip():
            log.error(result.stderr.strip())
        sys.exit(result.returncode)

    log.warning(f"Merge conflicts detected in {len(conflicted)} file(s). Resolving...")
    for path in conflicted:
        save_local_copy(path)
        resolve_with_theirs(path)

    # Finalize the merge
    commit_result = run(["git", "commit", "--no-edit"], check=False)
    if commit_result.returncode != 0:
        log.error("Failed to finalize merge:")
        if commit_result.stderr.strip():
            log.error(commit_result.stderr.strip())
        sys.exit(commit_result.returncode)

    log.trace("Merge completed. Remote changes accepted; local copies saved to conflicts/")


if __name__ == "__main__":
    main()
