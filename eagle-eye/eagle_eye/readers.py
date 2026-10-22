"""Turn an uploaded file into text.

Plain text and Markdown are read directly. Word and PDF are the planned next
formats: register a reader for the extension here and the text field becomes a
read-only preview of the extracted text.
"""

from typing import Callable

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def _read_plain(data: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


READERS: dict[str, Callable[[bytes], str]] = {
    "txt": _read_plain,
    "md": _read_plain,
}

SUPPORTED_TYPES = sorted(READERS)


def read_upload(name: str, data: bytes) -> str:
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in READERS:
        raise ValueError(f"Unsupported file type '.{extension}'. Supported: {', '.join(SUPPORTED_TYPES)}")
    return READERS[extension](data).replace("\r\n", "\n")
