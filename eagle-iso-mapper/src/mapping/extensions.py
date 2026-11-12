"""The extension vocabulary (irrigation code lists, characteristic classes): see eagle_iso_extensions.yaml."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

EXTENSIONS_PATH = Path(os.environ.get("EXTENSIONS_CONFIG_PATH") or Path(__file__).with_name("eagle_iso_extensions.yaml"))

IRRIGATION_CLASS = "LC_IrrigationCharacteristic"
FLORISTIC_CLASS = "LC_FloristicAspectsCharacteristic"  # defined by the FAO LChS profile itself


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    with open(EXTENSIONS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for code, attrs in data.get("irrigation", {}).items():
        for key, code_list in (("irrigationType", "IrrigationType"), ("waterSource", "WaterSource")):
            if key in attrs and attrs[key] not in data["code_lists"][code_list]:
                raise ValueError(f"{EXTENSIONS_PATH.name}: {code} uses {attrs[key]!r}, which is not in the {code_list} code list")
    return data


def code_list(name: str) -> Dict[str, str]:
    """Identifier -> definition."""
    return load()["code_lists"][name]


def irrigation(code: Optional[str]) -> Optional[Dict[str, Any]]:
    """Irrigation attributes stated by an EAGLE land characteristic, or None."""
    return load().get("irrigation", {}).get((code or "").strip())


def species(code: Optional[str]) -> Optional[str]:
    return load().get("species", {}).get((code or "").strip())


def characteristic_class(code: Optional[str]) -> str:
    """The characteristic class an EAGLE land characteristic belongs to (longest code prefix wins)."""
    code = (code or "").strip()
    best = ""
    for prefix in load().get("characteristic_classes", {}):
        if (code == prefix or code.startswith(prefix + "_")) and len(prefix) > len(best):
            best = prefix
    return load()["characteristic_classes"][best] if best else load()["default_characteristic_class"]


def states_irrigation(code: Optional[str]) -> bool:
    """True for the concepts the plain LCML subset writes as irrigation (not 'No Irrigation', not the water source)."""
    return bool((irrigation(code) or {}).get("irrigated"))
