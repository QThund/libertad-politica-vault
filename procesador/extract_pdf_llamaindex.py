"""
Extrae el texto de cada PDF de una carpeta usando LlamaIndex y guarda
un .txt por PDF en una subcarpeta con fecha y hora en el nombre.

Parsers disponibles: pypdf | pymupdf | llamaparse
El parser por defecto se lee de config.txt (PDF_PARSER). Se puede
sobreescribir con --parser.

Uso:
    python extract_pdf_llamaindex.py <carpeta_pdfs>
    python extract_pdf_llamaindex.py <carpeta_pdfs> --parser llamaparse
    python extract_pdf_llamaindex.py <carpeta_pdfs> --output-root <carpeta>
"""

import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
_REPO_ROOT = _HERE.parent

if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from config_utils import read_config  # noqa: E402
from logger import get_logger  # noqa: E402


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def load_with_pypdf(pdf_path: Path, log) -> str:
    from llama_index.readers.file import PDFReader
    reader = PDFReader(return_full_document=True)
    docs = reader.load_data(file=pdf_path)
    return "\n\n".join(d.text for d in docs if d.text).strip()


def load_with_pymupdf(pdf_path: Path, log) -> str:
    from llama_index.readers.file import PyMuPDFReader
    reader = PyMuPDFReader()
    docs = reader.load(file_path=pdf_path)
    return "\n\n".join(d.text for d in docs if d.text).strip()


async def _llamaparse_async(pdf_path: Path, cfg: dict[str, str], log) -> str:
    from llama_cloud import AsyncLlamaCloud

    api_key = cfg.get("LLAMAPARSE_API_KEY") or os.environ.get("LLAMAPARSE_API_KEY", "")
    if not api_key:
        raise ValueError(
            "LlamaParse requiere LLAMAPARSE_API_KEY en config.txt o como variable de entorno"
        )

    result_type = cfg.get("LLAMAPARSE_RESULT_TYPE", "markdown")
    tier = cfg.get("LLAMAPARSE_TIER", "cost_effective")
    version = cfg.get("LLAMAPARSE_VERSION", "latest")
    languages = [l.strip() for l in cfg.get("LLAMAPARSE_LANGUAGE", "es").split(",") if l.strip()]

    # expand selecciona qué campos devuelve la API; sin esto solo llega metadata
    expand_field = "markdown_full" if result_type == "markdown" else "text_full"

    log.trace(
        f"LlamaParse — tier={tier}, version={version}, "
        f"result_type={result_type}, languages={languages}"
    )

    client = AsyncLlamaCloud(api_key=api_key)
    file_obj = await client.files.create(file=str(pdf_path), purpose="parse")
    result = await client.parsing.parse(
        file_id=file_obj.id,
        tier=tier,
        version=version,
        processing_options={
            "ocr_parameters": {"languages": languages},
        },
        expand=[expand_field],
    )

    return (getattr(result, expand_field) or "").strip()


def load_with_llamaparse(pdf_path: Path, cfg: dict[str, str], log) -> str:
    import asyncio
    return asyncio.run(_llamaparse_async(pdf_path, cfg, log))


def extract_text(pdf_path: Path, parser: str, cfg: dict[str, str], log) -> str:
    if parser == "pypdf":
        return load_with_pypdf(pdf_path, log)
    if parser == "pymupdf":
        return load_with_pymupdf(pdf_path, log)
    if parser == "llamaparse":
        return load_with_llamaparse(pdf_path, cfg, log)
    raise ValueError(f"Parser desconocido: {parser!r}. Opciones: pypdf, pymupdf, llamaparse")


# ---------------------------------------------------------------------------
# Pipeline por PDF
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
    out_folder: Path,
    parser: str,
    cfg: dict[str, str],
    log,
    index: int,
    total: int,
) -> bool:
    start = time.monotonic()
    log.trace(f"▶ [{index}/{total}] {pdf_path.name} (parser: {parser})")
    try:
        text = extract_text(pdf_path, parser, cfg, log)
    except Exception as e:
        log.error(f"Error procesando {pdf_path.name}: {e}")
        return False

    if not text:
        log.error(f"Sin texto extraíble en {pdf_path.name}")
        return False

    txt_path = out_folder / (pdf_path.stem + ".txt")
    txt_path.write_text(text, encoding="utf-8")
    elapsed = time.monotonic() - start
    log.trace(f"✓ {pdf_path.name} → {txt_path.name} ({elapsed:.2f}s)")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extrae texto de PDFs con LlamaIndex y guarda un .txt por PDF."
    )
    parser.add_argument("pdf_folder", help="Carpeta con los PDFs")
    parser.add_argument(
        "--parser",
        choices=["pypdf", "pymupdf", "llamaparse"],
        default=None,
        help="Parser a usar (sobreescribe PDF_PARSER de config.txt)",
    )
    parser.add_argument(
        "--output-root",
        default=".",
        help="Carpeta donde crear la subcarpeta de salida (por defecto: cwd)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()
    log = get_logger()
    cfg = read_config()
    total_start = time.monotonic()

    # Resolver parser: argumento CLI > config.txt > fallback pymupdf
    parser = args.parser or cfg.get("PDF_PARSER", "pymupdf")
    log.trace(f"Parser seleccionado: {parser}")

    pdf_folder = Path(args.pdf_folder).resolve()
    if not pdf_folder.is_dir():
        log.error(f"La carpeta no existe: {pdf_folder}")
        sys.exit(1)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_folder = Path(args.output_root).resolve() / f"llamaindex_extract_{timestamp}"
    out_folder.mkdir(parents=True, exist_ok=True)
    log.trace(f"Carpeta de salida: {out_folder}")

    pdfs = sorted(set(list(pdf_folder.glob("*.pdf")) + list(pdf_folder.glob("*.PDF"))))
    if not pdfs:
        log.warning(f"No se encontraron PDFs en {pdf_folder}")
        sys.exit(0)

    log.trace(f"PDFs encontrados: {len(pdfs)}")

    ok = 0
    failed: list[Path] = []
    for i, pdf in enumerate(pdfs, start=1):
        if process_pdf(pdf, out_folder, parser, cfg, log, i, len(pdfs)):
            ok += 1
        else:
            failed.append(pdf)

    elapsed = time.monotonic() - total_start
    log.trace(f"DONE! {ok}/{len(pdfs)} PDFs procesados en {elapsed:.2f}s")
    if failed:
        plain = "\n".join(f"  - {p.name}" for p in failed)
        log.warning(f"PDFs fallidos ({len(failed)}):\n{plain}")


if __name__ == "__main__":
    main()
