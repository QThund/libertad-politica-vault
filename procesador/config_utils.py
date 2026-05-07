"""
Utilidades de configuración compartidas.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent.resolve()
REPO_ROOT = _HERE.parent
CONFIG_FILE = REPO_ROOT / "config.txt"


def read_config() -> dict[str, str]:
    if not CONFIG_FILE.exists():
        return {}
    config: dict[str, str] = {}
    for raw in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip()
    return config
