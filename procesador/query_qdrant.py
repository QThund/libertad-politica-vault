"""
Consulta la base de datos vectorial Qdrant usando LlamaIndex + Ollama o Claude.

Recupera chunks relevantes y genera una respuesta completa usando un LLM.
El proveedor se determina por LLM_PROVIDER en config.txt (ollama|claude).

Uso:
    python query_qdrant.py "<consulta>" [--k 5] [--model llama3]
                                        [--ollama-base-url http://localhost:11434]
                                        [--collection libertad_politica]
                                        [--qdrant-path vault/qdrant_db]
                                        [--temperature 1.0]
                                        [--thinking none|low|medium|high]

Presiona Ctrl+D (Unix) o Ctrl+Z Enter (Windows) para salir en modo interactivo.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.ollama import Ollama
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from logger import get_logger  # noqa: E402
from process_document import _resolve_thinking_budget  # noqa: E402

REPO_ROOT = _HERE.parent
DEFAULT_QDRANT_PATH = REPO_ROOT / "vault" / "qdrant_db"
DEFAULT_COLLECTION = "libertad_politica"
EMBED_MODEL_NAME = "BAAI/bge-m3"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

log = get_logger()


def load_config() -> dict:
    config = {}
    config_path = REPO_ROOT / "config.txt"
    if not config_path.exists():
        log.warning(f"config.txt no encontrado en {config_path}")
        return config
    try:
        with open(config_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
    except Exception as e:
        log.warning(f"Error leyendo config.txt: {e}")
    return config


def setup_index(qdrant_path: str, collection: str) -> VectorStoreIndex:
    client = QdrantClient(path=qdrant_path)
    vector_store = QdrantVectorStore(client=client, collection_name=collection)
    return VectorStoreIndex.from_vector_store(vector_store)


def call_claude_with_context(
    query: str,
    context_text: str,
    model: str,
    temperature: float = 1.0,
    thinking_budget: str = "none",
) -> tuple[str, dict]:
    """Llama a Claude directamente con el contexto recuperado del RAG."""
    import anthropic

    prompt = (
        "Eres un asistente especializado en política. Basándote en el siguiente "
        "contexto, responde la pregunta del usuario.\n\n"
        "CONTEXTO:\n"
        f"{context_text}\n\n"
        "PREGUNTA:\n"
        f"{query}"
    )

    client = anthropic.Anthropic()
    kwargs: dict = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }

    budget_tokens = _resolve_thinking_budget(thinking_budget)
    if budget_tokens > 0:
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget_tokens}
        kwargs["temperature"] = 1
    else:
        kwargs["temperature"] = temperature

    response = client.messages.create(**kwargs)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
    }
    text = next((b.text for b in response.content if b.type == "text"), "")
    return text, usage


def main() -> None:
    config = load_config()
    llm_provider = config.get("LLM_PROVIDER", "ollama").lower()

    if llm_provider == "claude":
        default_model = config.get("CLAUDE_MODEL", "claude-opus-4-7")
    else:
        default_model = config.get("OLLAMA_MODEL", "llama3")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default=None, help="Texto de la consulta")
    parser.add_argument("--k", type=int, default=5, help="Chunks a recuperar (def. 5)")
    parser.add_argument(
        "--model", default=default_model,
        help=(
            f"Modelo a usar (def. {default_model}). "
            "Opciones Claude: claude-opus-4-7 | claude-sonnet-4-6 | claude-haiku-4-5-20251001"
        ),
    )
    parser.add_argument(
        "--ollama-base-url",
        default=DEFAULT_OLLAMA_URL,
        help=f"URL de Ollama (def. {DEFAULT_OLLAMA_URL})",
    )
    parser.add_argument("--collection", default=DEFAULT_COLLECTION)
    parser.add_argument(
        "--qdrant-path", default=str(DEFAULT_QDRANT_PATH),
        help="Ruta del Qdrant embebido",
    )
    parser.add_argument("--device", default=None,
                        help="cpu, cuda, cuda:0, ... (def. autodeteccion)")
    parser.add_argument("--temperature", type=float, default=1.0,
                        help="Temperatura para Claude (0.0-2.0, def. 1.0)")
    parser.add_argument("--thinking", default="none",
                        help="Budget de thinking para Claude: none|low|medium|high (def. none)")
    args = parser.parse_args()

    if llm_provider == "claude" and args.thinking != "none" and "opus" not in args.model:
        log.warning(
            f"El modelo {args.model!r} no soporta extended thinking. "
            "Se ignora --thinking y se usa 'none'."
        )
        args.thinking = "none"

    qdrant_path = Path(args.qdrant_path)
    if not qdrant_path.exists():
        log.error(f"No se encontró Qdrant en {qdrant_path}")
        sys.exit(1)

    log.trace(f"Cargando modelo de embeddings {EMBED_MODEL_NAME}...")
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBED_MODEL_NAME,
        device=args.device,
        trust_remote_code=True,
    )

    # Para Ollama: configurar el LLM en LlamaIndex y usar TokenCountingHandler.
    # Para Claude: dejar Settings.llm vacío; se llama al SDK directamente para
    # soportar thinking y token reporting detallado.
    token_counter = None
    if llm_provider == "ollama":
        log.trace(f"LLM: OLLAMA (modelo: {args.model})")
        Settings.llm = Ollama(
            model=args.model,
            base_url=args.ollama_base_url,
            request_timeout=600,
        )
        token_counter = TokenCountingHandler()
        Settings.callback_manager = CallbackManager([token_counter])
    else:
        llm_info = f"CLAUDE (modelo: {args.model}"
        if args.thinking != "none":
            llm_info += f", thinking: {args.thinking}"
        llm_info += ")"
        log.trace(f"LLM: {llm_info}")

    log.trace(f"Cargando índice desde {qdrant_path} (colección: {args.collection})...")
    try:
        index = setup_index(str(qdrant_path), args.collection)
    except Exception as e:
        log.error(f"Error cargando el índice: {e}")
        sys.exit(1)

    # Claude calls the SDK directly for generation — only retrieval is needed.
    # Ollama uses the full query engine (retrieval + synthesis via LlamaIndex).
    if llm_provider == "claude":
        engine = index.as_retriever(similarity_top_k=args.k)
    else:
        engine = index.as_query_engine(similarity_top_k=args.k)

    llm_label = (
        f"CLAUDE ({args.model})" if llm_provider == "claude"
        else f"OLLAMA ({args.model})"
    )

    if args.query:
        _execute_single_query(
            engine, args.query, llm_provider, args.model,
            args.temperature, args.thinking, llm_label, token_counter,
        )
    else:
        _interactive_mode(
            engine, args.k, llm_provider, args.model,
            args.temperature, args.thinking, llm_label, token_counter,
        )


def _execute_single_query(
    query_engine,
    query: str,
    llm_provider: str,
    model: str,
    temperature: float,
    thinking_budget: str,
    llm_label: str,
    token_counter: TokenCountingHandler | None,
) -> None:
    try:
        if token_counter:
            token_counter.reset_counts()
        t0 = time.perf_counter()
        if llm_provider == "claude":
            source_nodes = query_engine.retrieve(query)
        else:
            response = query_engine.query(query)
            source_nodes = response.source_nodes
        elapsed = time.perf_counter() - t0
        log.trace(f"Consulta a Qdrant completada en {elapsed:.3f}s — consulta: {query!r}")

        print()
        print("=" * 80)
        print(f"CONSULTA: {query}")
        print(f"LLM: {llm_label}")
        print("=" * 80)
        print()

        if source_nodes:
            print("CHUNKS RECUPERADOS (antes de LLM):")
            print("-" * 80)
            context_parts = []
            for i, node in enumerate(source_nodes, 1):
                meta = node.metadata or {}
                content = node.get_content()
                context_parts.append(content)
                print(f"\n[Chunk {i}] (score: {node.score:.3f})")
                print(f"  Fuente: {meta.get('source', 'desconocida')}")
                print(f"  Doc ID: {meta.get('document_id', 'N/A')} | Chunk: {meta.get('chunk', 'N/A')}")
                print(f"  Texto: {content[:500]}{'...' if len(content) > 500 else ''}")
            print("\n" + "-" * 80)
            print()

        if llm_provider == "claude":
            if not source_nodes:
                log.warning("No se encontraron chunks relevantes")
                return
            context_text = "\n\n---\n\n".join(context_parts)
            print("Consultando a Claude...")
            t0_llm = time.perf_counter()
            try:
                response_text, usage = call_claude_with_context(
                    query, context_text, model, temperature, thinking_budget
                )
                elapsed_llm = time.perf_counter() - t0_llm
                log.response(response_text)
                print()
                print("RESPUESTA DE CLAUDE:")
                print("=" * 80)
                print()
                print(response_text)
                print()
                print("CONSUMO DE TOKENS (CLAUDE):")
                print("-" * 80)
                print(f"  Modelo:        {model}")
                print(f"  Input tokens:  {usage['input_tokens']:,}")
                print(f"  Output tokens: {usage['output_tokens']:,}")
                print(f"  Total tokens:  {usage['total_tokens']:,}")
                print(f"  Tiempo:        {elapsed_llm:.3f}s")
                print("-" * 80)
                print()
            except Exception as e:
                log.error(f"Error llamando a Claude: {e}")
                sys.exit(1)
        else:
            log.response(str(response))  # type: ignore[possibly-undefined]
            if token_counter:
                log.trace(
                    f"Tokens consumidos — "
                    f"LLM: {token_counter.total_llm_token_count}, "
                    f"embeddings: {token_counter.total_embedding_token_count}"
                )
            print("RESPUESTA DEL LLM:")
            print("=" * 80)
            print()
            print(response)  # type: ignore[possibly-undefined]
            print()
            if token_counter:
                print("CONSUMO DE TOKENS:")
                print("-" * 80)
                print(f"  LLM:        {token_counter.total_llm_token_count:,}")
                print(f"  Embeddings: {token_counter.total_embedding_token_count:,}")
                print(f"  Tiempo:     {elapsed:.3f}s")
                print("-" * 80)
                print()

    except Exception as e:
        log.error(f"Error en la consulta: {e}")
        sys.exit(1)


def _interactive_mode(
    query_engine,
    k: int,
    llm_provider: str,
    model: str,
    temperature: float,
    thinking_budget: str,
    llm_label: str,
    token_counter: TokenCountingHandler | None,
) -> None:
    print()
    print("=" * 80)
    print(f"Modo interactivo (mostrando {k} chunks más relevantes)")
    print(f"LLM: {llm_label}")
    print("Escribe 'salir' o presiona Ctrl+D para terminar")
    print("=" * 80)
    print()

    try:
        while True:
            try:
                query = input(">>> ").strip()
            except EOFError:
                print()
                print("Saliendo...")
                break

            if not query:
                continue
            if query.lower() in ("salir", "exit", "quit"):
                print("Saliendo...")
                break

            try:
                if token_counter:
                    token_counter.reset_counts()
                t0 = time.perf_counter()
                if llm_provider == "claude":
                    source_nodes = query_engine.retrieve(query)
                else:
                    response = query_engine.query(query)
                    source_nodes = response.source_nodes
                elapsed = time.perf_counter() - t0
                log.trace(f"Consulta a Qdrant completada en {elapsed:.3f}s — consulta: {query!r}")

                print()
                print("-" * 80)

                if source_nodes:
                    print("CHUNKS RECUPERADOS:")
                    context_parts = []
                    for i, node in enumerate(source_nodes, 1):
                        meta = node.metadata or {}
                        content = node.get_content()
                        context_parts.append(content)
                        print(f"[{i}] {meta.get('document_id', 'N/A')} (score: {node.score:.3f})")
                        print(f"    {content[:300]}{'...' if len(content) > 300 else ''}")
                    print()

                    if llm_provider == "claude":
                        context_text = "\n\n---\n\n".join(context_parts)
                        try:
                            response_text, usage = call_claude_with_context(
                                query, context_text, model, temperature, thinking_budget
                            )
                            log.response(response_text)
                            print("RESPUESTA:")
                            print(response_text)
                            print()
                            print(
                                f"[CLAUDE - Tokens: input={usage['input_tokens']:,}, "
                                f"output={usage['output_tokens']:,}, "
                                f"total={usage['total_tokens']:,}]"
                            )
                        except Exception as e:
                            log.error(f"Error llamando a Claude: {e}")
                    else:
                        log.response(str(response))  # type: ignore[possibly-undefined]
                        print("RESPUESTA:")
                        print(response)  # type: ignore[possibly-undefined]
                        print()
                        if token_counter:
                            print(
                                f"[Tokens — LLM: {token_counter.total_llm_token_count:,}, "
                                f"embeddings: {token_counter.total_embedding_token_count:,}, "
                                f"tiempo: {elapsed:.3f}s]"
                            )
                else:
                    print("No se encontraron chunks relevantes.")

                print("-" * 80)
                print()

            except Exception as e:
                log.error(f"Error: {e}")

    except KeyboardInterrupt:
        print()
        print("Saliendo...")


if __name__ == "__main__":
    main()
