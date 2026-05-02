import argparse
import os
import sys
import tempfile
import zipfile
from pathlib import Path

import gdown

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402

log = get_logger()


def extract_id_from_url(url: str) -> str:
    if "/file/d/" in url:
        return url.split("/file/d/")[1].split("/")[0]
    if "id=" in url:
        return url.split("id=")[1].split("&")[0]
    return url


def main():
    parser = argparse.ArgumentParser(description="Download a public Google Drive zip and extract it.")
    parser.add_argument("url_or_id", help="Public Google Drive share URL or raw file ID")
    parser.add_argument("dest", help="Destination folder to extract contents into")
    args = parser.parse_args()

    file_id = extract_id_from_url(args.url_or_id)
    gdrive_url = f"https://drive.google.com/uc?id={file_id}"
    log.trace(f"File ID: {file_id}")

    os.makedirs(args.dest, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        log.trace("Downloading...")
        result = gdown.download(gdrive_url, tmp_path, quiet=False)
        if not result:
            raise RuntimeError("gdown returned None — download likely failed (file may not be publicly shared)")

        size = os.path.getsize(tmp_path)
        log.trace(f"Downloaded {size / 1024 / 1024:.1f} MB to {tmp_path}")

        log.trace(f"Extracting to {args.dest} ...")
        with zipfile.ZipFile(tmp_path) as zf:
            for member in zf.infolist():
                parts = member.filename.split("/")
                # strip the first component (root folder inside zip)
                stripped = "/".join(parts[1:])
                if not stripped:
                    continue
                target = os.path.join(args.dest, stripped)
                if member.is_dir():
                    os.makedirs(target, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(member) as src, open(target, "wb") as dst:
                        dst.write(src.read())

        log.trace("Done.")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


if __name__ == "__main__":
    main()
