# Project Overview

RAG pipeline for processing Spanish/English political-liberty documents (PDFs → text → vector DB → LLM queries).

## Workflow

1. **Extract**: PDFs → `.txt` files via `extract_pdf_llamaindex.py`
2. **Index**: `.txt` files → Qdrant vector DB via `build_qdrant_index.py`
3. **Query**: User questions → retrieved chunks + LLM response via `query_qdrant.py`

## Folder Structure

- `all-pdfs/` — source PDF files to be processed
- `all-sources/` — plain-text files extracted from PDFs, ready for indexing
- `vault/` — Qdrant vector database and indexed sources
- `procesador/` — all Python scripts (see below)
- `final/` — final output files
- `test-pdfs/` — PDFs used for testing
- `log.html` — append-only HTML log written by `logger.py`
- `config.txt` — shared configuration for all scripts
- `documentos-procesados.txt` — names of already-processed documents (prevents re-processing)
- `grupos-procesados.txt` — names of already-processed folders (prevents re-processing)

## Scripts (`procesador/`)

| File | Purpose |
|------|---------|
| `extract_pdf_llamaindex.py` | Extracts text from PDFs; supports pypdf, pymupdf, llamaparse backends |
| `build_qdrant_index.py` | Indexes `.txt` files into Qdrant using KaLM-Embedding-Gemma3-12B embeddings |
| `query_qdrant.py` | Interactive RAG query interface; supports Claude or Ollama as the LLM |
| `config_utils.py` | Shared helper that parses `config.txt` into a dict |
| `logger.py` | Logs to console and `log.html`; API: `log.trace()`, `log.warning()`, `log.error()` |

## config.txt Keys

| Key | Description |
|-----|-------------|
| `DRIVE_URL` | Google Drive source link |
| `MAX_WORDS_PER_GROUP` | Word cap per processing group |
| `MAX_TOKENS_PER_CHUNK` | Token cap per indexed chunk |
| `DEBUG_RESPONSES` | Enable verbose LLM output (true/false) |
| `LLM_PROVIDER` | `claude` or `ollama` |
| `OLLAMA_MODEL` | Ollama model name (e.g. `llama3`) |
| `CLAUDE_MODEL` | Claude model ID (e.g. `claude-sonnet-4-6`) |
| `CLAUDE_TEMPERATURE` | Sampling temperature for Claude |
| `CLAUDE_THINKING_BUDGET` | Thinking depth (`low`/`medium`/`high`) |
| `PDF_PARSER` | `pypdf`, `pymupdf`, or `llamaparse` |
| `LLAMAPARSE_API_KEY` | LlamaParse API key |
| `LLAMAPARSE_RESULT_TYPE` | Output format (e.g. `markdown`) |
| `LLAMAPARSE_LANGUAGE` | Languages hint (e.g. `es,en`) |
| `LLAMAPARSE_TIER` | Cost tier (`cost_effective`, etc.) |

## Notes

- Python 3.13 or earlier required — LlamaIndex uses pydantic v1, incompatible with 3.14+.
- Virtual environment is in `.venv/`.
- All scripts read `config.txt` via `config_utils.py`; CLI flags can override individual settings.