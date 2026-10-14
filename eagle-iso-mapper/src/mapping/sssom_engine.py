import os
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
import pandas as pd
import yaml

import sssom
from sssom.parsers import from_sssom_dataframe, to_mapping_set_document
from sssom.util import MappingSetDataFrame

from src.config import settings
from src.python.generated.eagle_iso_models import (
    BarCodeValueEnum,
    ISOPresenceEnum
)

class SSSOMResolver:
    """
    Manages SSSOM mapping tables for EAGLE <-> ISO-19144 crosswalk using python sssom library.
    Provides bidirectional resolution, CURIE normalization, and fuzzy fallback.
    """

    def __init__(self, sssom_path: Optional[Path] = None):
        self.sssom_path = sssom_path or settings.SSSOM_CONFIG_PATH
        self.msdf: Optional[MappingSetDataFrame] = None
        self.forward_map: Dict[str, Dict[str, Any]] = {}
        self.reverse_map: Dict[str, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {}
        self.prefix_map: Dict[str, str] = {}
        self.load()

    def load(self):
        """Loads and parses the SSSOM YAML file using python sssom."""
        if not self.sssom_path.exists():
            raise FileNotFoundError(f"SSSOM file not found: {self.sssom_path}")

        with open(self.sssom_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}

        mappings_list = raw_data.get("mappings", [])
        self.metadata = {k: v for k, v in raw_data.items() if k != "mappings"}
        self.prefix_map = self.metadata.pop("prefixes", {
            "eagle": "https://dd.eionet.europa.eu/vocabulary/landcover/eagle/",
            "iso": "https://standards.isotc211.org/19144/",
            "skos": "http://www.w3.org/2004/02/skos/core#"
        })

        df = pd.DataFrame(mappings_list) if mappings_list else pd.DataFrame(columns=[
            "subject_id", "subject_label", "predicate_id", "object_id", "object_label"
        ])

        # Instantiate official MappingSetDataFrame from sssom library
        self.msdf = from_sssom_dataframe(df, prefix_map=self.prefix_map, meta=self.metadata)

        # Build bidirectional indexing
        self._rebuild_indices()

    def _normalize_curie(self, curie_or_id: str) -> str:
        """Strips prefix (eagle:, iso:) and whitespace, lowercase for keying."""
        if not curie_or_id:
            return ""
        s = str(curie_or_id).strip()
        if ":" in s:
            s = s.split(":", 1)[1]
        return s

    def _rebuild_indices(self):
        self.forward_map.clear()
        self.reverse_map.clear()

        if self.msdf is None or self.msdf.df.empty:
            return

        for _, row in self.msdf.df.iterrows():
            sub_id = str(row.get("subject_id", ""))
            sub_norm = self._normalize_curie(sub_id)
            obj_id = str(row.get("object_id", ""))
            obj_norm = self._normalize_curie(obj_id)
            sub_label = str(row.get("subject_label", ""))
            obj_label = str(row.get("object_label", ""))
            pred = str(row.get("predicate_id", ""))

            entry = {
                "subject_id": sub_id,
                "subject_label": sub_label,
                "predicate_id": pred,
                "object_id": obj_id,
                "object_label": obj_label
            }

            # Forward index
            self.forward_map[sub_id] = entry
            self.forward_map[sub_norm] = entry
            if sub_label:
                self.forward_map[sub_label.lower().strip()] = entry

            # Reverse index (preserve exactMatch and canonical primary mappings)
            existing = self.reverse_map.get(obj_id)
            should_update = True
            if existing:
                if existing.get("predicate_id") == "skos:exactMatch" and pred != "skos:exactMatch":
                    should_update = False
                elif existing.get("subject_id") == "eagle:BCV-2" and sub_id == "eagle:BCV-5":
                    should_update = False

            if should_update:
                self.reverse_map[obj_id] = entry
                self.reverse_map[obj_norm] = entry
                if obj_label:
                    self.reverse_map[obj_label.lower().strip()] = entry

            # Add common ISO variations (e.g. LC_BuiltUpSurface -> LC_BuildUpSurface)
            if "buildupsurface" in obj_norm.lower() or "builtupsurface" in obj_norm.lower():
                self.reverse_map["LC_BuiltUpSurface"] = entry
                self.reverse_map["LC_BuildUpSurface"] = entry
            if "vegetation" in obj_norm.lower():
                self.reverse_map["LC_VegetationElement"] = entry
            if "soil" in obj_norm.lower():
                self.reverse_map["LC_BareSoil"] = entry
                self.reverse_map["LC_Soil"] = entry
            if "tree" in obj_norm.lower():
                self.reverse_map["LC_Trees"] = entry
                self.reverse_map["LC_Tree"] = entry
            if "shrub" in obj_norm.lower():
                self.reverse_map["LC_Shrubs"] = entry
                self.reverse_map["LC_Shrub"] = entry
            if "naturalsurface" in obj_norm.lower():
                self.reverse_map["LC_NaturalSurfaceElement"] = entry
                self.reverse_map["LC_NaturalSurfaces"] = entry
            if "lichen" in obj_norm.lower() or "moss" in obj_norm.lower():
                self.reverse_map["LC_LichenAndMoss"] = entry
                self.reverse_map["LC_LichenAndMosses"] = entry
            if "building" in obj_norm.lower():
                self.reverse_map["LC_Building"] = entry
                self.reverse_map["LC_Buildings"] = entry
            if "graminoid" in obj_norm.lower():
                self.reverse_map["LC_Graminoid"] = entry
                self.reverse_map["LC_Graminoids"] = entry

    def resolve_eagle_to_iso(self, eagle_id_or_code: str, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolves an EAGLE concept to an ISO concept."""
        if not eagle_id_or_code and not label:
            return None

        # 1. Exact match by ID / CURIE
        if eagle_id_or_code in self.forward_map:
            return self.forward_map[eagle_id_or_code]

        norm_id = self._normalize_curie(eagle_id_or_code)
        if norm_id in self.forward_map:
            return self.forward_map[norm_id]

        # 2. Match by Label
        if label:
            clean_lbl = label.lower().strip()
            if clean_lbl in self.forward_map:
                return self.forward_map[clean_lbl]

        # 3. Fuzzy matching on Code or Label
        for key, entry in self.forward_map.items():
            if norm_id and norm_id.lower() == key.lower():
                return entry
            if label and label.lower().replace(" ", "") in key.lower().replace(" ", ""):
                return entry

        return None

    def resolve_iso_to_eagle(self, iso_ref_or_id: str, label: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolves an ISO concept to an EAGLE concept."""
        if not iso_ref_or_id and not label:
            return None

        # 1. Direct match
        if iso_ref_or_id in self.reverse_map:
            return self.reverse_map[iso_ref_or_id]

        norm_id = self._normalize_curie(iso_ref_or_id)
        if norm_id in self.reverse_map:
            return self.reverse_map[norm_id]

        if label:
            clean_lbl = label.lower().strip()
            if clean_lbl in self.reverse_map:
                return self.reverse_map[clean_lbl]

        # 2. Fuzzy clean match
        clean_search = re.sub(r'^(lc_|iso:)', '', iso_ref_or_id, flags=re.IGNORECASE).lower().replace("_", "").replace(" ", "")
        for key, entry in self.reverse_map.items():
            clean_key = re.sub(r'^(lc_|iso:)', '', key, flags=re.IGNORECASE).lower().replace("_", "").replace(" ", "")
            if clean_search == clean_key or clean_search == clean_key.rstrip("s"):
                return entry

        return None

    def map_bcv_to_presence(self, barcode_val: Any) -> ISOPresenceEnum:
        """Maps EAGLE Bar Code Value to ISO Presence Enum."""
        val_str = str(barcode_val).strip() if barcode_val is not None else "1"

        # Check in SSSOM index
        for prefix in [f"eagle:BCV-{val_str}", f"BCV-{val_str}", f"BCV_{val_str}"]:
            entry = self.forward_map.get(prefix)
            if entry:
                obj_id = self._normalize_curie(entry["object_id"])
                # Extract enum name (e.g. PresenceType_Fixed -> Fixed)
                enum_name = obj_id.replace("PresenceType_", "")
                if enum_name in ISOPresenceEnum.__members__:
                    return ISOPresenceEnum[enum_name]

        # Fallback heuristics
        if val_str in ["3", "BCV_3"]:
            return ISOPresenceEnum.Fixed
        elif val_str in ["2", "5", "BCV_2", "BCV_5"]:
            return ISOPresenceEnum.Exclusive
        elif val_str in ["1", "BCV_1"]:
            return ISOPresenceEnum.Conditional
        elif val_str.upper() in ["X", "BCV_X"]:
            return ISOPresenceEnum.Precluded if "Precluded" in ISOPresenceEnum.__members__ else ISOPresenceEnum.Exclusive

        return ISOPresenceEnum.Conditional

    def map_presence_to_bcv(self, presence_val: Any) -> BarCodeValueEnum:
        """Maps ISO Presence Type back to EAGLE BarCodeValueEnum."""
        if not presence_val:
            return BarCodeValueEnum.BCV_1

        val_str = getattr(presence_val, "value", str(presence_val)).strip()

        # Check in SSSOM reverse index
        for prefix in [f"iso:PresenceType_{val_str}", f"PresenceType_{val_str}", val_str]:
            entry = self.reverse_map.get(prefix)
            if entry:
                sub_id = self._normalize_curie(entry["subject_id"]) # e.g. BCV-3
                sub_enum = sub_id.replace("-", "_")
                if sub_enum in BarCodeValueEnum.__members__:
                    return BarCodeValueEnum[sub_enum]

        # Fallback heuristics
        lower_p = val_str.lower()
        if "fix" in lower_p:
            return BarCodeValueEnum.BCV_3
        elif "exclu" in lower_p:
            return BarCodeValueEnum.BCV_2
        elif "cond" in lower_p or "temporal" in lower_p or "option" in lower_p:
            return BarCodeValueEnum.BCV_1
        elif "preclud" in lower_p:
            return BarCodeValueEnum.BCV_X

        return BarCodeValueEnum.BCV_1

    def factor_to_coverage(self, factor_val: Any) -> Tuple[Optional[int], Optional[int]]:
        """Maps EAGLE Factor back to Min/Max cover thresholds."""
        if factor_val is None:
            return None, None

        f_str = str(factor_val).strip()
        if f_str in ["0.55", "055", "55"]:
            return 30, 80
        elif f_str in ["0.75", "075", "75", "075_plus"]:
            return 75, 100
        elif f_str in ["0.875", "87.5", "88"]:
            return 75, 100

        try:
            val = float(f_str)
            if val < 1.0 and val > 0:
                val = val * 100
            int_val = int(round(val))
            return max(0, int_val - 15), min(100, int_val + 15)
        except (ValueError, TypeError):
            return None, None

    def coverage_to_factor(self, c_min: Optional[int], c_max: Optional[int]) -> Optional[str]:
        """Maps Min/Max cover thresholds back to EAGLE Factor."""
        if c_min is None and c_max is None:
            return None
        if c_min == 30 and c_max == 80:
            return "055"
        if c_min == 75 and c_max == 100:
            return "075"
        if c_min == 0 and c_max == 100:
            return None

        if c_min is not None and c_max is not None:
            avg = int((c_min + c_max) / 2)
            return f"{avg:02d}"
        if c_min is not None:
            return f"{c_min:02d}"
        return None

# Global instance for shared use
sssom_resolver = SSSOMResolver()
