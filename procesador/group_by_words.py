"""
Group .txt files from a folder into numbered subfolders
based on a maximum total word count per group.

Usage:
    python group_by_words.py <input_folder> <max_words>

Example:
    python group_by_words.py ../all-sources 100
"""

import argparse
import shutil
import sys
from pathlib import Path

_HERE = Path(__file__).parent.resolve()
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
from logger import get_logger  # noqa: E402

log = get_logger()


def count_words(filepath: Path) -> int:
    text = filepath.read_text(encoding="utf-8", errors="ignore")
    return len(text.split())


def group_files(input_folder: Path, max_words: int) -> None:
    txt_files = sorted(input_folder.glob("*.txt"))

    if not txt_files:
        log.warning(f"No .txt files found in {input_folder}")
        return

    group_num = 1
    current_words = 0
    current_group: list[Path] = []

    def flush_group(files: list[Path], num: int) -> None:
        dest = input_folder / str(num)
        dest.mkdir(exist_ok=True)
        for f in files:
            shutil.move(str(f), dest / f.name)
        total = sum(count_words(dest / f.name) for f in files)
        log.trace(f"Group {num}: {len(files)} file(s), {total} words -> {dest}")

    for txt in txt_files:
        words = count_words(txt)

        if current_group and current_words + words > max_words:
            flush_group(current_group, group_num)
            group_num += 1
            current_group = []
            current_words = 0

        current_group.append(txt)
        current_words += words

    if current_group:
        flush_group(current_group, group_num)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Group .txt files into subfolders by max word count."
    )
    parser.add_argument("input_folder", help="Folder containing the .txt files")
    parser.add_argument("max_words", type=int, help="Maximum words per group")
    args = parser.parse_args()

    input_folder = Path(args.input_folder).resolve()
    if not input_folder.is_dir():
        parser.error(f"Not a directory: {input_folder}")

    group_files(input_folder, args.max_words)


if __name__ == "__main__":
    main()
