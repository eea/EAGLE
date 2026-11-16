"""The EAGLE concepts (code, Eionet URI, label, level) behind the matrix the reverse direction writes.

The data is the shared EAGLE vocabulary JSON: a small bundled extract (eagle_concepts.json, see
scripts/extract_eagle_concepts.py), or the full file named by the environment variable EAGLE_VOCABULARY.
Without it the matrix still has every row, just without URI and with the label and level of the file itself.
"""

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

BUNDLED = Path(__file__).with_name("eagle_concepts.json")
SECTIONS = {"LCC": 0, "LUA": 1, "LCH": 2}


@lru_cache(maxsize=1)
def load() -> Dict[str, Dict[str, Any]]:
    """code -> {uri, label, level}."""
    path = Path(os.environ.get("EAGLE_VOCABULARY") or BUNDLED)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {c["code"]: c for c in data["concepts"]}


def lookup(code: Optional[str]) -> Optional[Dict[str, Any]]:
    return load().get((code or "").strip())


def level_of(code: str) -> int:
    """The level of an EAGLE code: the number of its segments (LCC-1_2_2_2 is level 4, the segment LCC level 0)."""
    return len(code.split("-", 1)[1].split("_")) if "-" in code else 0


def order_key(code: str) -> Tuple[int, Tuple[int, ...], str]:
    """The order of the EAGLE matrix: section (LCC, LUA, LCH), then the numeric segments of the code, so a parent
    comes right before its children (LCC-2_2, LCC-2_2_1, LCC-2_2_1_1, LCC-2_2_2) and LCH-5_1_2 before LCH-5_1_10."""
    section = SECTIONS.get(code[:3].upper(), len(SECTIONS))
    tail = code.split("-", 1)[1] if "-" in code else ""
    numbers = tuple(int(part) if part.isdigit() else 10**6 for part in re.split(r"_", tail) if part)
    return section, numbers, code
