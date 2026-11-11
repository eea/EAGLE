"""Example class descriptions, read from config/examples.

Every `.txt` and `.md` file in the folder is an example; its file name (without the
extension) is the label in the Example menu. The folder is read on every page run, so
adding, editing or removing a file takes effect on the next interaction, without a restart.
Set EAGLE_EYE_EXAMPLES_DIR to read another folder.

Hidden files (starting with "." or "_") and README files are skipped.
"""

import os
from pathlib import Path

from .readers import read_upload

DEFAULT_DIR = Path(__file__).resolve().parent.parent / "config" / "examples"
SUFFIXES = (".txt", ".md")


def examples_dir() -> Path:
    return Path(os.environ.get("EAGLE_EYE_EXAMPLES_DIR") or DEFAULT_DIR)


def _is_example(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and path.suffix.lower() in SUFFIXES and not name.startswith((".", "_")) and path.stem.lower() != "readme"


def load_examples(directory: Path | None = None) -> dict[str, str]:
    """{label: text} of the example files, sorted by file name. Unreadable or empty files are skipped."""
    directory = directory or examples_dir()
    if not directory.is_dir():
        return {}
    examples: dict[str, str] = {}
    for path in sorted((p for p in directory.iterdir() if _is_example(p)), key=lambda p: p.name.lower()):
        try:
            text = read_upload(path.name, path.read_bytes()).strip()
        except (OSError, ValueError):
            continue
        if text:
            label = path.stem if path.stem not in examples else path.name  # a.txt and a.md: tell them apart
            examples[label] = text
    return examples
