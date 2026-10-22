"""Build data/eagle_vocabulary.json from the official EAGLE matrix sources.

* EAGLE Barcoding Template (v3.2): URI, code, label and level of every element.
* 3.2 change-log workbook: element type (Heading / Parameter / Character) and
  LC/LU relevance.
* Eionet EAGLE vocabulary (CSV export): the element definitions, including their
  "Includes" / "Excludes" notes, thematic domains and parameter units.

Usage:
    uv run --group build python scripts/build_vocabulary.py [BARCODING_DIR] [EIONET_CSV]

Without EIONET_CSV the vocabulary CSV is downloaded from dd.eionet.europa.eu.
"""

import csv
import io
import json
import re
import sys
import urllib.request
from pathlib import Path

import openpyxl

EIONET_CSV_URL = "https://dd.eionet.europa.eu/vocabulary/landcover/eagle/csv"

DEFAULT_DIR = Path(
    r"C:\Users\rosenauer\OneDrive\OneDrive - Umweltbundesamt GmbH\Projekte\EAGLE"
    r"\Task 8_ Use of AI\Barcoding"
)
TEMPLATE = "EAGLE Barcoding Template_3.2_20230829.xlsx"
CHANGELOG = "EAGLE Matrix ChangeLogFile Old3.1.2-New3.2_20240606_corr.xlsx"
OUT = Path(__file__).resolve().parent.parent / "data" / "eagle_vocabulary.json"

BLOCKS = {
    "LCC": "Land Cover Components",
    "LUA": "Land Use Attributes",
    "LCH": "Land Characteristics",
}


def parent_code(code: str) -> str | None:
    if "_" in code:
        return code.rsplit("_", 1)[0]
    if "-" in code:
        return code.split("-", 1)[0]
    return None


def read_metadata(path: Path) -> dict[str, tuple[str | None, str | None]]:
    wb = openpyxl.load_workbook(path, read_only=True)
    meta = {}
    for row in wb["Matrix_Vertical_CLEAN_NEW"].iter_rows(min_row=2, values_only=True):
        if row[1]:
            meta[row[1]] = (row[4], row[5])
    return meta


def clean(text: str) -> str:
    """Repair cp1252 punctuation that arrives as C1 control characters."""
    text = "".join(ch.encode("latin-1").decode("cp1252", errors="replace") if "\x80" <= ch <= "\x9f" else ch for ch in text)
    return text.replace("�", "'").replace("\r\n", "\n").strip()


def split_definition(definition: str) -> tuple[str, list[str], str]:
    """Split a definition into (description, included examples, excludes note)."""
    parts = re.split(r"\n?\s*(Includes?|Excludes?|Applicable for):\s*", definition)
    description, includes, excludes = parts[0].strip(), "", ""
    for heading, body in zip(parts[1::2], parts[2::2]):
        if heading.startswith("Include") or heading.startswith("Applicable"):
            includes += " " + body
        else:
            excludes += " " + body
    terms = []
    for chunk in re.split(r"[,;.]|and|or", re.sub(r"\([^)]*\)|\be\.g\.|\bsuch as\b|\bincluding\b", " ", includes)):
        term = " ".join(chunk.split()).strip(" .")
        if term and len(term.split()) <= 3 and term.lower() not in {"etc", "also", "however", "basically"}:
            terms.append(term)
    return description, terms, " ".join(excludes.split())


def read_eionet(source: str | None) -> dict[str, dict]:
    if source:
        raw = Path(source).read_bytes()
    else:
        request = urllib.request.Request(EIONET_CSV_URL, headers={"User-Agent": "eagle-eye"})
        raw = urllib.request.urlopen(request, timeout=60).read()
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    result = {}
    for row in rows:
        description, includes, excludes = split_definition(clean(row["Definition"]))
        result[row["code"]] = {
            "definition": description,
            "includes": includes,
            "excludes": excludes,
            "domains": [d.strip() for d in row["Thematic_Domain_Context"].split(",") if d.strip()],
            "data_unit": row["data_unit"].strip() or None,
            "is_parameter": row["isParameter"].strip().lower() == "true",
        }
    return result


def main(src: Path, eionet_csv: str | None = None) -> None:
    meta = read_metadata(src / CHANGELOG)
    definitions = read_eionet(eionet_csv)
    wb = openpyxl.load_workbook(src / TEMPLATE, read_only=True)
    concepts = []
    for row in wb["Matrix_Vertical_BarCoding"].iter_rows(min_row=6, values_only=True):
        uri, code, label, level = row[:4]
        if not code:
            continue
        relevance, element_type = meta.get(code, (None, None))
        concepts.append(
            {
                "code": code,
                "uri": uri,
                "label": label.strip(),
                "level": int(level),
                "block": code.split("-")[0],
                "parent": parent_code(code),
                "element_type": element_type,
                "relevance": relevance,
                **definitions[code],
            }
        )
    payload = {
        "source": f"{TEMPLATE} + {CHANGELOG} + Eionet vocabulary CSV",
        "version": "3.2",
        "blocks": BLOCKS,
        "concepts": concepts,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(concepts)} concepts to {OUT}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR, sys.argv[2] if len(sys.argv) > 2 else None)
