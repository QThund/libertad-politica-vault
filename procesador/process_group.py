"""
Process a document-group folder.

Given the name of a folder under all-sources/, this script:

1. Reads grupos-procesados.txt (if it exists).
2. Looks for an exact match of the folder name.
3. If it is already there, asks whether to re-process it and whether to
   skip already-processed documents.
4. If it is new, appends the name, pulls the repo and pushes the change
   with the message "Reserva: Grupo <group>".
5. Copies the folder contents to vault/sources/.
6. Iterates over the documents copied (filtering already-processed ones
   when skip_flag is true) and runs the document-processing routine on
   each.
7. On success, appends the document name to documentos-procesados.txt
   and pushes with message "Procesado: <doc>  - Grupo <group>".

Usage:
    python process_group.py <group_name>
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Make sure the script's own directory is importable when invoked from
# anywhere (e.g. `python procesador/process_group.py 1`).
_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from logger import get_logger, log_session_start  # noqa: E402

REPO_ROOT = _HERE.parent
ALL_SOURCES = REPO_ROOT / "all-sources"
VAULT_SOURCES = REPO_ROOT / "vault" / "sources"
GROUPS_FILE = REPO_ROOT / "grupos-procesados.txt"
DOCS_FILE = REPO_ROOT / "documentos-procesados.txt"
CONFIG_FILE = REPO_ROOT / "config.txt"

GIT_PULL_SCRIPT = _HERE / "git_pull.py"
GIT_PUSH_SCRIPT = _HERE / "git_push.py"
DOWNLOAD_SCRIPT = _HERE / "download_and_extract.py"

log = get_logger()


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_line(path: Path, text: str) -> None:
    """Append `text` as its own line, fixing a missing trailing newline if needed."""
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as f:
            f.seek(-1, 2)
            ends_with_nl = f.read(1) == b"\n"
    else:
        ends_with_nl = True
    with path.open("a", encoding="utf-8") as f:
        if not ends_with_nl:
            f.write("\n")
        f.write(text + "\n")


def read_config(path: Path = CONFIG_FILE) -> dict[str, str]:
    """Parse config.txt as KEY=VALUE pairs (one per line, '#' for comments)."""
    if not path.exists():
        return {}
    config: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        config[key.strip()] = value.strip()
    return config


def ensure_all_sources() -> None:
    """If all-sources/ is missing, download and extract it from Drive."""
    if ALL_SOURCES.is_dir():
        return

    log.warning(
        f"No se encontró {ALL_SOURCES}. Descargando desde Google Drive..."
    )
    config = read_config()
    drive_url = config.get("DRIVE_URL")
    if not drive_url:
        log.error(
            f"No se pudo descargar all-sources: falta la entrada DRIVE_URL en {CONFIG_FILE}."
        )
        sys.exit(1)

    run_subscript(DOWNLOAD_SCRIPT, drive_url, str(ALL_SOURCES))

    if not ALL_SOURCES.is_dir():
        log.error(
            f"La descarga finalizó pero {ALL_SOURCES} sigue sin existir."
        )
        sys.exit(1)
    log.trace(f"all-sources disponible en {ALL_SOURCES}.")


def ask_yes_no(question: str) -> bool:
    while True:
        ans = input(f"{question} (s/n): ").strip().lower()
        if ans in ("s", "si", "sí", "y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        log.warning("Respuesta no reconocida; responde 's' o 'n'.")


def run_subscript(script: Path, *args: str) -> None:
    cmd = [sys.executable, str(script), *args]
    log.trace(f"Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        log.error(f"El subproceso {script.name} falló con código {result.returncode}")
        sys.exit(result.returncode)


def git_pull() -> None:
    run_subscript(GIT_PULL_SCRIPT)


def git_push(message: str) -> None:
    run_subscript(GIT_PUSH_SCRIPT, message)


def process_document(doc_path: Path, group_name: str) -> bool:
    """Run the document-processing pipeline on a single file.

    The actual processing script is still to be defined; for now this is
    a placeholder that returns True so the surrounding workflow can be
    exercised end-to-end.
    """
    log.trace(f"Procesando documento: {doc_path.name}")
    # TODO: invoke the document-processing script here once it is defined.
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a document-group folder.")
    parser.add_argument(
        "group_name",
        help="Name of the folder under all-sources/ to process",
    )
    args = parser.parse_args()
    log_session_start()
    group_name = args.group_name

    ensure_all_sources()

    group_dir = ALL_SOURCES / group_name
    if not group_dir.is_dir():
        log.error(f"No existe el grupo en all-sources: {group_dir}")
        sys.exit(1)

    log.trace(f"Iniciando procesamiento del grupo: {group_name}")

    skip_flag = False
    processed_groups = read_lines(GROUPS_FILE)

    if group_name in processed_groups:
        log.warning(f"El grupo {group_name!r} ya estaba registrado en {GROUPS_FILE.name}")
        if not ask_yes_no(
            "El grupo que intentas procesar ya ha sido procesado anteriormente, "
            "seguro que quieres re-procesarlo?"
        ):
            log.trace("Reproceso cancelado por el usuario.")
            return
        skip_flag = ask_yes_no("Quieres saltar los documentos ya procesados?")
        log.trace(f"Reproceso aceptado. skip_flag={skip_flag}")
    else:
        log.trace(f"Reservando grupo {group_name!r} en {GROUPS_FILE.name}")
        append_line(GROUPS_FILE, group_name)
        git_pull()
        git_push(f"Reserva: Grupo {group_name}")

    # Step 5: copy the group's files into vault/sources.
    VAULT_SOURCES.mkdir(parents=True, exist_ok=True)
    log.trace(f"Copiando documentos a {VAULT_SOURCES}")
    docs_in_group: list[str] = []
    for src in sorted(group_dir.iterdir()):
        if not src.is_file():
            continue
        shutil.copy2(src, VAULT_SOURCES / src.name)
        docs_in_group.append(src.name)
    log.trace(f"Copiados {len(docs_in_group)} documento(s) al vault.")

    # Steps 6 & 7: iterate, process, record, push.
    processed_docs = set(read_lines(DOCS_FILE))
    for doc_name in docs_in_group:
        if skip_flag and doc_name in processed_docs:
            log.trace(f"Saltando documento ya procesado: {doc_name}")
            continue

        doc_path = VAULT_SOURCES / doc_name
        try:
            success = process_document(doc_path, group_name)
        except Exception as e:
            log.error(f"Excepción procesando {doc_name}: {e}")
            continue

        if not success:
            log.error(f"Procesamiento fallido para {doc_name}")
            continue

        if doc_name not in processed_docs:
            append_line(DOCS_FILE, doc_name)
            processed_docs.add(doc_name)
        git_push(f"Procesado: {doc_name}  - Grupo {group_name}")
        log.trace(f"Documento procesado y subido: {doc_name}")

    log.trace(f"Finalizado el procesamiento del grupo: {group_name}")


if __name__ == "__main__":
    main()
