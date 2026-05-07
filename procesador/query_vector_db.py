"""
Consulta la base de datos vectorial FAISS global creada por build_vector_db.py.

Pasos:
1. Carga el índice FAISS global y los metadatos desde vault/vector_db/.
2. Calcula el embedding de la consulta usando Ollama con el mismo modelo
   con el que se construyó la base (registrado en chunks.json).
3. Busca los k chunks más cercanos (L2) e imprime fuente, distancia y texto.

Uso:
    python query_vector_db.py "<consulta>" [--k 5] [--max-chars 500]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import faiss
import numpy as np
import requests

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from logger import get_logger  # noqa: E402

REPO_ROOT = _HERE.parent
VECTOR_DB_DIR = REPO_ROOT / "vault" / "vector_db"
GLOBAL_INDEX_PATH = VECTOR_DB_DIR / "index.faiss"
GLOBAL_META_PATH = VECTOR_DB_DIR / "chunks.json"

OLLAMA_EMBEDDINGS_URL = "http://localhost:11434/api/embeddings"
OLLAMA_TIMEOUT_S = 600

log = get_logger()


def embed_query(text: str, model: str) -> np.ndarray:
    response = requests.post(
        OLLAMA_EMBEDDINGS_URL,
        json={"model": model, "prompt": text},
        timeout=OLLAMA_TIMEOUT_S,
    )
    response.raise_for_status()
    embedding = response.json().get("embedding")
    if not embedding:
        raise ValueError("Respuesta de Ollama sin campo 'embedding'.")
    return np.array([embedding], dtype="float32")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consulta la base vectorial FAISS global."
    )
    parser.add_argument("query", help="Texto de la consulta")
    parser.add_argument("--k", type=int, default=5, help="Número de resultados (def. 5)")
    parser.add_argument("--max-chars", type=int, default=500,
                        help="Máx. caracteres de cada chunk a mostrar (def. 500)")
    args = parser.parse_args()

    if not GLOBAL_INDEX_PATH.is_file() or not GLOBAL_META_PATH.is_file():
        log.error(
            f"No se encontró la base de datos global en {VECTOR_DB_DIR}. "
            "Ejecuta build_vector_db.py sobre al menos un documento primero."
        )
        sys.exit(1)

    try:
        meta = json.loads(GLOBAL_META_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log.error(f"Error leyendo metadatos {GLOBAL_META_PATH}: {e}")
        sys.exit(1)

    model = meta.get("model")
    if not model:
        log.error("Los metadatos no incluyen el modelo de embeddings.")
        sys.exit(1)

    index = faiss.read_index(str(GLOBAL_INDEX_PATH))
    log.trace(f"Índice global cargado: {index.ntotal} vectores, dim={index.d}, modelo={model}.")

    try:
        q_vec = embed_query(args.query, model)
    except Exception as e:
        log.error(f"Error embebiendo la consulta: {e}")
        sys.exit(1)

    k = min(args.k, index.ntotal)
    t0 = time.perf_counter()
    distances, indices = index.search(q_vec, k)
    elapsed = time.perf_counter() - t0

    chunks = meta.get("chunks", [])
    log.trace(f"Búsqueda en FAISS completada en {elapsed:.3f}s — {k} resultados para: {args.query!r}")

    print()
    print(f"=== Top {k} resultados para: {args.query!r} ===")
    for rank, (dist, idx) in enumerate(zip(distances[0], indices[0]), start=1):
        if idx < 0 or idx >= len(chunks):
            continue
        c = chunks[idx]
        text = c.get("text", "")
        if len(text) > args.max_chars:
            text = text[:args.max_chars].rstrip() + "..."
        log.trace(
            f"Resultado #{rank}: distancia={dist:.4f}  "
            f"chunk={c.get('chunk_index')}  fuente={c.get('source')}\n{text}"
        )
        print()
        print(f"--- #{rank}  distancia={dist:.4f}  "
              f"chunk {c.get('chunk_index')}  fuente={c.get('source')} ---")
        print(text)
    print()


if __name__ == "__main__":
    main()
