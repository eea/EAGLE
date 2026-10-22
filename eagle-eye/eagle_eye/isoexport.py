"""Export an analysis as ISO 19144-2 LChS XML.

The conversion is done by the eagle-iso-mapper next to this project: EAGLE Eye writes
the class as a column of an EAGLE barcoding matrix (the vertical Excel layout the mapper
reads: element rows with their bar code values), and the mapper turns that matrix into
the LChS XML. Mapping rules (SSSOM crosswalk, presence types) therefore stay in one place.

The mapper writes land cover components (LCC) as LC_Properties and a few land
characteristics (irrigation, rice, hops) as LC_Characteristics. Land use attributes and
other characteristics are read but not written by the mapper; `IsoExport.not_written`
lists them so the export is never silently incomplete.
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
# What LchsXmlGenerator writes for land characteristics (see its generate_xml).
_WRITTEN_CHARACTERISTICS = re.compile(r"irrigation|rice|hops", re.IGNORECASE)


class IsoExportError(Exception):
    pass


@dataclass
class ExportPlan:
    """What of the analysis the LChS XML can carry."""

    to_send: dict[str, str] = field(default_factory=dict)  # element code -> bar code value, for the matrix
    written: list[str] = field(default_factory=list)  # element codes that appear in the XML
    not_written: list[str] = field(default_factory=list)  # "code label (reason)" the mapper cannot express
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
    """Decide, without running the mapper, which elements go into the XML and which cannot."""
    vocab = vocab or load_vocabulary()
    coded, notes = _coded_elements(analysis, vocab)
    plan = ExportPlan(notes=notes)
    for code, bcv in coded.items():
        concept = vocab.get(code)
        label = f"{code} {concept.label}"
        if concept.block == "LCC":
            plan.to_send[code] = bcv
            plan.written.append(code)
        elif concept.block == "LCH" and bcv != "X" and _WRITTEN_CHARACTERISTICS.search(concept.label):
            plan.to_send[code] = bcv
            plan.written.append(code)
        elif concept.block == "LUA":
            plan.not_written.append(f"{label} (land use is not part of the LChS XML the mapper writes)")
        elif bcv == "X":
            plan.not_written.append(f"{label} (an excluded characteristic cannot be expressed)")
        else:
            plan.not_written.append(f"{label} (characteristic not covered by the mapper)")
    return plan


def warm_up() -> None:
    """Import the mapper in the background: its first import takes many seconds."""
    threading.Thread(target=lambda: available() and _mapper(), daemon=True).start()


def to_lchs_xml(analysis: Analysis, vocab: Vocabulary | None = None, class_code: str = "", class_name: str = "") -> IsoExport:
    vocab = vocab or load_vocabulary()
    plan = plan_export(analysis, vocab)
    class_name = class_name.strip() or "EAGLE Eye class"
    class_code = class_code.strip() or re.sub(r"[^A-Za-z0-9]+", "", class_name).upper()[:16] or "CLASS"
    log: list[str] = []
    run = _mapper()
    try:
        xml = run(build_matrix(plan.to_send, vocab, class_code, class_name), SHEET, log.append)
    except Exception as err:  # the mapper raises plain ValueError / KeyError on malformed input
        raise IsoExportError(f"The eagle-iso-mapper could not convert the class: {err}") from err
    return IsoExport(xml, plan)
