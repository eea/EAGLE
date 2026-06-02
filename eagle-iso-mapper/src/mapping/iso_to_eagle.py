import io
import xml.etree.ElementTree as ET
import openpyxl
import os
import re
import yaml
from typing import List
from src.config import settings
from src.python.generated.eagle_iso_models import (
    CorineClass,
    LandCoverComponent,
    LcmlPresenceType,
    EagleLccType,
    EagleMatrixValue
)

class LchsXmlParser:
    """Parses raw data and applies semantic mapping to EAGLE.
    Supports both hierarchical (mock) and relational (official) LChS XML structures."""

    def __init__(self, xml_bytes: bytes):
        xml_str = xml_bytes.decode('utf-8', errors='ignore')
        # Remove namespaces for robust parsing
        xml_str = re.sub(r'\sxmlns="[^"]+"', '', xml_str, count=1)
        self.mappings = self._load_mappings()
        self.root = ET.fromstring(xml_str)

        for elem in self.root.iter():
            if '}' in elem.tag:
                elem.tag = elem.tag.split('}', 1)[1]
            if ':' in elem.tag:
                elem.tag = elem.tag.split(':', 1)[1]

    def _load_mappings(self):
        if not settings.MAPPING_CONFIG_PATH.exists():
            os.makedirs(settings.MAPPING_CONFIG_PATH.parent, exist_ok=True)
            with open(settings.MAPPING_CONFIG_PATH, "w") as f:
                yaml.dump({}, f)
            return {}

        with open(settings.MAPPING_CONFIG_PATH, "r") as f:
            return yaml.safe_load(f) or {}

    def _resolve_alias(self, search_str: str) -> str:
        """checks if str is contained in any EAGLE alias mapping"""
        for eagle_class, aliases in self.mappings.items():
            if search_str in aliases or search_str == eagle_class:
                return eagle_class
        return search_str

    def _map_eagle_value(self, presence_str: str):
        """Translates ISO Presence Type to EAGLE Barcode."""
        mapping = {
            "Fixed": "3",
            "Exclusive": "2",
            "ConditionalTemporal": "1",
            "Conditional Temporal": "1" # LChS uses a space here
        }
        for key, val in mapping.items():
            if key.lower() in presence_str.lower():
                return val
        return None

    def _map_eagle_factor(self, c_min, c_max):
        """Translates ISO Min/Max back to EAGLE factor."""
        if c_min == 30 and c_max == 80:
            return "055"
        if c_min is not None and c_max is not None:
            # 0 to 100 is usually the default for "unspecified", avoid writing it as factor '50'
            if c_min == 0 and c_max == 100:
                return None
            return str(int((c_min + c_max) / 2))
        return None

    def extract_classes(self, log_callback, use_fuzzy: bool, force_hierarchical: bool) -> List[CorineClass]:
        # Logik: Wenn forced, dann hierarchisch, sonst Autodetect
        if force_hierarchical or (self.root.find('.//LegendClass') is not None and self.root.find('.//LC_Class') is None):
            log_callback("ℹ️ Parsing in Hierarchical Mode...")
            return self._extract_lchs_hierarchical(log_callback, use_fuzzy)
        else:
            log_callback("ℹ️ Parsing in Relational Mode...")
            return self._extract_lchs_relational(log_callback, use_fuzzy)

    def _fuzzy_match_enum(self, enum_class, search_str: str, use_fuzzy: bool):
        if not search_str: return None

        # 1. Alias Check (YAML)
        resolved = self._resolve_alias(search_str)
        if resolved in enum_class.__members__:
            return enum_class[resolved]

        # 2. Fuzzy Matching
        if not use_fuzzy:
            return enum_class.get(search_str)

        ##print("using fuzzy matching for " + search_str + " in " + enum_class.__name__ + " ...")

        # Cleanup: all lowercase, remove blanks, underscore, prefix LC_
        clean = search_str.lower().replace(" ", "").replace("lc_", "").replace("_", "")

        # build a list of all variants to test against
        # also include standard and Latin Plural forms
        variants = {
            clean,
            clean + "s",
            clean.rstrip("s"),
            clean.replace("ae", "a") # Für Algae/Alga
        }

        ##print("  > variants: " + str(variants))
        ##print("  > enum members: " + str(enum_class.__members__.keys()))

        for name, member in enum_class.__members__.items():
            if name.lower() in variants:
                return member
        return None

    def _extract_lchs_relational(self, log_callback, use_fuzzy: bool) -> List[CorineClass]:
        """Parses the complex ID-linked relational structure from the official LChS Tool."""
        classes = {}
        class_to_hp = {}
        hp_to_stratum = {}
        stratum_to_props = {}

        # 1. Parse Classes
        for lc_class in self.root.findall('.//LC_Class'):
            c_id = lc_class.findtext('class_id')
            c_code_raw = lc_class.findtext('class_map_code')
            c_name = lc_class.findtext('class_name')

            if c_id and c_code_raw and c_name:
                c_id = c_id.strip() # Safety first!
                clean_code = c_code_raw.replace(" ", "").strip()
                classes[c_id] = CorineClass(class_code=clean_code, class_name=c_name.strip(), components=[])
                class_to_hp[c_id] = []

        # 2. Parse Horizontal Patterns mapping
        for hp in self.root.findall('.//LC_HorizontalPatterns'):
            c_id = hp.findtext('class_id')
            hp_id = hp.findtext('horizontal_pattern_id')
            if c_id and hp_id:
                class_to_hp[c_id.strip()].append(hp_id.strip())
                hp_to_stratum[hp_id.strip()] = []

        # 3. Parse Strata mapping
        for stratum in self.root.findall('.//LC_Strata'):
            hp_id = stratum.findtext('HPID')
            stratum_id = stratum.findtext('stratumID')
            if hp_id and stratum_id:
                hp_to_stratum[hp_id.strip()].append(stratum_id.strip())
                stratum_to_props[stratum_id.strip()] = []

        # 4. Parse Properties
        for prop in self.root.findall('.//LC_Properties'):
            stratum_id = prop.findtext('StratumID')
            if stratum_id and stratum_id.strip() in stratum_to_props:
                block_ref = prop.findtext('BlockReference')
                presence_str = prop.findtext('elementPresenceType')

                covers = []
                for c in prop.findall('cover'):
                    try:
                        covers.append(int(float(c.text)))
                    except (ValueError, TypeError):
                        pass

                c_min = covers[0] if len(covers) > 0 else None
                c_max = covers[1] if len(covers) > 1 else c_min

                stratum_to_props[stratum_id].append({
                    'block_ref': block_ref,
                    'presence_str': presence_str,
                    'c_min': c_min,
                    'c_max': c_max
                })

        log_callback(f"Found Strata with properties: { {k: len(v) for k, v in stratum_to_props.items() if v} }")

        # 5. Assemble everything into Pydantic Objects
        # Map LChS internal BlockReferences to our EAGLE LinkML concepts
        block_ref_mapping = {
            "LC_BuiltUpSurface": EagleLccType.SealedArtificialSurface,
            "LC_VegetationElement": EagleLccType.BioticVegetation,
            "LC_Building": EagleLccType.SpecificBuildings,
            "LC_BareSoil": EagleLccType.BareSoil,
            "LC_Graminoid": EagleLccType.Graminoids,
            "LC_NaturalSurfaceElement": EagleLccType.NaturalSurfaces
        }

        extracted = []
        for c_id, corine_class in classes.items():
            log_callback(f"DEBUG: processing class {c_id} ({corine_class.class_code})")

            for hp_id in class_to_hp.get(c_id, []):
                for stratum_id in hp_to_stratum.get(hp_id, []):
                    for prop in stratum_to_props.get(stratum_id, []):

                        block_ref = prop['block_ref']
                        presence_str = prop['presence_str']
                        c_min = prop['c_min']
                        c_max = prop['c_max']

                        if not block_ref or not presence_str:
                            continue

                        lcc_type = block_ref_mapping.get(block_ref)
                        if not lcc_type:
                            lcc_type = self._fuzzy_match_enum(EagleLccType, block_ref, use_fuzzy)

                        if not lcc_type:
                            log_callback(f"⚠️️ Unmapped BlockReference '{block_ref}'. Skipping.")
                            continue

                        presence = self._fuzzy_match_enum(LcmlPresenceType, presence_str, use_fuzzy)
                        if not presence:
                            log_callback(f"⚠️ Unmapped PresenceType '{presence_str}'. Skipping.")
                            continue

                        eagle_val_str = self._map_eagle_value(presence_str)
                        if not eagle_val_str:
                            # Typically happens on 'Precluded' values. We skip them for EAGLE.
                            continue

                        factor = self._map_eagle_factor(c_min, c_max)

                        if c_min == 0 and c_max == 100:
                            c_min, c_max = None, None

                        try:
                            comp = LandCoverComponent(
                                lcc_type=lcc_type,
                                presence_type=presence,
                                eagle_value=EagleMatrixValue(eagle_val_str),
                                eagle_factor=factor,
                                coverage_min=c_min,
                                coverage_max=c_max
                            )
                            corine_class.components.append(comp)
                        except Exception as e:
                            log_callback(f"⚠️ Error creating component {block_ref}: {e}")

            # Deduplicate components (Relational XML often maps the same component multiple times)
            unique_comps = {}
            for comp in corine_class.components:
                comp_type = getattr(comp.lcc_type, 'name', str(comp.lcc_type))
                if comp_type not in unique_comps or comp.eagle_factor is not None:
                    unique_comps[comp_type] = comp

            corine_class.components = list(unique_comps.values())
            extracted.append(corine_class)

        return extracted

    def _extract_lchs_hierarchical(self, log_callback, use_fuzzy: bool) -> List[CorineClass]:
        """Parses our simplified, generated XML."""
        extracted_classes = []
        for legend_class in self.root.findall('.//LegendClass'):
            class_code = legend_class.find('Code')
            class_name = legend_class.find('Name')

            if class_code is None or class_name is None:
                continue

            # Sanitize the class code: remove all spaces
            clean_code = class_code_node.text.replace(" ", "").strip()
            class_name = class_name_node.text.strip() if class_name_node.text else ""

            components = []
            for element in legend_class.findall('.//LC_Element'):
                try:
                    type_str = element.get('type')
                    lcc_type = self._fuzzy_match_enum(EagleLccType, type_str, use_fuzzy)
                    if not lcc_type: continue

                    presence_node = element.find('PresenceType')
                    presence, eagle_val_str = None, None

                    if presence_node is not None:
                        presence = self._fuzzy_match_enum(LcmlPresenceType, presence_node.text, use_fuzzy)
                        if presence:
                            eagle_val_str = self._map_eagle_value(str(presence.value) if hasattr(presence, 'value') else str(presence))

                    if not eagle_val_str: continue

                    cov_min_node = element.find('CoverMin')
                    cov_max_node = element.find('CoverMax')
                    c_min = int(cov_min_node.text) if (cov_min_node is not None and cov_min_node.text) else None
                    c_max = int(cov_max_node.text) if (cov_max_node is not None and cov_max_node.text) else None

                    factor = self._map_eagle_factor(c_min, c_max)

                    comp = LandCoverComponent(
                        lcc_type=lcc_type, presence_type=presence, eagle_value=EagleMatrixValue(eagle_val_str),
                        eagle_factor=factor, coverage_min=c_min, coverage_max=c_max
                    )
                    components.append(comp)
                except Exception as e:
                    pass

            extracted_classes.append(CorineClass(
                class_code=clean_code,
                class_name=class_name,
                components=components
            ))

        return extracted_classes


class EagleExcelExporter:
    """Writes the validated Pydantic models into the EAGLE Matrix Excel structure."""
    def __init__(self):
        self.workbook = openpyxl.Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "EAGLE Matrix Barcoding"
        self._setup_headers()

    def _setup_headers(self):
        # Define ALL columns you want to export
        headers = [
            "CORINE Code",
            "Class Name",
            "Sealed Artificial Surface (Value)", "Sealed Artificial Surface (Factor)",
            "Biotic Vegetation (Value)", "Biotic Vegetation (Factor)",
            "Trees (Value)", "Trees (Factor)",
            "Shrubs (Value)", "Shrubs (Factor)",
            "Graminoids (Value)", "Graminoids (Factor)",
            "LichenMosses (Value)", "LichenMosses (Factor)"
        ]
        for col_idx, header in enumerate(headers, 1):
            cell = self.sheet.cell(row=1, column=col_idx, value=header)
            cell.font = openpyxl.styles.Font(bold=True)

    def generate(self, eagle_classes: List[CorineClass]) -> bytes:
        row = 2

        # Map the Enum types to the respective Excel column pairs (Value, Factor)
        col_mapping = {
            EagleLccType.SealedArtificialSurface: (3, 4),
            EagleLccType.BioticVegetation: (5, 6),
            EagleLccType.Trees: (7, 8),
            EagleLccType.Shrubs: (9, 10),
            EagleLccType.Graminoids: (11, 12),
            EagleLccType.LichenMosses: (13, 14)
        }

        for e_class in eagle_classes:
            self.sheet.cell(row=row, column=1, value=e_class.class_code)
            self.sheet.cell(row=row, column=2, value=e_class.class_name)

            for comp in e_class.components:
                comp_type_name = getattr(comp.lcc_type, 'name', str(comp.lcc_type))

                for enum_key, cols in col_mapping.items():
                    if comp_type_name == getattr(enum_key, 'name', str(enum_key)):
                        val_col, factor_col = cols

                        if comp.eagle_value:
                            eagle_val = str(comp.eagle_value).replace("EagleMatrixValue.", "")
                            self.sheet.cell(row=row, column=val_col, value=int(eagle_val))

                        if comp.eagle_factor:
                            self.sheet.cell(row=row, column=factor_col, value=str(comp.eagle_factor))
                        break
            row += 1

        output = io.BytesIO()
        self.workbook.save(output)
        return output.getvalue()


def run_iso_to_eagle_mapping(xml_bytes: bytes, log_callback, use_fuzzy: bool = False, force_hierarchical: bool = False) -> bytes:
    log_callback("Initializing robust LchsXmlParser...")
    parser = LchsXmlParser(xml_bytes)

    log_callback("Extracting and semantically mapping data...")
    validated_objects = parser.extract_classes(log_callback, use_fuzzy, force_hierarchical)

    if not validated_objects:
        log_callback("❌ Error: No valid data could be extracted from the XML. Please check the file structure.")
    else:
        log_callback(f"Successfully processed {len(validated_objects)} Corine classes. Generating Excel Matrix...")

    exporter = EagleExcelExporter()
    return exporter.generate(validated_objects)