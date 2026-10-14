import io
import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict, Any, Tuple
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from src.python.generated.eagle_iso_models import (
    LandUnit,
    LandCoverComponent,
    AbioticComponent,
    BioticComponent,
    WaterComponent,
    LandUseAttribute,
    LandCharacteristic,
    BarCodeValueEnum,
    ISOPresenceEnum,
    FunctionalRelationshipEnum,
    TemporalRelationshipEnum
)
from src.mapping.sssom_engine import sssom_resolver


class LchsXmlParser:
    """
    Parses LChS / ISO 19144 XML (relational or hierarchical) into validated LandUnit objects.
    Uses SSSOM crosswalk for reverse mapping from ISO block references to EAGLE concepts.
    """

    def __init__(self, xml_bytes: bytes, log_callback=print):
        self.log = log_callback
        xml_str = xml_bytes.decode("utf-8", errors="ignore")
        # Strip default xmlns to simplify XPath handling
        xml_str = re.sub(r'\sxmlns="[^"]+"', '', xml_str, count=1)
        self.root = ET.fromstring(xml_str)

        # Remove XML namespaces from tags
        for elem in self.root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]
            if ":" in elem.tag:
                elem.tag = elem.tag.split(":", 1)[1]

    def extract_land_units(self, use_fuzzy: bool = True, force_hierarchical: bool = False) -> List[LandUnit]:
        if force_hierarchical or (self.root.find(".//LegendClass") is not None and self.root.find(".//LC_Class") is None):
            self.log("Parsing ISO XML in Hierarchical Mode...")
            return self._extract_hierarchical(use_fuzzy)
        else:
            self.log("Parsing ISO XML in Relational Mode (official LChS structure)...")
            return self._extract_relational(use_fuzzy)

    def _extract_relational(self, use_fuzzy: bool) -> List[LandUnit]:
        classes: Dict[str, Dict[str, Any]] = {}
        class_to_hp: Dict[str, List[str]] = {}
        hp_to_stratum: Dict[str, List[str]] = {}
        stratum_to_props: Dict[str, List[Dict[str, Any]]] = {}
        stratum_to_chars: Dict[str, List[Dict[str, Any]]] = {}

        # 1. Parse Classes
        for lc_class in self.root.findall(".//LC_Class"):
            c_id = lc_class.findtext("class_id")
            c_code_raw = lc_class.findtext("class_map_code")
            c_name = lc_class.findtext("class_name")

            if c_id and c_name:
                c_id_clean = c_id.strip()
                code_clean = (c_code_raw or f"C{c_id_clean}").replace(" ", "").strip()
                classes[c_id_clean] = {
                    "id": code_clean,
                    "name": c_name.strip(),
                    "land_cover_components": [],
                    "land_use_attributes": [],
                    "land_characteristics": []
                }
                class_to_hp[c_id_clean] = []

        # 2. Horizontal Patterns
        for hp in self.root.findall(".//LC_HorizontalPatterns"):
            c_id = hp.findtext("class_id")
            hp_id = hp.findtext("horizontal_pattern_id")
            if c_id and hp_id:
                c_key = c_id.strip()
                hp_key = hp_id.strip()
                if c_key in class_to_hp:
                    class_to_hp[c_key].append(hp_key)
                hp_to_stratum[hp_key] = []

        # 3. Strata
        for stratum in self.root.findall(".//LC_Strata"):
            hp_id = stratum.findtext("HPID")
            stratum_id = stratum.findtext("stratumID")
            if hp_id and stratum_id:
                hp_key = hp_id.strip()
                st_key = stratum_id.strip()
                if hp_key in hp_to_stratum:
                    hp_to_stratum[hp_key].append(st_key)
                stratum_to_props[st_key] = []
                stratum_to_chars[st_key] = []

        # 4. Properties (LC_Properties)
        for prop in self.root.findall(".//LC_Properties"):
            stratum_id = prop.findtext("StratumID")
            if stratum_id:
                st_key = stratum_id.strip()
                block_ref = prop.findtext("BlockReference")
                presence_str = prop.findtext("elementPresenceType")

                covers = []
                for c in prop.findall("cover"):
                    try:
                        covers.append(int(float(c.text)))
                    except (ValueError, TypeError):
                        pass

                c_min = covers[0] if len(covers) > 0 else None
                c_max = covers[1] if len(covers) > 1 else c_min

                if st_key not in stratum_to_props:
                    stratum_to_props[st_key] = []

                stratum_to_props[st_key].append({
                    "block_ref": block_ref,
                    "presence_str": presence_str,
                    "c_min": c_min,
                    "c_max": c_max
                })

        # 5. Characteristics (LC_Characteristics)
        for char in self.root.findall(".//LC_Characteristics"):
            stratum_id = char.findtext("StratumID")
            if stratum_id:
                st_key = stratum_id.strip()
                if st_key not in stratum_to_chars:
                    stratum_to_chars[st_key] = []
                stratum_to_chars[st_key].append({
                    "ref": char.findtext("CharacteristicReference"),
                    "label": char.findtext("CharacteristicLabel"),
                    "irrigation_type": char.findtext("irrigationType"),
                    "species_name": char.findtext("speciesName")
                })

        # 6. Map to LandUnit Pydantic objects using SSSOM
        land_units: List[LandUnit] = []
        for c_id, class_dict in classes.items():
            self.log(f"Processing ISO class {c_id}: {class_dict['id']} ({class_dict['name']})")

            # Collect all strata belonging to this class
            associated_strata = []
            for hp_id in class_to_hp.get(c_id, []):
                associated_strata.extend(hp_to_stratum.get(hp_id, []))

            # If no strata mapped explicitly, fallback to stratum_id == c_id
            if not associated_strata and c_id in stratum_to_props:
                associated_strata = [c_id]

            components: List[LandCoverComponent] = []
            characteristics: List[LandCharacteristic] = []
            seen_components = set()

            for st_id in associated_strata:
                for prop in stratum_to_props.get(st_id, []):
                    block_ref = prop.get("block_ref")
                    presence_str = prop.get("presence_str")
                    c_min = prop.get("c_min")
                    c_max = prop.get("c_max")

                    if not block_ref or not presence_str:
                        continue

                    # SSSOM Reverse lookup
                    sssom_match = sssom_resolver.resolve_iso_to_eagle(block_ref)
                    eagle_code = sssom_match["subject_id"] if sssom_match else None
                    eagle_label = sssom_match["subject_label"] if sssom_match else block_ref.replace("LC_", "")

                    # Map presence type & barcode enum
                    bcv_enum = sssom_resolver.map_presence_to_bcv(presence_str)
                    iso_presence = sssom_resolver.map_bcv_to_presence(bcv_enum.value.replace("BCV_", ""))

                    # Deduplicate components
                    comp_key = (eagle_code or block_ref)
                    if comp_key in seen_components:
                        continue
                    seen_components.add(comp_key)

                    is_abiotic = any(term in eagle_label.lower() for term in ["sealed", "surface", "soil", "rock", "construction", "building"])
                    is_water = any(term in eagle_label.lower() for term in ["water", "snow", "ice"])

                    comp_args = dict(
                        uri=f"https://dd.eionet.europa.eu/vocabulary/landcover/eagle/{eagle_code.replace('eagle:', '')}" if eagle_code else None,
                        label=eagle_label,
                        bcv_operator=bcv_enum,
                        iso_presence_type=iso_presence,
                        min_cover=c_min,
                        max_cover=c_max,
                        stratum_id=int(st_id) if st_id.isdigit() else 1
                    )

                    if is_abiotic:
                        comp = AbioticComponent(**comp_args)
                    elif is_water:
                        comp = WaterComponent(**comp_args)
                    else:
                        comp = BioticComponent(**comp_args)

                    components.append(comp)

                # Process Characteristics for this stratum
                for char in stratum_to_chars.get(st_id, []):
                    irr = char.get("irrigation_type")
                    sp = char.get("species_name")
                    if irr:
                        characteristics.append(LandCharacteristic(
                            label=f"Irrigation ({irr})",
                            characteristic_type="Irrigation"
                        ))
                    if sp:
                        characteristics.append(LandCharacteristic(
                            label=f"Species: {sp}",
                            characteristic_type="FloristicAspect"
                        ))

            unit = LandUnit(
                id=class_dict["id"],
                name=class_dict["name"],
                geometry_type="Polygon",
                land_cover_components=components,
                land_use_attributes=[],
                land_characteristics=characteristics
            )
            land_units.append(unit)

        return land_units

    def _extract_hierarchical(self, use_fuzzy: bool) -> List[LandUnit]:
        land_units: List[LandUnit] = []
        for legend_class in self.root.findall(".//LegendClass"):
            code_elem = legend_class.find("Code")
            name_elem = legend_class.find("Name")

            clean_code = (code_elem.text or "Unknown").replace(" ", "").strip()
            clean_name = (name_elem.text or clean_code).strip()

            components: List[LandCoverComponent] = []
            for element in legend_class.findall(".//LC_Element"):
                type_str = element.get("type")
                if not type_str:
                    continue

                presence_node = element.find("PresenceType")
                presence_text = presence_node.text if presence_node is not None else "Fixed"

                cov_min_node = element.find("CoverMin")
                cov_max_node = element.find("CoverMax")
                c_min = int(cov_min_node.text) if (cov_min_node is not None and cov_min_node.text) else None
                c_max = int(cov_max_node.text) if (cov_max_node is not None and cov_max_node.text) else None

                sssom_match = sssom_resolver.resolve_iso_to_eagle(type_str)
                eagle_code = sssom_match["subject_id"] if sssom_match else None
                eagle_label = sssom_match["subject_label"] if sssom_match else type_str

                bcv_enum = sssom_resolver.map_presence_to_bcv(presence_text)
                iso_presence = sssom_resolver.map_bcv_to_presence(bcv_enum.value.replace("BCV_", ""))

                comp = LandCoverComponent(
                    uri=f"https://dd.eionet.europa.eu/vocabulary/landcover/eagle/{eagle_code.replace('eagle:', '')}" if eagle_code else None,
                    label=eagle_label,
                    bcv_operator=bcv_enum,
                    iso_presence_type=iso_presence,
                    min_cover=c_min,
                    max_cover=c_max,
                    stratum_id=1
                )
                components.append(comp)

            unit = LandUnit(
                id=clean_code,
                name=clean_name,
                geometry_type="Polygon",
                land_cover_components=components,
                land_use_attributes=[],
                land_characteristics=[]
            )
            land_units.append(unit)

        return land_units


class EagleExcelExporter:
    """
    Exports LandUnit objects into the official EAGLE Barcode Matrix Excel format.
    Generates standard header, concept rows across LCC, LUA, and LCH, and fills Barcode/Factor values.
    """

    # Baseline EAGLE taxonomy concepts for standard matrix export
    DEFAULT_TAXONOMY = [
        # LCC Section
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-land-cover-components", "LCC", "Land Cover Components", 0, True),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-sealed-artificial-surfaces-and-constructions", "LCC-1_1_1", "Sealed Artificial Surfaces and Constructions", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-specific-buildings", "LCC-1_1_1_1_2", "Specific Buildings", 5, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-natural-material-surfaces", "LCC-1_2", "Natural Material Surfaces", 2, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-bare-soils", "LCC-1_2_2_2", "Bare Soils", 4, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-biotic-vegetation", "LCC-2", "Biotic, Vegetation", 1, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-trees", "LCC-2_1_1", "Trees", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-bushes-shrubs", "LCC-2_1_2", "Bushes, Shrubs", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-herbaceous-vegetation", "LCC-2_2", "Herbaceous Vegetation", 2, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-graminoids", "LCC-2_2_1", "Graminoids, Grass-Like", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-non-graminoids-forbs-ferns", "LCC-2_2_2", "Non-Graminoids, Forbs, Ferns", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCC-lichens-mosses-algae", "LCC-2_4", "Lichens, Mosses, Algae", 3, False),
        # LUA Section
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LUA-land-use-attributes", "LUA", "Land Use Attributes", 0, True),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LUA-commercial-crop-production", "LUA-1_1_1", "Commercial Crop Production", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LUA-permanent-residential", "LUA-5_1", "Permanent Residential", 2, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LUA-residential-use-with-other-compatible-uses", "LUA-5_2", "Residential Use With Other Compatible Uses", 2, False),
        # LCH Section
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-land-characteristics", "LCH", "Land Characteristics", 0, True),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-irrigation", "LCH-5_1_4_5", "Irrigation", 4, True),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-sprinkler-irrigation", "LCH-5_1_4_5_4", "Sprinkler Irrigation", 5, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-rice", "LCH-5_1_6_1_1_7", "Rice", 6, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-hops", "LCH-5_1_6_1_10_2", "Hops", 6, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-urban-context", "LCH-7_3_5", "Urban Context", 3, False),
        ("https://dd.eionet.europa.eu/vocabulary/landcover/eagle/LCH-rural-context", "LCH-7_3_6", "Rural Context", 3, False)
    ]

    def __init__(self, log_callback=print):
        self.log = log_callback
        self.workbook = openpyxl.Workbook()
        self.sheet = self.workbook.active
        self.sheet.title = "EAGLE Barcoding Matrix"

    def generate(self, land_units: List[LandUnit]) -> bytes:
        self.log(f"Generating EAGLE Barcode Excel for {len(land_units)} Land Units...")

        # Setup standard styles
        header_font = Font(name="Calibri", size=11, bold=True)
        title_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        title_fill = PatternFill(start_color="1F497D", end_color="1F497D", fill_type="solid")
        section_fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")

        # Row 1: Class Codes
        self.sheet.cell(row=1, column=1, value='Class Code* (If continuous dataset, enter "0" as Class Code)').font = header_font
        for idx, unit in enumerate(land_units):
            col_barcode = 5 + idx * 2
            self.sheet.cell(row=1, column=col_barcode, value=unit.id).font = header_font

        # Row 2: Class Names
        self.sheet.cell(row=2, column=1, value="Name*").font = header_font
        for idx, unit in enumerate(land_units):
            col_barcode = 5 + idx * 2
            self.sheet.cell(row=2, column=col_barcode, value=unit.name).font = header_font

        # Row 3: EAGLE Compliant
        self.sheet.cell(row=3, column=1, value='100% EAGLE Compliant* (Possible Values: "Yes" / "No")')
        for idx, unit in enumerate(land_units):
            col_barcode = 5 + idx * 2
            self.sheet.cell(row=3, column=col_barcode, value="YES")

        # Row 4: Colour Code
        self.sheet.cell(row=4, column=1, value="Colour Code (Possible values: only hex colour codes e.g. #87CEFA)")

        # Row 5: Column Headers
        col_headers = ["URI", "Code", "Label", "Level"]
        for idx, unit in enumerate(land_units):
            col_headers.extend(["Barcode", "Factor"])

        for col_num, h_text in enumerate(col_headers, 1):
            cell = self.sheet.cell(row=5, column=col_num, value=h_text)
            cell.font = title_font
            cell.fill = title_fill

        # Build dynamic taxonomy rows: baseline + any extra components found in LandUnits
        taxonomy = list(self.DEFAULT_TAXONOMY)
        existing_codes = set(item[1] for item in taxonomy)

        for unit in land_units:
            for comp in (unit.land_cover_components or []):
                sssom_match = sssom_resolver.resolve_eagle_to_iso(comp.uri, comp.label)
                code = sssom_match["subject_id"].replace("eagle:", "") if sssom_match else "LCC-Custom"
                if code not in existing_codes:
                    taxonomy.append((comp.uri or "", code, comp.label or code, 3, False))
                    existing_codes.add(code)

        # Write taxonomy rows and values
        current_row = 6
        for uri, code, label, level, is_heading in taxonomy:
            self.sheet.cell(row=current_row, column=1, value=uri)
            self.sheet.cell(row=current_row, column=2, value=code)
            self.sheet.cell(row=current_row, column=3, value=label)
            self.sheet.cell(row=current_row, column=4, value=level)

            if is_heading:
                for idx in range(len(land_units)):
                    c_col = 5 + idx * 2
                    cell = self.sheet.cell(row=current_row, column=c_col, value="SEGMENT HEADING")
                    cell.font = Font(italic=True, color="555555")
                current_row += 1
                continue

            # Populate barcode and factor for each LandUnit
            for idx, unit in enumerate(land_units):
                col_barcode = 5 + idx * 2
                col_factor = col_barcode + 1

                # Check if unit has a matching component
                matched_comp = None
                for comp in (unit.land_cover_components or []):
                    sssom_match = sssom_resolver.resolve_eagle_to_iso(comp.uri, comp.label)
                    comp_code = sssom_match["subject_id"].replace("eagle:", "") if sssom_match else None
                    if comp_code == code or (comp.label and comp.label.lower() in label.lower()):
                        matched_comp = comp
                        break

                if matched_comp:
                    bcv_val = matched_comp.bcv_operator
                    bcv_str = getattr(bcv_val, "value", str(bcv_val)).replace("BCV_", "") if bcv_val else "1"
                    try:
                        self.sheet.cell(row=current_row, column=col_barcode, value=int(bcv_str))
                    except ValueError:
                        self.sheet.cell(row=current_row, column=col_barcode, value=bcv_str)

                    # Factor
                    factor = sssom_resolver.coverage_to_factor(matched_comp.min_cover, matched_comp.max_cover)
                    if factor:
                        self.sheet.cell(row=current_row, column=col_factor, value=factor)

                # Check LandCharacteristics
                for char in (unit.land_characteristics or []):
                    char_lbl = (char.label or "").lower()
                    if ("irrigation" in char_lbl and "irrigation" in label.lower()) or \
                       ("rice" in char_lbl and "rice" in label.lower()) or \
                       ("hops" in char_lbl and "hops" in label.lower()):
                        self.sheet.cell(row=current_row, column=col_barcode, value="X" if any(s in char_lbl for s in ["rice", "hops"]) else 2)

            current_row += 1

        output = io.BytesIO()
        self.workbook.save(output)
        return output.getvalue()


def run_iso_to_eagle_mapping(xml_bytes: bytes, log_callback=print,
                             use_fuzzy: bool = True, force_hierarchical: bool = False) -> bytes:
    log_callback("Initializing LchsXmlParser with SSSOM crosswalk...")
    parser = LchsXmlParser(xml_bytes, log_callback)

    log_callback("Extracting ISO classes and properties into validated LandUnits...")
    land_units = parser.extract_land_units(use_fuzzy=use_fuzzy, force_hierarchical=force_hierarchical)

    if not land_units:
        log_callback("❌ Error: No valid data could be extracted from the XML.")
        return b""

    log_callback(f"Successfully processed {len(land_units)} Land Units. Generating EAGLE Matrix Excel...")
    exporter = EagleExcelExporter(log_callback)
    return exporter.generate(land_units)