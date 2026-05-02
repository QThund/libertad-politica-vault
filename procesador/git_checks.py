"""
Pre-flight git/GitHub checks shared across all entry-point scripts.

Call check_ready() at the top of any script that touches the repository
or the network, before doing any real work.
"""

import subprocess
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402

REPO_ROOT = _HERE.parent
log = get_logger()


def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout
    )


def check_main_branch() -> None:
    result = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.strip()
    if branch != "main":
        log.error(
            f"La rama actual es '{branch}', no 'main'. "
            "Cambia a la rama main antes de continuar."
        )
        sys.exit(1)


def check_github_connection() -> None:
    """Verify network access to the git remote by querying its HEAD ref."""
    result = _run(["git", "ls-remote", "--exit-code", "origin", "HEAD"], timeout=15)
    if result.returncode != 0:
        log.error(
            "No se pudo conectar con el repositorio remoto (origin). "
            "Verifica tu conexión a Internet y que tengas acceso al repositorio."
        )
        sys.exit(1)


def check_ready() -> None:
    """Run all pre-flight checks. Call once at the start of main()."""
    check_main_branch()
    check_github_connection()
