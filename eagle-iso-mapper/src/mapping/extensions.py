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
    for value, code in data.get("reverse_irrigation_type", {}).items():
        if value not in data["code_lists"]["IrrigationType"] or code not in data["irrigation"]:
            raise ValueError(f"{EXTENSIONS_PATH.name}: reverse_irrigation_type {value!r} -> {code!r} is not a known value and code")
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


def irrigation_label(code: Optional[str]) -> Optional[str]:
    return (irrigation(code) or {}).get("label")


def irrigation_codes(irrigated: Optional[bool], irrigation_types, water_sources, precluded: bool = False) -> list[str]:
    """EAGLE codes for what an LC_IrrigationCharacteristic states (XML -> EAGLE); the inverse of the table above.

    Identifiers are compared ignoring case (the FAO profile writes "Sprinkler"). Values with no EAGLE concept
    of their own map to the nearest one; a water source EAGLE does not know is dropped."""
    data = load()
    by_type = {a["irrigationType"].lower(): code for code, a in data.get("irrigation", {}).items() if "irrigationType" in a}
    by_type.update({v.lower(): code for v, code in data.get("reverse_irrigation_type", {}).items()})
    by_source = {a["waterSource"].lower(): code for code, a in data.get("irrigation", {}).items() if "waterSource" in a}
    codes = [by_type[t.strip().lower()] for t in irrigation_types if t and t.strip().lower() in by_type]
    codes += [by_source[w.strip().lower()] for w in water_sources if w and w.strip().lower() in by_source]
    if irrigated is False and not codes:
        codes = ["LCH-5_1_4_5_2" if precluded else "LCH-5_1_4_5_1"]  # "not irrigated" is "No Irrigation", or irrigation excluded
    return list(dict.fromkeys(codes))


def species_code(name: Optional[str]) -> Optional[str]:
    """The EAGLE code of a floristic species name (XML -> EAGLE), compared ignoring case."""
    wanted = (name or "").strip().lower()
    return next((code for code, species_name in load().get("species", {}).items() if species_name.lower() == wanted), None)
