import io
import string
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

class EagleXslxParser:
    def __init__(self, workbook: openpyxl.Workbook, sheet_name: str, log_callback):
        self.workbook = workbook
        self.sheet = self.workbook[sheet_name]
        self.log = log_callback

        # Mapping der Original EAGLE-Zeilenbeschriftungen auf unsere Enums
        # (WICHTIG: Die Werte hier müssen exakt den LinkML-String-Werten entsprechen)
        self.lcc_mapping = {
            "Sealed Artificial Surfaces and Constructions": "SealedArtificialSurface",
            "Biotic Vegetation": "BioticVegetation",
            "Trees": "Trees",
            "Shrubs": "Shrubs",
            "Graminoids": "Graminoids",
            "Lichens, Mosses, Algae": "LichenMosses",
            "Natural Material Surfaces": "NaturalSurfaces"
        }

    def extract_classes(self) -> List[CorineClass]:
        self.log("Identifying Class-Codes...")
        classes_info = {}

        # SCHRITT 1: Finde dynamisch die Basis-Zeile, in der die Klassen-Codes stehen
        code_row = 1
        for r in range(1, 10):
            val = self.sheet.cell(row=r, column=1).value
            if val and "Class Code" in str(val):
                code_row = r
                break

        name_row = code_row + 1

        # SCHRITT 2: Klassen identifizieren (Spalten E, G, I... = Index 5, 7, 9)
        for col_idx in range(5, self.sheet.max_column + 1, 2):
            class_code = self.sheet.cell(row=code_row, column=col_idx).value
            class_name = self.sheet.cell(row=name_row, column=col_idx).value

            if class_code and str(class_code).strip() != "":
                classes_info[col_idx] = {
                    "code": str(class_code).strip(),
                    "name": str(class_name).strip() if class_name else "Unknown",
                    "components": []
                }

        self.log(f"Found {len(classes_info)} Classes. Parsing rows...")

        # SCHRITT 3: Zeilen iterieren
        start_row = name_row + 2
        for row_idx in range(start_row, self.sheet.max_row + 1):
            label_cell = self.sheet.cell(row=row_idx, column=3).value
            if not label_cell:
                continue

            if row_idx % 20 == 0:
                # Alle 20 Zeilen ein Lebenszeichen senden
                self.log(f"processing row {row_idx} of {self.sheet.max_row}...")

            label_str = str(label_cell).strip()

            lcc_string_value = None
            for key, mapped_val in self.lcc_mapping.items():
                # exaktes Matching, um Sub-Kategorien nicht versehentlich mitzunehmen
                if key in label_str:
                    lcc_string_value = mapped_val
                    break

            if lcc_string_value:
                for col_idx, class_data in classes_info.items():
                    barcode_val = self.sheet.cell(row=row_idx, column=col_idx).value
                    factor_val = self.sheet.cell(row=row_idx, column=col_idx + 1).value

                    if barcode_val is not None and str(barcode_val).strip() != "":
                        barcode_str = str(barcode_val).strip()
                        factor_str = str(factor_val).strip() if factor_val else None

                        # ensure value is unique
                        # check if there already is a Corine class (z.B. C212) for
                        # a component of the this type (e.g., "Graminoids") and if so,
                        # skip it to avoid duplicates.
                        already_exists = any(c.lcc_type == lcc_string_value for c in class_data["components"])

                        if not already_exists:
                            # 1. EAGLE Value zu ISO Presence Type
                            presence_mapping = {
                                "3": "Fixed",
                                "2": "Exclusive",
                                "1": "ConditionalTemporal"
                            }
                            presence_val = presence_mapping.get(barcode_str, "ConditionalTemporal")

                            # 2. EAGLE Factor zu Schwellwerten (Min/Max rekonstruieren)
                            cov_min = None
                            cov_max = None

                            if factor_str in ["0.55", "055", "55"]:
                                cov_min = 30
                                cov_max = 80
                            elif factor_str in ["0.75", "075", "75"]:
                                cov_min = 75
                                cov_max = 100

                            # Instanziierung
                            comp = LandCoverComponent(
                                lcc_type=lcc_string_value,
                                eagle_value=barcode_str,
                                eagle_factor=factor_str,
                                presence_type=presence_val,
                                coverage_min=cov_min,
                                coverage_max=cov_max
                            )
                            # Die Komponente wird hinzugefügt, und beim nächsten Schleifendurchlauf
                            # greift unsere `already_exists` Prüfung!
                            class_data["components"].append(comp)

        # SCHRITT 4: Validierte Objekte zusammenbauen
        self.log(f"Merging {len(class_data)} validated classes into a list of CorineClasses.")

        extracted_classes = []
        for col_idx, class_data in classes_info.items():
            if class_data["components"]:
                extracted_classes.append(
                    CorineClass(
                        class_code=class_data["code"],
                        class_name=class_data["name"],
                        components=class_data["components"]
                    )
                )

        return extracted_classes

# ==========================================
# 3. LOAD (XML Generator)
# ==========================================

class LchsXmlGenerator:
    def __init__(self, log_callback=print):
        self.log = log_callback
        self.namespace = "http://fao.org/lchs"
        ET.register_namespace("lchs", self.namespace)

    def _prettify(self, elem) -> str:
        rough_string = ET.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="    ")

    def generate_xml(self, corine_classes: List[CorineClass]):
        root = ET.Element(f"{{{self.namespace}}}Export")

        self.log(f"Generating XML for {len(corine_classes)} Corine classes.")

        for c_class in corine_classes:
            legend_class = ET.SubElement(root, f"{{{self.namespace}}}LegendClass")

            code_elem = ET.SubElement(legend_class, f"{{{self.namespace}}}Code")
            code_elem.text = c_class.class_code

            name_elem = ET.SubElement(legend_class, f"{{{self.namespace}}}Name")
            name_elem.text = c_class.class_name

            stratum = ET.SubElement(legend_class, f"{{{self.namespace}}}Stratum")
            stratum.set("name", "Stratum 1")

            for comp in c_class.components:
                lc_element = ET.SubElement(stratum, f"{{{self.namespace}}}LC_Element")
                lc_element.set("type", comp.lcc_type)

                presence = ET.SubElement(lc_element, f"{{{self.namespace}}}PresenceType")
                presence.text = comp.presence_type

                if comp.coverage_min is not None:
                    c_min = ET.SubElement(lc_element, f"{{{self.namespace}}}CoverMin")
                    c_min.text = str(comp.coverage_min)
                if comp.coverage_max is not None:
                    c_max = ET.SubElement(lc_element, f"{{{self.namespace}}}CoverMax")
                    c_max.text = str(comp.coverage_max)

        return self._prettify(root)


def run_eagle_to_iso_mapping(excel_workbook: openpyxl.Workbook, sheet_name: str, log_callback) -> bytes:
    log_callback("Initializing EagleExcelParser...")
    parser = EagleXslxParser(excel_workbook, sheet_name, log_callback)

    log_callback("Extracting and semantically validating data...")
    validated_objects = parser.extract_classes()

    log_callback(f"Successfully processed {len(validated_objects)} Corine classes. Generating XML...")
    generator = LchsXmlGenerator(log_callback)

    return generator.generate_xml(validated_objects)