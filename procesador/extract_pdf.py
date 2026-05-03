import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import pypdf
import pytesseract
from pdf2image import convert_from_path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def extract_text_pypdf(pdf_path: Path, log) -> str:
    try:
        reader = pypdf.PdfReader(str(pdf_path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages_text).strip()
    except Exception as e:
        log.warning(f"Error leyendo {pdf_path.name} con pypdf: {e}")
        return ""


def extract_text_ocr(pdf_path: Path, ocr_lang: str, log) -> str:
    log.warning(f"Usando OCR (tesseract lang={ocr_lang}) para {pdf_path.name}")
    images = convert_from_path(str(pdf_path), dpi=300)
    parts = []
    for i, image in enumerate(images):
        try:
            text = pytesseract.image_to_string(image, lang=ocr_lang)
            parts.append(text)
        except pytesseract.TesseractNotFoundError:
            log.error(
                "Tesseract no encontrado. Establece la variable de entorno TESSERACT_CMD "
                "con la ruta al ejecutable tesseract.exe"
            )
            raise
        except Exception as e:
            log.warning(f"Error OCR en página {i+1} de {pdf_path.name}: {e}")
    return "\n\n".join(parts).strip()


def extract_text(pdf_path: Path, ocr_lang: str, log) -> tuple[str, str]:
    text = extract_text_pypdf(pdf_path, log)
    if text:
        return text, "pypdf"
    text = extract_text_ocr(pdf_path, ocr_lang, log)
    return text, "ocr"


# ---------------------------------------------------------------------------
# Text file output
# ---------------------------------------------------------------------------

def write_text_file(pdf_path: Path, text: str, txt_folder: Path, log) -> Path:
    txt_path = txt_folder / (pdf_path.stem + ".txt")
    txt_path.write_text(text, encoding="utf-8")
    log.trace(f"Texto guardado en {txt_path}")
    return txt_path


# ---------------------------------------------------------------------------
# Per-PDF pipeline
# ---------------------------------------------------------------------------

def process_pdf(
    pdf_path: Path,
    txt_folder: Path,
    ocr_lang: str,
    log,
    index: int = 1,
    total: int = 1,
) -> dict | None:
    start_time = time.monotonic()
    counter = f"[{index} / {total}]"
    log.trace(f"▶ {counter} PDF: {pdf_path.name}")

    text, method = extract_text(pdf_path, ocr_lang, log)
    if not text:
        log.error(f"Sin texto extraíble en {pdf_path.name} (ni pypdf ni OCR)")
        return None

    txt_path = write_text_file(pdf_path, text, txt_folder, log)

    elapsed = time.monotonic() - start_time
    log.trace(f"Completado: {pdf_path.name} | {elapsed:.3f}s | método: {method}")
    return {
        "pdf": str(pdf_path),
        "txt": str(txt_path),
        "method": method,
        "elapsed_s": round(elapsed, 3),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extrae texto de PDFs.")
    parser.add_argument("pdf_folder", help="Carpeta con los PDFs")
    parser.add_argument("--ocr-lang", default="spa+eng+ca+gl+eu", help="Idioma para Tesseract OCR",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    total_start = time.monotonic()

    run_folder = Path.cwd() / f"results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    run_folder.mkdir(parents=True, exist_ok=True)

    json_path = run_folder / "results.json"
    txt_folder = run_folder / "extracted_texts"
    txt_folder.mkdir()

    log = get_logger()

    tesseract_cmd = os.environ.get("TESSERACT_CMD", "")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        log.trace(f"Tesseract cmd: {tesseract_cmd}")

    log.trace(f"Inicio — carpeta de resultados: {run_folder}")

    pdf_folder = Path(args.pdf_folder).resolve()
    pdfs = sorted(set(list(pdf_folder.glob("*.pdf")) + list(pdf_folder.glob("*.PDF"))))

    if not pdfs:
        log.warning(f"No se encontraron PDFs en {pdf_folder}")
        sys.exit(0)

    log.trace(f"PDFs encontrados: {len(pdfs)}")

    total = len(pdfs)
    results = []
    failed: list[Path] = []
    for index, pdf_path in enumerate(pdfs, start=1):
        try:
            entry = process_pdf(
                pdf_path, txt_folder, args.ocr_lang, log,
                index=index, total=total,
            )
        except Exception as e:
            log.error(f"Error inesperado procesando {pdf_path.name}: {e}")
            entry = None
        if entry is not None:
            results.append(entry)
        else:
            failed.append(pdf_path)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    log.trace(f"Escritos {len(results)} registros en {json_path}")

    if failed:
        plain = "\n".join(f"  - {p}" for p in failed)
        log.warning(f"PDFs que no se pudieron procesar ({len(failed)}):\n{plain}")

    total_elapsed = time.monotonic() - total_start
    log.trace(f"DONE! Tiempo total: {total_elapsed:.3f}s")


if __name__ == "__main__":
    main()
