"""Export an analysis as ISO 19144-2 LChS XML.

The conversion is done by the eagle-iso-mapper next to this project: EAGLE Eye writes
the class as a column of an EAGLE barcoding matrix (the vertical Excel layout the mapper
reads: element rows with their bar code values), and the mapper turns that matrix into
the LChS XML. Mapping rules (SSSOM crosswalk, presence types) therefore stay in one place.

The mapper decides what the LChS XML carries (land cover, and with its extensions land use
and the land characteristics); EAGLE Eye sends every bar coded element and uses nothing of the
mapper but its pipeline entry point.
"""

import io
import os
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

from .extractor import Analysis
from .vocabulary import Vocabulary, load_vocabulary

ISO_MAPPER_DIR = Path(os.environ.get("EAGLE_ISO_MAPPER_DIR") or Path(__file__).resolve().parents[2] / "eagle-iso-mapper")
SHEET = "EAGLE Eye"

_MAPPER_FILES = {
    "SSSOM_CONFIG_PATH": "src/mapping/eagle_iso_sssom.yaml",
    "MAPPING_CONFIG_PATH": "src/mapping/eagle_iso_sssom.yaml",
    "LINKML_MODEL_PATH": "src/model/eagle-iso-mapping.linkml.yaml",
}
DEFAULT_CLASS_NAME = "Corine class"


class IsoExportError(Exception):
    pass


@dataclass
class ExportPlan:
    """What of the analysis is sent to the mapper."""

    to_send: dict[str, str] = field(default_factory=dict)  # element code -> bar code value, for the matrix
    written: list[str] = field(default_factory=list)  # element codes sent to the mapper
    notes: list[str] = field(default_factory=list)


@dataclass
class IsoExport:
    xml: bytes
    plan: ExportPlan


def available() -> bool:
    return (ISO_MAPPER_DIR / "src" / "mapping" / "eagle_to_iso.py").exists()


def _mapper():
    """Import the mapper's pipeline (it expects to run from its own project folder)."""
    if not available():
        raise IsoExportError(
            f"The eagle-iso-mapper project was not found at {ISO_MAPPER_DIR}. "
            "Keep it next to eagle-eye or set EAGLE_ISO_MAPPER_DIR."
        )
    for variable, relative in _MAPPER_FILES.items():
        os.environ.setdefault(variable, str(ISO_MAPPER_DIR / relative))
    if str(ISO_MAPPER_DIR) not in sys.path:
        sys.path.append(str(ISO_MAPPER_DIR))
    from src.mapping.eagle_to_iso import run_eagle_to_iso_mapping

    return run_eagle_to_iso_mapping


def _coded_elements(analysis: Analysis, vocab: Vocabulary) -> tuple[dict[str, str], list[str]]:
    """Bar code value per element: {code: bcv}. An element both stated and excluded keeps the stated value."""
    notes, chosen = [], {}
    for entry in analysis.entries:
        if not entry.code or entry.bcv is None:
            continue
        if entry.code in chosen:
            keep = entry.bcv if chosen[entry.code] == "X" else chosen[entry.code]
            notes.append(f"{vocab.get(entry.code).label}: stated and excluded in the text; kept bar code value {keep}.")
            chosen[entry.code] = keep
        else:
            chosen[entry.code] = entry.bcv
    return chosen, notes


def build_matrix(coded: dict[str, str], vocab: Vocabulary, class_code: str, class_name: str) -> openpyxl.Workbook:
    """A one-class EAGLE barcoding matrix in the vertical layout the mapper reads."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET
    ws["A1"], ws["E1"] = "Class Code* (If continuous dataset, enter a short name)", class_code
    ws["A2"], ws["E2"] = "Name*", class_name
    ws["A3"], ws["A4"] = "100% EAGLE Compliant*", "Colour Code"
    for column, title in enumerate(("URI", "Code", "Label", "Level", "Barcode", "Factor"), 1):
        ws.cell(row=5, column=column, value=title)
    row = 6
    for concept in vocab.concepts:  # matrix order
        if concept.code in coded:
            for column, value in enumerate((concept.uri, concept.code, concept.label, concept.level, coded[concept.code]), 1):
                ws.cell(row=row, column=column, value=value)
            row += 1
    return wb


def plan_export(analysis: Analysis, vocab: Vocabulary | None = None) -> ExportPlan:
    """The elements to send to the mapper: every bar coded one. An element both stated and excluded keeps the stated value."""
    vocab = vocab or load_vocabulary()
    coded, notes = _coded_elements(analysis, vocab)
    return ExportPlan(to_send=dict(coded), written=list(coded), notes=notes)


def warm_up() -> None:
    """Import the mapper in the background: its first import takes many seconds."""
    threading.Thread(target=lambda: available() and _mapper(), daemon=True).start()


def to_lchs_xml(
    analysis: Analysis,
    vocab: Vocabulary | None = None,
    class_code: str = "",
    class_name: str = "",
) -> IsoExport:
    vocab = vocab or load_vocabulary()
    plan = plan_export(analysis, vocab)
    class_name = class_name.strip() or DEFAULT_CLASS_NAME
    class_code = class_code.strip() or re.sub(r"[^A-Za-z0-9]+", "", class_name).upper()[:16] or "CLASS"
    log: list[str] = []
    run = _mapper()
    try:
        xml = run(build_matrix(plan.to_send, vocab, class_code, class_name), SHEET, log.append)
    except Exception as err:  # the mapper raises plain ValueError / KeyError on malformed input
        raise IsoExportError(f"The eagle-iso-mapper could not convert the class: {err}") from err
    return IsoExport(xml, plan)
