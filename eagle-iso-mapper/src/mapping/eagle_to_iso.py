import io
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import List, Optional, Dict, Any
import openpyxl

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
from src.mapping import extensions
from src.mapping.sssom_engine import sssom_resolver


class EagleXslxParser:
    """
    Parses vertical EAGLE Matrix Barcoding sheets into validated LandUnit Pydantic objects.
    Uses SSSOM crosswalk for semantic bridging between EAGLE codes/labels and ISO concepts.
    """

    def __init__(self, workbook: openpyxl.Workbook, sheet_name: str, log_callback=print):
        self.workbook = workbook
        self.sheet = self.workbook[sheet_name]
        self.log = log_callback

    @staticmethod
    def _block_of(code: str, label: str) -> Optional[str]:
        """LCC, LUA or LCH. The code prefix wins: a land use or characteristic whose label says
        "land cover" must not become a land cover component."""
        prefix = code.upper()[:3]
        if prefix in ("LCC", "LUA", "LCH"):
            return prefix
        lowered = label.lower()
        if "land cover" in lowered:
            return "LCC"
        if "land use" in lowered:
            return "LUA"
        if "land characteristic" in lowered:
            return "LCH"
        return None

    def extract_land_units(self) -> List[LandUnit]:
        self.log("Identifying Class Codes and Names from sheet...")
        classes_info: Dict[int, Dict[str, Any]] = {}

        # 1. Locate header rows dynamically
        code_row = 1
        for r in range(1, 10):
            val = self.sheet.cell(row=r, column=1).value
            if val and "Class Code" in str(val):
                code_row = r
                break

        name_row = code_row + 1

        # 2. Identify Class columns (starting at col 5, step 2)
        for col_idx in range(5, self.sheet.max_column + 1, 2):
            class_code = self.sheet.cell(row=code_row, column=col_idx).value
            class_name = self.sheet.cell(row=name_row, column=col_idx).value

            if class_code and str(class_code).strip() != "":
                clean_code = str(class_code).strip()
                clean_name = str(class_name).strip() if class_name else clean_code
                classes_info[col_idx] = {
                    "code": clean_code,
                    "name": clean_name,
                    "land_cover_components": [],
                    "land_use_attributes": [],
                    "land_characteristics": []
                }

        if not classes_info:
            err_msg = f"No Land Unit classes found in sheet '{self.sheet.title}'. Please ensure the sheet has 'Class Code' headers (e.g. 'CLC-all 3 Classes' or 'CLC112')."
            self.log(f"⚠️ {err_msg}")
            raise ValueError(err_msg)

        self.log(f"Found {len(classes_info)} Land Unit classes in sheet. Parsing taxonomy rows...")

        # 3. Iterate over concept rows
        start_row = name_row + 4  # usually row 6 or 7
        for row_idx in range(start_row, self.sheet.max_row + 1):
            uri_val = self.sheet.cell(row=row_idx, column=1).value
            code_val = self.sheet.cell(row=row_idx, column=2).value
            label_val = self.sheet.cell(row=row_idx, column=3).value

            if not code_val and not label_val:
                continue

            code_str = str(code_val).strip() if code_val else ""
            label_str = str(label_val).strip() if label_val else ""
            uri_str = str(uri_val).strip() if uri_val else ""

            # Skip root segment headings
            if code_str.upper() in ["LCC", "LUA", "LCH"] or label_str.lower() in [
                "land cover components", "land use attributes", "land characteristics"
            ]:
                continue

            # Check each class column for barcode entries
            for col_idx, class_data in classes_info.items():
                barcode_cell = self.sheet.cell(row=row_idx, column=col_idx).value
                factor_cell = self.sheet.cell(row=row_idx, column=col_idx + 1).value

                if barcode_cell is None:
                    continue

                barcode_str = str(barcode_cell).strip()
                if not barcode_str or barcode_str.upper() in ["SEGMENT HEADING", "NONE", "LCC", "LUA", "LCH"]:
                    continue

                factor_str = str(factor_cell).strip() if factor_cell is not None else None

                # Resolve SSSOM crosswalk mapping
                sssom_match = sssom_resolver.resolve_eagle_to_iso(code_str, label_str)
                iso_presence = sssom_resolver.map_bcv_to_presence(barcode_str)
                cov_min, cov_max = sssom_resolver.factor_to_coverage(factor_str)

                bcv_enum = None
                bcv_key = f"BCV_{barcode_str.upper()}"
                if bcv_key in BarCodeValueEnum.__members__:
                    bcv_enum = BarCodeValueEnum[bcv_key]
                elif barcode_str in BarCodeValueEnum.__members__:
                    bcv_enum = BarCodeValueEnum[barcode_str]

                # Component categorization: the code prefix decides, the label only when there is no code
                kind = self._block_of(code_str, label_str)
                if kind == "LCC":
                    # Check for duplicates
                    already_exists = any(
                        c.uri == uri_str or (c.label and c.label == label_str)
                        for c in class_data["land_cover_components"]
                    )
                    if not already_exists:
                        # Instantiate specific subtype according to nature of component
                        is_abiotic = any(term in label_str.lower() for term in ["sealed", "surface", "soil", "rock", "construction", "building"])
                        is_water = any(term in label_str.lower() for term in ["water", "snow", "ice"])

                        comp_kwargs = dict(
                            uri=uri_str or None,
                            label=label_str,
                            bcv_operator=bcv_enum,
                            iso_presence_type=iso_presence,
                            min_cover=cov_min,
                            max_cover=cov_max,
                            stratum_id=1
                        )

                        if is_abiotic:
                            comp = AbioticComponent(**comp_kwargs)
                        elif is_water:
                            comp = WaterComponent(**comp_kwargs)
                        else:
                            comp = BioticComponent(**comp_kwargs)

                        class_data["land_cover_components"].append(comp)

                elif kind == "LUA":
                    # Extract HILUCS code from code_str (e.g. LUA-5_1 -> 5.1)
                    hilucs_code = None
                    if code_str.startswith("LUA-"):
                        hilucs_code = code_str.replace("LUA-", "").replace("_", ".")

                    lua = LandUseAttribute(
                        uri=uri_str or None,
                        label=label_str,
                        code=code_str or None,
                        bcv_operator=bcv_enum,
                        iso_presence_type=iso_presence,
                        hilucs_code=hilucs_code,
                        iso_function_type=sssom_match.get("object_label") if sssom_match else None,
                        functional_relationship=FunctionalRelationshipEnum.Primary if barcode_str in ["3", "5"] else FunctionalRelationshipEnum.Secondary,
                        temporal_relationship=TemporalRelationshipEnum.Coexistant
                    )
                    class_data["land_use_attributes"].append(lua)

                elif kind == "LCH":
                    char_type = "Context"
                    if extensions.characteristic_class(code_str) == extensions.IRRIGATION_CLASS:
                        char_type = "Irrigation"
                    elif extensions.species(code_str):
                        char_type = "FloristicAspect"

                    lch = LandCharacteristic(
                        uri=uri_str or None,
                        label=label_str,
                        code=code_str or None,
                        bcv_operator=bcv_enum,
                        iso_presence_type=iso_presence,
                        characteristic_type=char_type
                    )
                    class_data["land_characteristics"].append(lch)

        # 4. Construct validated LandUnit Pydantic objects
        validated_units: List[LandUnit] = []
        for col_idx, data in classes_info.items():
            unit = LandUnit(
                id=data["code"],
                name=data["name"],
                geometry_type="Polygon",
                land_cover_components=data["land_cover_components"],
                land_use_attributes=data["land_use_attributes"],
                land_characteristics=data["land_characteristics"]
            )
            validated_units.append(unit)

        self.log(f"Successfully constructed {len(validated_units)} validated LandUnits.")
        return validated_units


class LchsXmlGenerator:
    """
    Generates standard ISO 19144 (LChS LCML/LUML) XML from validated LandUnit objects.
    Produces the standard relational structure supported by ISO 19144 tools.
    """

    def __init__(self, log_callback=print, include_extensions: bool = True):
        """`include_extensions=False` writes only what the FAO LChS profile of ISO 19144-2 knows: land cover
        components, and irrigation / rice / hops characteristics. `include_extensions=True` also writes
        land use (LU_LandUse) and every other land characteristic, with the irrigation code lists
        of eagle_iso_extensions.yaml. Those are a project extension, not a published ISO schema."""
        self.log = log_callback
        self.include_extensions = include_extensions

    @staticmethod
    def _presence(item) -> str:
        presence = getattr(item, "iso_presence_type", None)
        return getattr(presence, "value", str(presence)) if presence else "Fixed"

    @staticmethod
    def _text(parent: ET.Element, tag: str, value) -> None:
        ET.SubElement(parent, tag).text = str(value)

    def _block_reference(self, comp) -> str:
        sssom_match = sssom_resolver.resolve_eagle_to_iso(comp.uri, comp.label)
        if sssom_match:
            return sssom_resolver._normalize_curie(sssom_match.get("object_id", ""))
        # Fallback clean label
        return f"LC_{re.sub(r'[^a-zA-Z0-9]', '', comp.label or 'Vegetation')}"

    def _host_block(self, unit: LandUnit) -> str:
        """The land cover element a characteristic is attached to: the first biotic one, else the first."""
        components = unit.land_cover_components or []
        biotic = [c for c in components if isinstance(c, BioticComponent)]
        host = (biotic or components or [None])[0]
        return self._block_reference(host) if host else "LC_Graminoid"

    def _prettify(self, elem: ET.Element) -> bytes:
        rough_string = ET.tostring(elem, encoding="utf-8")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # ------------------------------------------------------------------ characteristics

    def _floristic_aspect(self, objects: ET.Element, idx: int, host: str, species: str, presence: Optional[str] = None) -> None:
        elem = ET.SubElement(objects, "LC_Characteristics")
        self._text(elem, "StratumID", idx)
        self._text(elem, "BlockReference", host)
        self._text(elem, "CharacteristicReference", extensions.FLORISTIC_CLASS)
        self._text(elem, "CharacteristicLabel", "Floristic Aspects")
        if presence:
            self._text(elem, "elementPresenceType", presence)
        self._text(elem, "speciesName", species)

    def _write_lcml_characteristics(self, objects: ET.Element, idx: int, unit: LandUnit) -> None:
        """Plain LCML subset: irrigation (as the FAO cultivated & managed vegetation characteristic), rice, hops."""
        for char in unit.land_characteristics or []:
            if self._presence(char) == "Precluded":
                continue  # the plain profile cannot say "no sprinkler irrigation"
            species = extensions.species(char.code)
            if extensions.states_irrigation(char.code):
                irr_elem = ET.SubElement(objects, "LC_Characteristics")
                self._text(irr_elem, "StratumID", idx)
                self._text(irr_elem, "BlockReference", "LC_Graminoid")
                self._text(irr_elem, "CharacteristicReference", "LC_CultivatedAndManagedVegetationCharacteristics")
                self._text(irr_elem, "CharacteristicLabel", "Cultivated & Managed Vegetation")
                irr_type = extensions.irrigation(char.code)["irrigationType"]
                self._text(irr_elem, "irrigationType", irr_type[:1].upper() + irr_type[1:])
            elif species:
                self._floristic_aspect(objects, idx, "LC_Graminoid", species)

    def _write_characteristics(self, objects: ET.Element, idx: int, unit: LandUnit) -> None:
        """Every land characteristic. Irrigation concepts are merged into one LC_IrrigationCharacteristic
        (a stated one and a precluded one at most), as the extension model has one per land cover element."""
        host = self._host_block(unit)
        irrigation = []
        for char in unit.land_characteristics or []:
            species = extensions.species(char.code)
            klass = extensions.characteristic_class(char.code)
            if species:
                self._floristic_aspect(objects, idx, host, species, self._presence(char))
            elif klass == extensions.IRRIGATION_CLASS:
                irrigation.append(char)
            else:
                elem = ET.SubElement(objects, "LC_Characteristics")
                self._text(elem, "StratumID", idx)
                self._text(elem, "BlockReference", host)
                self._text(elem, "CharacteristicReference", klass)
                self._text(elem, "CharacteristicLabel", char.label or char.code or "")
                if char.code:
                    self._text(elem, "CharacteristicCode", char.code)
                if char.uri:
                    self._text(elem, "CharacteristicURI", char.uri)
                self._text(elem, "elementPresenceType", self._presence(char))
        for precluded in (False, True):
            members = [c for c in irrigation if (self._presence(c) == "Precluded") == precluded]
            if members:
                self._write_irrigation(objects, idx, host, members, precluded)

    def _write_irrigation(self, objects: ET.Element, idx: int, host: str, members: list, precluded: bool) -> None:
        facts = [extensions.irrigation(c.code) or {} for c in members]
        types = list(dict.fromkeys(f["irrigationType"] for f in facts if "irrigationType" in f))
        sources = list(dict.fromkeys(f["waterSource"] for f in facts if "waterSource" in f))
        if precluded:
            # Excluding irrigation in general means "not irrigated"; excluding a method or a source keeps that value.
            irrigated = False if "unspecified" in types else None
            types = [t for t in types if t != "unspecified"]
        else:
            stated = [f["irrigated"] for f in facts if "irrigated" in f]
            irrigated = any(stated) if stated else None
            if len(types) > 1:
                types = [t for t in types if t != "unspecified"]

        elem = ET.SubElement(objects, "LC_Characteristics")
        self._text(elem, "StratumID", idx)
        self._text(elem, "BlockReference", host)
        self._text(elem, "CharacteristicReference", extensions.IRRIGATION_CLASS)
        self._text(elem, "CharacteristicLabel", "Irrigation")
        for char in members:
            self._text(elem, "CharacteristicCode", char.code)
        self._text(elem, "elementPresenceType", "Precluded" if precluded else self._strongest(members))
        if irrigated is not None:
            self._text(elem, "irrigated", str(irrigated).lower())
        for value in types:
            self._text(elem, "irrigationType", value)
        for value in sources:
            self._text(elem, "waterSource", value)

    def _strongest(self, members: list) -> str:
        order = ["Fixed", "Exclusive", "Conditional", "Optional"]
        presences = [self._presence(c) for c in members]
        return min(presences, key=lambda p: order.index(p) if p in order else len(order))

    # ------------------------------------------------------------------ land use

    def _write_land_use(self, objects: ET.Element, idx: int, lua) -> None:
        elem = ET.SubElement(objects, "LU_LandUse")
        self._text(elem, "class_id", idx)
        if lua.code:
            self._text(elem, "LandUseCode", lua.code)
        if lua.hilucs_code:
            self._text(elem, "hilucsCode", lua.hilucs_code)
        self._text(elem, "LandUseLabel", lua.label or lua.code or "")
        if lua.uri:
            self._text(elem, "LandUseURI", lua.uri)
        self._text(elem, "elementPresenceType", self._presence(lua))
        for tag, value in (("functionalRelationship", lua.functional_relationship), ("temporalRelationship", lua.temporal_relationship)):
            if value:
                self._text(elem, tag, getattr(value, "value", value))

    def generate_xml(self, land_units: List[LandUnit]) -> bytes:
        root = ET.Element(
            "LC_Legend",
            attrib={
                "id": "1",
                "legend_name": "EAGLE to ISO 19144 Crosswalk Legend",
                "legend_description": "Exported from EAGLE Matrix Barcoding via SSSOM",
                "legend_author": "EAGLE ISO Mapper",
                "elementID": "1",
                "formElementID": "1",
                "objectID": "1",
                "objectReference": "LC_Legend"
            }
        )
        objects = ET.SubElement(root, "objects")

        self.log(f"Generating ISO 19144 XML for {len(land_units)} Land Units...")

        # 1. Classes
        for idx, unit in enumerate(land_units, 1):
            c_elem = ET.SubElement(objects, "LC_Class")
            ET.SubElement(c_elem, "legend_id").text = "1"
            ET.SubElement(c_elem, "class_id").text = str(idx)
            ET.SubElement(c_elem, "class_name").text = unit.name or unit.id
            ET.SubElement(c_elem, "class_description").text = f"Corine class {unit.id}"
            ET.SubElement(c_elem, "class_map_code").text = unit.id

        # 2. Horizontal Patterns
        for idx in range(1, len(land_units) + 1):
            hp_elem = ET.SubElement(objects, "LC_HorizontalPatterns")
            ET.SubElement(hp_elem, "class_id").text = str(idx)
            ET.SubElement(hp_elem, "horizontal_pattern_id").text = str(idx)
            ET.SubElement(hp_elem, "name").text = f"Horizontal Pattern {idx}"
            ET.SubElement(hp_elem, "cover").text = "0"
            ET.SubElement(hp_elem, "cover").text = "100"
            ET.SubElement(hp_elem, "occurrence").text = "0"
            ET.SubElement(hp_elem, "occurrence").text = "100"

        # 3. Strata
        for idx in range(1, len(land_units) + 1):
            strata_elem = ET.SubElement(objects, "LC_Strata")
            ET.SubElement(strata_elem, "HPID").text = str(idx)
            ET.SubElement(strata_elem, "stratumID").text = str(idx)
            ET.SubElement(strata_elem, "name").text = f"Stratum {idx}"
            ET.SubElement(strata_elem, "presenceType").text = "Fixed"
            ET.SubElement(strata_elem, "portioning").text = "100"

        # 4. Properties (Land Cover Components)
        for idx, unit in enumerate(land_units, 1):
            if not unit.land_cover_components:
                continue

            for comp in unit.land_cover_components:
                prop_elem = ET.SubElement(objects, "LC_Properties")
                ET.SubElement(prop_elem, "StratumID").text = str(idx)
                ET.SubElement(prop_elem, "BlockReference").text = self._block_reference(comp)
                ET.SubElement(prop_elem, "elementPresenceType").text = self._presence(comp)

                # ISO 19144-2 models the cover as one range. LChS serialises that range as two
                # repeated <cover> elements: the first is the minimum, the second the maximum
                # percentage (the FAO LChS export of "30-80% sealed" has <cover>30</cover><cover>80</cover>).
                c_min = comp.min_cover if comp.min_cover is not None else 0
                c_max = comp.max_cover if comp.max_cover is not None else 100
                ET.SubElement(prop_elem, "cover").text = str(c_min)
                ET.SubElement(prop_elem, "cover").text = str(c_max)

        # 5. Characteristics (Land Characteristics)
        for idx, unit in enumerate(land_units, 1):
            if self.include_extensions:
                self._write_characteristics(objects, idx, unit)
            else:
                self._write_lcml_characteristics(objects, idx, unit)

        # 6. Land use (extension: ISO 19144-3 LUML is a separate schema the LChS profile does not carry)
        if self.include_extensions:
            for idx, unit in enumerate(land_units, 1):
                for lua in unit.land_use_attributes or []:
                    self._write_land_use(objects, idx, lua)

        return self._prettify(root)


def run_eagle_to_iso_mapping(excel_workbook: openpyxl.Workbook, sheet_name: str, log_callback=print, include_extensions: bool = True) -> bytes:
    log_callback("Initializing EagleXslxParser with SSSOM Resolver...")
    parser = EagleXslxParser(excel_workbook, sheet_name, log_callback)

    log_callback("Extracting and semantically validating data into LandUnits...")
    land_units = parser.extract_land_units()

    log_callback(f"Successfully processed {len(land_units)} Land Units. Generating ISO 19144 XML...")
    generator = LchsXmlGenerator(log_callback, include_extensions=include_extensions)

    return generator.generate_xml(land_units)