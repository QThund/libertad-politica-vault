"""
Indexa documentos de texto plano en una base de datos vectorial Qdrant
usando LlamaIndex y el modelo de embeddings KaLM-Embedding-Gemma3-12B-2511.

Cada chunk se almacena con los metadatos:
    - document_id: identificador estable del documento (stem + hash corto)
    - source:      ruta absoluta del fichero original
    - version:     version del documento/indexado (parametro --version)
    - chunk:       indice del chunk dentro del documento (0-based)

Uso:
    python build_qdrant_index.py <ruta> [--version V] [--collection NAME]
                                        [--qdrant-url URL] [--qdrant-path DIR]
                                        [--chunk-size N] [--chunk-overlap N]

<ruta> puede ser un fichero .txt o un directorio (se procesan recursivamente
los .txt). Por defecto Qdrant se usa en modo embebido en vault/qdrant_db/.

Requiere Python 3.13 o anterior (LlamaIndex usa pydantic v1, incompatible con 3.14).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from logger import get_logger  # noqa: E402
from process_document import read_config  # noqa: E402

REPO_ROOT = _HERE.parent
DEFAULT_QDRANT_PATH = REPO_ROOT / "vault" / "qdrant_db"
DEFAULT_COLLECTION = "libertad_politica"
EMBED_MODEL_NAME = "BAAI/bge-m3"

log = get_logger()


def stable_document_id(path: Path) -> str:
    """ID estable derivado del nombre + hash corto de la ruta absoluta."""
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:8]
    return f"{path.stem}-{digest}"


def collect_txt_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if root.is_dir():
        return sorted(p for p in root.rglob("*.txt") if p.is_file())
    raise FileNotFoundError(root)


def load_documents(paths: list[Path], version: str) -> list[Document]:
    docs: list[Document] = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        docs.append(Document(
            text=text,
            metadata={
                "document_id": stable_document_id(path),
                "source": str(path),
                "version": version,
            },
        ))
    return docs


def build_nodes(docs: list[Document], chunk_size: int, chunk_overlap: int):
    splitter = SentenceSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    all_nodes = []
    docs_seen = set()
    for doc in docs:
        doc_nodes = splitter.get_nodes_from_documents([doc])
        for i, node in enumerate(doc_nodes):
            node.metadata["chunk"] = i
            node.excluded_embed_metadata_keys = ["chunk"]
            node.excluded_llm_metadata_keys = ["chunk"]
        docs_seen.add(doc.metadata["document_id"])
        all_nodes.extend(doc_nodes)
    return all_nodes, docs_seen


def make_qdrant_client(args) -> QdrantClient:
    if args.qdrant_url:
        return QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key)
    Path(args.qdrant_path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=args.qdrant_path)


def main() -> None:
    config = read_config()
    default_chunk = int(config.get("MAX_TOKENS_PER_CHUNK", "1500") or 1500)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="Fichero .txt o directorio con .txt")
    parser.add_argument("--version", default="1", help="Version del documento (metadato)")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument("--qdrant-url", default=None,
                        help="URL de un Qdrant remoto. Si se omite se usa modo embebido.")
    parser.add_argument("--qdrant-api-key", default=None)
    parser.add_argument("--qdrant-path", default=str(DEFAULT_QDRANT_PATH),
                        help="Directorio para Qdrant embebido (def. vault/qdrant_db)")
    parser.add_argument("--chunk-size", type=int, default=default_chunk)
    parser.add_argument("--device", default=None,
                        help="cpu, cuda, cuda:0, ... (def. autodeteccion)")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    files = collect_txt_files(root)
    if not files:
        log.error(f"No se encontraron .txt en {root}")
        sys.exit(1)
    log.trace(f"Indexando {len(files)} fichero(s) bajo {root}.")

    log.trace(f"Cargando modelo de embeddings {EMBED_MODEL_NAME}...")
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBED_MODEL_NAME,
        device=args.device,
        trust_remote_code=True,
    )

    docs = load_documents(files, args.version)
    nodes, docs_seen = build_nodes(docs, args.chunk_size, args.chunk_size * 0.1)
    total_chunks = len(nodes)
    log.trace(f"Generados {total_chunks} chunks ({len(docs_seen)} documento(s)).")

    client = make_qdrant_client(args)
    try:
        vector_store = QdrantVectorStore(client=client, collection_name=args.collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        VectorStoreIndex(nodes=nodes, storage_context=storage_context, show_progress=True)
        log.trace(f"Indexados {total_chunks} chunks en la coleccion '{args.collection}'.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
