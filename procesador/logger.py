"""
Logger that writes to both the console and an append-only HTML file.

Each entry becomes a <p> element inside the HTML file containing the
timestamp, the level (TRACE / WARNING / ERROR) and the message.

The log file lives at <repo_root>/log.html. The first time the file is
created an HTML header with UTF-8 charset is written so accents render
correctly in the browser.

Usage:
    from logger import get_logger
    log = get_logger()
    log.trace("hello")
    log.warning("careful")
    log.error("boom")
"""

from __future__ import annotations

import datetime
import html
import subprocess
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).parent.parent.resolve()
LOG_FILE = REPO_ROOT / "log.html"

_HTML_HEADER = (
    "<!doctype html>\n"
    "<html lang=\"es\">\n"
    "<head><meta charset=\"utf-8\"><title>LLM Wiki log</title>\n"
    "<style>\n"
    "  body { font-family: monospace; }\n"
    "  p.trace { color: black; }\n"
    "  p.prompt { color: #1a1a1a; background-color: #dff0ff; "
    "border-left: 3px solid #4a90d9; padding: 4px 8px; "
    "white-space: pre-wrap; }\n"
    "  p.response { color: #1a1a1a; background-color: #ffe4ef; "
    "border-left: 3px solid #e75480; padding: 4px 8px; "
    "white-space: pre-wrap; }\n"
    "  p.warning { color: #b58900; }\n"
    "  p.error { color: red; }\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
)


def _resolve_github_username() -> str:
    """Best-effort lookup of the user's GitHub login.

    Tries `gh api user --jq .login` first; falls back to `git config user.name`.
    """
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass

    return "desconocido"


class WikiLogger:
    def __init__(self, log_path: Path = LOG_FILE) -> None:
        self.log_path = log_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        if not self.log_path.exists():
            self.log_path.write_text(_HTML_HEADER, encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    _INLINE_STYLES = {
        "PROMPT": (
            "color:#1a1a1a;background-color:#dff0ff;"
            "border-left:3px solid #4a90d9;padding:4px 8px;"
            "white-space:pre-wrap;"
        ),
        "RESPONSE": (
            "color:#1a1a1a;background-color:#ffe4ef;"
            "border-left:3px solid #e75480;padding:4px 8px;"
            "white-space:pre-wrap;"
        ),
        "WARNING": "color:#b58900;",
        "ERROR": "color:red;",
    }

    def _write(self, level: str, message: str) -> None:
        if message is None:
            return
        text = str(message)
        if not text:
            return
        timestamp = self._now()
        print(f"[{timestamp}] {level}: {text}")
        escaped = html.escape(text).replace("\n", "<br>\n")
        style = self._INLINE_STYLES.get(level, "")
        style_attr = f" style=\"{style}\"" if style else ""
        line = (
            f"<p class=\"{level.lower()}\"{style_attr}>"
            f"[{html.escape(timestamp)}] "
            f"<strong>{level}</strong>: {escaped}</p>\n"
        )
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def trace(self, message: str) -> None:
        self._write("TRACE", message)

    def warning(self, message: str) -> None:
        self._write("WARNING", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def prompt(self, message: str) -> None:
        self._write("PROMPT", message)

    def response(self, message: str) -> None:
        self._write("RESPONSE", message)


_shared: Optional[WikiLogger] = None


def get_logger() -> WikiLogger:
    global _shared
    if _shared is None:
        _shared = WikiLogger()
    return _shared


def log_session_start() -> None:
    """Write the 'session started by <user>' trace. Call once at the top of main()."""
    get_logger().trace(f"Sesión iniciada por usuario: {_resolve_github_username()}")
