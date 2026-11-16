"""The FAO LChS tool's numeric ids (fao_lchs_profile.json, see scripts/extract_fao_profile.py).

The tool joins properties and characteristics to its block library by BlockID / CharacteristicID, not by the name:
a .lchs file with only BlockReference loads its classes, but the elements do not attach to their blocks.
"""

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

PROFILE = Path(__file__).with_name("fao_lchs_profile.json")


@lru_cache(maxsize=1)
def _profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def block_id(reference: Optional[str]) -> Optional[int]:
    return next((b["id"] for b in _profile()["blocks"] if b["reference"] == reference), None)


def characteristic_id(reference: Optional[str]) -> Optional[int]:
    return _profile()["characteristic_ids"].get(reference or "")
