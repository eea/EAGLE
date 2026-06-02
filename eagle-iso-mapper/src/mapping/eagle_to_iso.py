import io
import xml.etree.ElementTree as ET
from xml.dom import minidom
import openpyxl
from typing import List

# Import generated models
from src.python.generated.eagle_iso_models import (
    CorineClass,
    LandCoverComponent,
    EagleMatrixValue,
    EagleLccType,
    LcmlPresenceType
)

class EagleExcelParser:
    """Extracts raw data and applies semantic mapping to ISO."""
    def __init__(self, file_bytes: bytes):
        self.workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        self.sheet = self.workbook.active

        self.code_to_enum = {
            "LCC-1_1_1": EagleLccType.SealedArtificialSurface,
            "LCC-1_1_1_1_2": EagleLccType.SpecificBuildings,
            "LCC-1_2": EagleLccType.NaturalSurfaces,
            "LCC-1_2_2": EagleLccType.BareSoil,
            "LCC-2": EagleLccType.BioticVegetation,
            "LCC-2_1": EagleLccType.Trees,
            "LCC-2_2": EagleLccType.Shrubs,
            "LCC-2_3": EagleLccType.HerbaceousVegetation,
            "LCC-2_4_1": EagleLccType.LichenMosses,
            "LCC-2_4_2": EagleLccType.LichenMosses,
            "LCC-2_4_3": EagleLccType.Algae
        }

    def _map_presence_type(self, barcode: str):
        """Translates EAGLE Matrix Value to ISO Presence Type."""
        mapping = {
            "3": LcmlPresenceType.Fixed,
            "2": LcmlPresenceType.Exclusive,
            "1": LcmlPresenceType.ConditionalTemporal
        }
        return mapping.get(barcode)

    def _map_coverage(self, factor: str):
        """Translates EAGLE Factor back to ISO Cover Min/Max."""
        if factor == "055" or factor == "55" or factor == "0.55":
            return 30, 80
        if factor == "075_plus" or factor == "75":
            return 75, 100
        return None, None

    def extract_classes(self, log_callback) -> List[CorineClass]:
        extracted_classes = {}

        for col in range(5, self.sheet.max_column + 1, 2):
            c_code = self.sheet.cell(row=1, column=col).value
            c_name = self.sheet.cell(row=2, column=col).value
            if c_code and c_name and str(c_code).strip() != "":
                extracted_classes[col] = CorineClass(
                    class_code=str(c_code).strip(),
                    class_name=str(c_name).strip(),
                    components=[]
                )

        if not extracted_classes:
            log_callback("❌ Error: No classes found in Header.")
            return []

        for row in range(6, self.sheet.max_row + 1):
            eagle_code = self.sheet.cell(row=row, column=2).value
            if not eagle_code or str(eagle_code).strip() not in self.code_to_enum:
                continue

            lcc_enum = self.code_to_enum[str(eagle_code).strip()]

            for col_idx, corine_obj in extracted_classes.items():
                barcode_val = self.sheet.cell(row=row, column=col_idx).value
                factor_val = self.sheet.cell(row=row, column=col_idx + 1).value

                if barcode_val is not None and str(barcode_val).strip() in ["1", "2", "3"]:
                    barcode_str = str(barcode_val).strip()
                    factor_str = str(factor_val).strip() if factor_val else None

                    # 1. Explicitly Map Semantics!
                    presence = self._map_presence_type(barcode_str)
                    c_min, c_max = self._map_coverage(factor_str)

                    # 2. Instantiate fully populated object
                    comp = LandCoverComponent(
                        lcc_type=lcc_enum,
                        eagle_value=EagleMatrixValue(barcode_str),
                        eagle_factor=factor_str,
                        presence_type=presence,
                        coverage_min=c_min,
                        coverage_max=c_max
                    )
                    corine_obj.components.append(comp)

        return list(extracted_classes.values())

class LchsXmlGenerator:
    """Generates the LChS XML tree from validated Pydantic objects."""
    def __init__(self):
        self.namespace = "http://fao.org/lchs"
        ET.register_namespace("lchs", self.namespace)

    def _prettify(self, elem) -> bytes:
        rough_string = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="    ", encoding="utf-8")

    def generate(self, corine_classes: List[CorineClass]) -> bytes:
        root = ET.Element(f"{{{self.namespace}}}Export")

        for c_class in corine_classes:
            legend_class = ET.SubElement(root, f"{{{self.namespace}}}LegendClass")
            ET.SubElement(legend_class, f"{{{self.namespace}}}Code").text = c_class.class_code
            ET.SubElement(legend_class, f"{{{self.namespace}}}Name").text = c_class.class_name
            stratum = ET.SubElement(legend_class, f"{{{self.namespace}}}Stratum")
            stratum.set("name", "Stratum 1")

            for comp in c_class.components:
                lc_element = ET.SubElement(stratum, f"{{{self.namespace}}}LC_Element")
                lc_element.set("type", getattr(comp.lcc_type, 'name', str(comp.lcc_type)))

                # Jetzt sind diese Werte gesetzt und werden korrekt geschrieben!
                if comp.presence_type:
                    ET.SubElement(lc_element, f"{{{self.namespace}}}PresenceType").text = getattr(comp.presence_type, 'name', str(comp.presence_type))
                if comp.coverage_min is not None:
                    ET.SubElement(lc_element, f"{{{self.namespace}}}CoverMin").text = str(comp.coverage_min)
                if comp.coverage_max is not None:
                    ET.SubElement(lc_element, f"{{{self.namespace}}}CoverMax").text = str(comp.coverage_max)

        return self._prettify(root)

def run_eagle_to_iso_mapping(excel_bytes: bytes, log_callback) -> bytes:
    log_callback("Initializing EagleExcelParser...")
    parser = EagleExcelParser(excel_bytes)
    log_callback("Extracting and semantically validating data...")
    validated_objects = parser.extract_classes(log_callback)
    log_callback(f"Successfully processed {len(validated_objects)} Corine classes. Generating XML...")
    generator = LchsXmlGenerator()
    return generator.generate(validated_objects)