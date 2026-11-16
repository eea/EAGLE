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
from src.mapping import extensions, fao
from src.mapping.cover import CoverItem, balance_stratum
from src.mapping.sssom_engine import sssom_resolver


def load_matrix(source, sheet_name: str, log_callback=None) -> openpyxl.Workbook:
    """The values of one sheet of an EAGLE workbook, as a small in-memory workbook.

    A full `load_workbook` parses every sheet with all its styles, which takes about 15-30 seconds
    for the multi-megabyte EAGLE workbooks. Reading the one sheet that is mapped, values only and
    in streaming mode, takes about half a second and gives the parser the same cells."""
    source_wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    try:
        if sheet_name not in source_wb.sheetnames:
            raise ValueError(f"Sheet '{sheet_name}' not found; the workbook has {', '.join(source_wb.sheetnames)}.")
        if log_callback:
            log_callback(f"Workbook has {len(source_wb.sheetnames)} sheets; reading only '{sheet_name}'...")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name
        for row_idx, row in enumerate(source_wb[sheet_name].iter_rows(min_row=1, min_col=1, values_only=True), 1):
            for col_idx, value in enumerate(row, 1):
                if value is not None:
                    ws.cell(row=row_idx, column=col_idx, value=value)
        if log_callback:
            log_callback(f"Read sheet '{sheet_name}': {ws.max_row} rows x {ws.max_column} columns.")
        return wb
    finally:
        source_wb.close()


class EagleXslxParser:
    """
    Parses vertical EAGLE Matrix Barcoding sheets into validated LandUnit Pydantic objects.
    Uses SSSOM crosswalk for semantic bridging between EAGLE codes/labels and ISO concepts.
    """

    def __init__(self, workbook: openpyxl.Workbook, sheet_name: str, log_callback=print, progress_callback=None):
        """`progress_callback(fraction, message)` is called while the rows are parsed (fraction 0..1)."""
        self.progress = progress_callback or (lambda fraction, message: None)
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
        total_rows = max(1, self.sheet.max_row - start_row + 1)
        report_every = max(1, total_rows // 10)
        for row_idx in range(start_row, self.sheet.max_row + 1):
            done = row_idx - start_row
            if done % report_every == 0:
                self.progress(done / total_rows, f"Parsing taxonomy rows {done}/{total_rows}")
                if done:
                    self.log(f"Parsed {done}/{total_rows} taxonomy rows ({100 * done // total_rows}%)...")
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
                if sssom_resolver.factor_status(factor_str)[0] == "unknown" and code_str.upper().startswith("LCC"):
                    self.log(f"\u26a0\ufe0f {class_data['code']}: factor {factor_str} of {code_str} has no known cover interval; cover left open")

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
                            code=code_str or None,
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

        self.progress(1.0, "Taxonomy rows parsed")
        for unit in validated_units:
            self.log(
                f"  {unit.id}: {len(unit.land_cover_components)} land cover, "
                f"{len(unit.land_use_attributes)} land use, {len(unit.land_characteristics)} characteristics"
            )
        self.log(f"Successfully constructed {len(validated_units)} validated LandUnits.")
        return validated_units


class LchsXmlGenerator:
    """
    Generates standard ISO 19144 (LChS LCML/LUML) XML from validated LandUnit objects.
    Produces the standard relational structure supported by ISO 19144 tools.
    """

    def __init__(self, log_callback=print, include_extensions: bool = True, progress_callback=None):
        """`include_extensions=False` writes only what the FAO LChS profile of ISO 19144-2 knows: land cover
        components, and irrigation / rice / hops characteristics. `include_extensions=True` also writes
        land use (LU_LandUse) and every other land characteristic, with the irrigation code lists
        of eagle_iso_extensions.yaml. Those are a project extension, not a published ISO schema."""
        self.log = log_callback
        self.progress = progress_callback or (lambda fraction, message: None)
        self.include_extensions = include_extensions

    # The element presence types of the FAO LChS tool (fao_lchs_profile.json). There is no plain "Conditional": its
    # own export writes "Conditional Temporal" for optional elements. Older enum values are written that way too.
    _PRESENCE_LABELS = {
        "Fixed": "Fixed", "Exclusive": "Exclusive", "Precluded": "Precluded",
        "ConditionalTemporal": "Conditional Temporal", "Conditional": "Conditional Temporal", "Optional": "Conditional Temporal",
    }

    @staticmethod
    def _presence(item) -> str:
        presence = getattr(item, "iso_presence_type", None)
        value = getattr(presence, "value", str(presence)) if presence else "Fixed"
        return LchsXmlGenerator._PRESENCE_LABELS.get(value, value)

    @staticmethod
    def _eagle_bcv(item) -> Optional[str]:
        """The bar code value as written in the matrix ("1".."5", "X"): ISO presence types cannot tell 2 from 5."""
        bcv = getattr(item, "bcv_operator", None)
        return getattr(bcv, "value", str(bcv)).replace("BCV_", "") if bcv else None

    def _report_bcv_losses(self, land_units: List[LandUnit]) -> None:
        """BCV 4 has no ISO presence type, BCV 5 is the same as 2 in the plain subset: say so, per class."""
        for unit in land_units:
            items = list(unit.land_cover_components or []) + list(unit.land_use_attributes or []) + list(unit.land_characteristics or [])
            four = [i.code or i.label for i in items if self._eagle_bcv(i) == "4"]
            five = [i.code or i.label for i in items if self._eagle_bcv(i) == "5"]
            kept = " (the exact value is kept in EagleBcv)" if self.include_extensions else ""
            if four:
                self.log(f"\u26a0\ufe0f {unit.id}: BCV 4 (at least two) has no ISO presence type, written as Conditional{kept}: {', '.join(four[:6])}{' ...' if len(four) > 6 else ''}")
            if five and not self.include_extensions:
                self.log(f"\u26a0\ufe0f {unit.id}: BCV 5 (only this one) is written as Exclusive like BCV 2 in the plain subset: {len(five)} elements")

    @staticmethod
    def _text(parent: ET.Element, tag: str, value) -> None:
        ET.SubElement(parent, tag).text = str(value)

    def _block(self, parent: ET.Element, reference: str) -> None:
        """BlockID and BlockReference, as the FAO tool writes them (it joins on the numeric BlockID)."""
        block_id = fao.block_id(reference)
        if block_id is not None:
            self._text(parent, "BlockID", block_id)
        self._text(parent, "BlockReference", reference)

    def _characteristic(self, parent: ET.Element, reference: str, label: str) -> None:
        characteristic_id = fao.characteristic_id(reference)
        if characteristic_id is not None:
            self._text(parent, "CharacteristicID", characteristic_id)
        self._text(parent, "CharacteristicReference", reference)
        self._text(parent, "CharacteristicLabel", label)

    def _block_reference(self, comp, unit_id: str = "", warn: bool = True) -> str:
        """The ISO block of a land cover component: by EAGLE code (own row, else nearest ancestor), for
        components without a code by label. A concept with no known ISO block is written under a name
        derived from its label, and reported: the FAO tool may not know that name."""
        if comp.code:
            sssom_match, _ = sssom_resolver.resolve_block(comp.code)
        else:
            sssom_match = sssom_resolver.resolve_eagle_to_iso(comp.uri, comp.label)
        if sssom_match:
            return sssom_resolver._normalize_curie(sssom_match.get("object_id", ""))
        name = f"LC_{re.sub(r'[^a-zA-Z0-9]', '', comp.label or 'Vegetation')}"
        if warn:
            self.log(f"⚠️ {unit_id}: no ISO block is known for {comp.code or comp.label} ({comp.label}); written as {name}, which the FAO tool may not know")
        return name

    def _merge_by_block(self, unit_id: str, entries: list) -> list:
        """Plain LChS subset: EAGLE concepts that share one ISO block (Bare Rock and Hard Pan are both a
        natural surface element) become one property. A stated presence wins over an excluded one, the cover
        range spans all of them."""
        order = ["Fixed", "Exclusive", "Conditional Temporal", "Precluded"]
        merged: Dict[str, dict] = {}
        for entry in entries:
            kept = merged.get(entry["block"])
            if kept is None:
                merged[entry["block"]] = dict(entry, merged=1)
                continue
            kept["merged"] += 1
            kept["presence"] = min(kept["presence"], entry["presence"], key=lambda p: order.index(p) if p in order else len(order))
            kept["cover"] = (min(kept["cover"][0], entry["cover"][0]), max(kept["cover"][1], entry["cover"][1]))
        for block, entry in merged.items():
            if entry["merged"] > 1:
                self.log(f"{unit_id}: {entry['merged']} EAGLE concepts share the ISO block {block}; merged into one property (plain LChS subset)")
        return list(merged.values())

    def _host_block(self, unit: LandUnit) -> str:
        """The land cover element a characteristic is attached to: the first biotic one, else the first."""
        components = unit.land_cover_components or []
        biotic = [c for c in components if isinstance(c, BioticComponent)]
        host = (biotic or components or [None])[0]
        return self._block_reference(host, unit.id, warn=False) if host else "LC_Graminoid"

    def _prettify(self, elem: ET.Element) -> bytes:
        rough_string = ET.tostring(elem, encoding="utf-8")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="utf-8")

    # ------------------------------------------------------------------ characteristics

    def _floristic_aspect(self, objects: ET.Element, idx: int, host: str, species: str, presence: Optional[str] = None, bcv: Optional[str] = None) -> None:
        elem = ET.SubElement(objects, "LC_Characteristics")
        self._text(elem, "StratumID", idx)
        self._block(elem, host)
        self._characteristic(elem, extensions.FLORISTIC_CLASS, "Floristic Aspects")
        if presence:
            self._text(elem, "elementPresenceType", presence)
        if bcv:
            self._text(elem, "EagleBcv", bcv)
        self._text(elem, "speciesName", species)

    def _write_lcml_characteristics(self, objects: ET.Element, idx: int, unit: LandUnit) -> None:
        """Plain LCML subset: irrigation (as the FAO cultivated & managed vegetation characteristic), rice, hops.
        The FAO tool knows three irrigation types (Surface, Sprinkler, Drip): the EAGLE methods are written as the
        nearest of them, once each; a method without one (manual, unspecified) is written without a type."""
        written = set()
        for char in unit.land_characteristics or []:
            if self._presence(char) == "Precluded":
                continue  # the plain profile cannot say "no sprinkler irrigation"
            species = extensions.species(char.code)
            if extensions.states_irrigation(char.code):
                method = extensions.irrigation(char.code)["irrigationType"]
                fao_type = extensions.fao_irrigation_type(method)
                if (fao_type or method) in written:
                    continue
                written.add(fao_type or method)
                if not fao_type:
                    self.log(f"{unit.id}: {method} irrigation has no FAO irrigation type (Surface, Sprinkler, Drip); written without a type")
                irr_elem = ET.SubElement(objects, "LC_Characteristics")
                self._text(irr_elem, "StratumID", idx)
                self._block(irr_elem, "LC_Graminoid")
                self._characteristic(irr_elem, "LC_CultivatedAndManagedVegetationCharacteristics", "Cultivated & Managed Vegetation")
                if fao_type:
                    self._text(irr_elem, "irrigationType", fao_type)
            elif species:
                self._floristic_aspect(objects, idx, "LC_Graminoid", species)

    def _write_characteristics(self, objects: ET.Element, idx: int, unit: LandUnit) -> None:
        """Every land characteristic. Irrigation concepts are merged into one LC_IrrigationCharacteristic
        per presence type (the either-or methods and a mandatory water source differ in presence)."""
        host = self._host_block(unit)
        irrigation = []
        for char in unit.land_characteristics or []:
            species = extensions.species(char.code)
            klass = extensions.characteristic_class(char.code)
            if species:
                self._floristic_aspect(objects, idx, host, species, self._presence(char), self._eagle_bcv(char))
            elif klass == extensions.IRRIGATION_CLASS:
                irrigation.append(char)
            else:
                elem = ET.SubElement(objects, "LC_Characteristics")
                self._text(elem, "StratumID", idx)
                self._block(elem, host)
                self._characteristic(elem, klass, char.label or char.code or "")
                if char.code:
                    self._text(elem, "CharacteristicCode", char.code)
                if char.uri:
                    self._text(elem, "CharacteristicURI", char.uri)
                self._text(elem, "elementPresenceType", self._presence(char))
                if self._eagle_bcv(char):
                    self._text(elem, "EagleBcv", self._eagle_bcv(char))
        by_bcv: Dict[str, list] = {}
        for char in irrigation:
            by_bcv.setdefault(self._eagle_bcv(char) or self._presence(char), []).append(char)
        for bcv, members in by_bcv.items():
            self._write_irrigation(objects, idx, host, members, self._presence(members[0]), self._eagle_bcv(members[0]))

    def _write_irrigation(self, objects: ET.Element, idx: int, host: str, members: list, presence: str, bcv: Optional[str] = None) -> None:
        precluded = presence == "Precluded"
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
        self._block(elem, host)
        self._characteristic(elem, extensions.IRRIGATION_CLASS, "Irrigation")
        for char in members:
            self._text(elem, "CharacteristicCode", char.code)
        self._text(elem, "elementPresenceType", presence)
        if bcv:
            self._text(elem, "EagleBcv", bcv)
        if irrigated is not None:
            self._text(elem, "irrigated", str(irrigated).lower())
        for value in types:
            self._text(elem, "irrigationType", value)
        for value in sources:
            self._text(elem, "waterSource", value)

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
        if self._eagle_bcv(lua):
            self._text(elem, "EagleBcv", self._eagle_bcv(lua))
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
        self.progress(0.0, "Writing classes, patterns and strata")
        self._report_bcv_losses(land_units)

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
            self.progress(0.2 + 0.5 * (idx - 1) / len(land_units), f"Writing land cover of class {unit.id} ({idx}/{len(land_units)})")
            if not unit.land_cover_components:
                continue

            # All elements of a class share one stratum: their covers must fit 100% (see cover.py)
            ranges, warnings = balance_stratum([
                CoverItem(c.code, self._presence(c), c.min_cover, c.max_cover) for c in unit.land_cover_components
            ])
            for warning in warnings:
                self.log(f"⚠️ {unit.id}: {warning}")

            entries = [
                {"comp": comp, "block": self._block_reference(comp, unit.id), "presence": self._presence(comp), "bcv": self._eagle_bcv(comp), "cover": cover}
                for comp, cover in zip(unit.land_cover_components, ranges)
            ]
            if not self.include_extensions:
                entries = self._merge_by_block(unit.id, entries)

            for entry in entries:
                comp, (c_min, c_max) = entry["comp"], entry["cover"]
                prop_elem = ET.SubElement(objects, "LC_Properties")
                ET.SubElement(prop_elem, "StratumID").text = str(idx)
                self._block(prop_elem, entry["block"])
                if self.include_extensions and comp.code:  # lets ISO -> EAGLE return the exact concept, not just its block
                    ET.SubElement(prop_elem, "EagleCode").text = comp.code
                    ET.SubElement(prop_elem, "EagleLabel").text = comp.label or comp.code
                ET.SubElement(prop_elem, "elementPresenceType").text = entry["presence"]
                if self.include_extensions and entry["bcv"]:
                    ET.SubElement(prop_elem, "EagleBcv").text = entry["bcv"]

                # ISO 19144-2 models the cover as one range. LChS serialises that range as two
                # repeated <cover> elements: the first is the minimum, the second the maximum
                # percentage (the FAO LChS export of "30-80% sealed" has <cover>30</cover><cover>80</cover>).
                ET.SubElement(prop_elem, "cover").text = str(c_min)
                ET.SubElement(prop_elem, "cover").text = str(c_max)

        self.log(f"Land cover written for {len(land_units)} classes. Writing characteristics...")

        # 5. Characteristics (Land Characteristics)
        for idx, unit in enumerate(land_units, 1):
            self.progress(0.7 + 0.2 * (idx - 1) / len(land_units), f"Writing characteristics of class {unit.id} ({idx}/{len(land_units)})")
            if self.include_extensions:
                self._write_characteristics(objects, idx, unit)
            else:
                self._write_lcml_characteristics(objects, idx, unit)

        # 6. Land use (extension: ISO 19144-3 LUML is a separate schema the LChS profile does not carry)
        if self.include_extensions:
            self.progress(0.9, "Writing land use")
            self.log("Writing land use...")
            for idx, unit in enumerate(land_units, 1):
                for lua in unit.land_use_attributes or []:
                    self._write_land_use(objects, idx, lua)

        self.progress(0.95, "Formatting XML")
        result = self._prettify(root)
        self.progress(1.0, "XML ready")
        return result


def run_eagle_to_iso_mapping(
    excel_workbook: openpyxl.Workbook,
    sheet_name: str,
    log_callback=print,
    include_extensions: bool = True,
    progress_callback=None,
) -> bytes:
    """`progress_callback(fraction, message)`: 0..1 over the whole run (parsing the rows takes most of it)."""
    report = progress_callback or (lambda fraction, message: None)
    log_callback("Initializing EagleXslxParser with SSSOM Resolver...")
    parser = EagleXslxParser(excel_workbook, sheet_name, log_callback, lambda f, m: report(0.05 + 0.75 * f, m))

    log_callback("Extracting and semantically validating data into LandUnits...")
    land_units = parser.extract_land_units()

    log_callback(f"Successfully processed {len(land_units)} Land Units. Generating ISO 19144 XML...")
    generator = LchsXmlGenerator(
        log_callback, include_extensions=include_extensions, progress_callback=lambda f, m: report(0.8 + 0.2 * f, m)
    )

    return generator.generate_xml(land_units)