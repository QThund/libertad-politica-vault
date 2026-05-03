"""
Process a single plain-text document by chunking it and sending each
chunk to Ollama (model llama3) together with CLAUDE.md as base context.

Behaviour:
1. Read the .txt file.
2. Split it into chunks of approximately N tokens (parameter), trying
   not to break paragraphs. A paragraph boundary is a blank line.
   Token count is approximated by whitespace-separated words.
3. For each chunk, send a prompt to Ollama containing:
     - CLAUDE.md (base context)
     - the source file path
     - the chunk number (1-based) and total chunk count
     - the chunk text itself
   The HTTP call to Ollama uses a 600-second timeout.
4. On a timeout or any other error the whole process stops, the error
   is logged via the shared logger and the script exits with code 1.

Usage:
    python process_document.py <txt_path> <n_tokens>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from logger import get_logger  # noqa: E402

REPO_ROOT = _HERE.parent
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
ANNOTATIONS_DIR = REPO_ROOT / "vault" / "annotations"
CONFIG_FILE = REPO_ROOT / "config.txt"
ERRORED_DOCS_FILE = REPO_ROOT / "documentos_erroneos.txt"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"
OLLAMA_TIMEOUT_S = 600

log = get_logger()


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


def record_error(filename: str) -> None:
    with ERRORED_DOCS_FILE.open("a", encoding="utf-8") as f:
        f.write(filename + "\n")


def count_tokens(text: str) -> int:
    """Rough token count: whitespace-separated words."""
    return len(text.split())


def split_into_chunks(text: str, max_tokens: int) -> list[str]:
    """Split `text` into chunks of ~max_tokens, preserving paragraph boundaries.

    Paragraphs are separated by one or more blank lines. A paragraph
    larger than max_tokens is kept whole rather than being split.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = count_tokens(para)
        if current and current_tokens + para_tokens > max_tokens:
            chunks.append("\n\n".join(current))
            current = [para]
            current_tokens = para_tokens
        else:
            current.append(para)
            current_tokens += para_tokens

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def build_prompt(claude_md: str, source_path: Path, chunk_index: int,
                 total_chunks: int, chunk_text: str) -> str:
    pdf_path = source_path.with_suffix(".pdf")
    return (
        "=== CONTEXTO BASE (CLAUDE.md) ===\n"
        f"{claude_md}\n\n"
        "=== INSTRUCCIONES ===\n"
        "Analiza el fragmento de texto que aparece al final y genera anotaciones "
        "en formato wiki para los conceptos relevantes que encuentres "
        "(partidos políticos, personas, medios de comunicación, fechas, "
        "organizaciones, empresas, opiniones de García-Trevijano, citas de "
        "libros/películas/arte/papers, etc.).\n\n"
        "Devuelve ÚNICAMENTE un array JSON válido. Cada elemento tiene dos campos:\n"
        '  "filename": nombre del fichero markdown basado en el concepto '
        "(sin carpeta, sin espacios, en minúsculas con guiones, extensión .md)\n"
        '  "content": contenido completo de la anotación en markdown, que debe '
        "incluir obligatoriamente un enlace a la fuente original con esta ruta: "
        f"`{pdf_path}`\n\n"
        "No incluyas nada fuera del array JSON.\n\n"
        "=== METADATOS ===\n"
        f"Fichero fuente: {source_path}\n"
        f"Chunk: {chunk_index} de {total_chunks}\n\n"
        "=== FRAGMENTO ===\n"
        f"{chunk_text}\n"
    )


def call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    response = requests.post(
        OLLAMA_URL,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
        timeout=OLLAMA_TIMEOUT_S,
    )
    response.raise_for_status()
    return response.json().get("response", "")


def parse_and_save_annotations(raw: str, chunk_index: int) -> int:
    """Parse Ollama's JSON response and write each annotation to vault/annotations/.

    Returns the number of files written.
    """
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Extract the JSON array even if Ollama wraps it in a code block.
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("No se encontró un array JSON en la respuesta de Ollama.")
    annotations = json.loads(raw[start: end + 1])

    written = 0
    for item in annotations:
        filename = item.get("filename", "").strip()
        content = item.get("content", "").strip()
        if not filename or not content:
            log.warning(f"Anotación vacía o sin nombre en chunk {chunk_index}, ignorada.")
            continue
        out_file = ANNOTATIONS_DIR / filename
        out_file.write_text(content, encoding="utf-8")
        written += 1

    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chunk a .txt and send each chunk to Ollama (llama3)."
    )
    parser.add_argument("txt_path", help="Ruta al fichero .txt a procesar")
    parser.add_argument("n_tokens", type=int,
                        help="Tamaño aproximado de cada chunk en tokens")
    args = parser.parse_args()

    config = read_config()
    debug_responses = config.get("DEBUG_RESPONSES", "false").lower() == "true"

    txt_path = Path(args.txt_path).resolve()
    if not txt_path.is_file():
        log.error(f"No existe el fichero: {txt_path}")
        record_error(txt_path.name)
        sys.exit(1)

    if args.n_tokens <= 0:
        log.error(f"n_tokens debe ser positivo, recibido: {args.n_tokens}")
        record_error(txt_path.name)
        sys.exit(1)

    if not CLAUDE_MD.is_file():
        log.error(f"No se encuentra CLAUDE.md en {CLAUDE_MD}")
        record_error(txt_path.name)
        sys.exit(1)

    try:
        text = txt_path.read_text(encoding="utf-8")
        claude_md = CLAUDE_MD.read_text(encoding="utf-8")
    except Exception as e:
        log.error(f"Error leyendo ficheros de entrada: {e}")
        record_error(txt_path.name)
        sys.exit(1)

    chunks = split_into_chunks(text, args.n_tokens)
    total = len(chunks)
    log.trace(f"Fichero {txt_path.name} dividido en {total} chunk(s) "
              f"(~{args.n_tokens} tokens cada uno).")

    for i, chunk in enumerate(chunks, start=1):
        prompt = build_prompt(claude_md, txt_path, i, total, chunk)
        log.trace(f"Enviando chunk {i}/{total} a Ollama "
                  f"({count_tokens(chunk)} tokens aprox.)...")
        log.prompt(f"Prompt chunk {i}/{total}:\n{prompt}")
        t0 = time.monotonic()
        try:
            answer = call_ollama(prompt)
        except requests.exceptions.Timeout:
            log.error(
                f"Timeout (>{OLLAMA_TIMEOUT_S}s) llamando a Ollama "
                f"en el chunk {i}/{total} de {txt_path}. Proceso detenido."
            )
            record_error(txt_path.name)
            sys.exit(1)
        except Exception as e:
            log.error(
                f"Error llamando a Ollama en el chunk {i}/{total} "
                f"de {txt_path}: {e}. Proceso detenido."
            )
            record_error(txt_path.name)
            sys.exit(1)
        elapsed = time.monotonic() - t0
        mins, secs = divmod(int(elapsed), 60)
        log.trace(f"Ollama respondió al chunk {i}/{total} en {mins}m {secs:02d}s.")

        if debug_responses:
            log.response(f"Respuesta Ollama chunk {i}/{total}:\n{answer}")

        try:
            n = parse_and_save_annotations(answer, i)
        except Exception as e:
            log.error(
                f"Error parseando/guardando anotaciones del chunk {i}/{total}: {e}. "
                "Proceso detenido."
            )
            record_error(txt_path.name)
            sys.exit(1)
        log.trace(f"Chunk {i}/{total}: {n} anotación(es) guardada(s) en annotations.")

    log.trace(f"Procesamiento completado para {txt_path.name}.")


if __name__ == "__main__":
    main()
