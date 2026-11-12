import io
import xml.etree.ElementTree as ET
import openpyxl
import pytest
from pathlib import Path

from src.mapping.sssom_engine import SSSOMResolver
from src.mapping.eagle_to_iso import run_eagle_to_iso_mapping
from src.mapping.iso_to_eagle import run_iso_to_eagle_mapping
from src.python.generated.eagle_iso_models import (
    LandUnit,
    LandCoverComponent,
    BarCodeValueEnum,
    ISOPresenceEnum
)

TEST_EXCEL_PATH = Path("testdata/eagle/EAGLE Barcoding Examples CLC - v4.xlsx")
TEST_XML_PATH = Path("testdata/iso/LChS_Legend.lchs.xml")


def test_sssom_resolver_load():
    resolver = SSSOMResolver()
    assert resolver.msdf is not None
    assert not resolver.msdf.df.empty
    assert len(resolver.msdf.df) >= 20

    # Test forward lookup
    sealed = resolver.resolve_eagle_to_iso("LCC-1_1_1")
    assert sealed is not None
    assert "LC_BuildUpSurface" in sealed["object_id"] or "LC_BuiltUpSurface" in sealed["object_id"]

    # Test reverse lookup
    rev_soil = resolver.resolve_iso_to_eagle("LC_BareSoil")
    assert rev_soil is not None
    assert "LCC-1_2_2_2" in rev_soil["subject_id"]


def test_sssom_bcv_and_coverage_mapping():
    resolver = SSSOMResolver()

    # Presence mappings
    assert resolver.map_bcv_to_presence("3") == ISOPresenceEnum.Fixed
    assert resolver.map_bcv_to_presence("2") == ISOPresenceEnum.Exclusive
    assert resolver.map_bcv_to_presence("1") == ISOPresenceEnum.Conditional

    # Reverse presence mappings
    assert resolver.map_presence_to_bcv("Fixed") == BarCodeValueEnum.BCV_3
    assert resolver.map_presence_to_bcv("Exclusive") == BarCodeValueEnum.BCV_2

    # Coverage factor mappings
    c_min, c_max = resolver.factor_to_coverage("0.55")
    assert c_min == 30 and c_max == 80

    factor = resolver.coverage_to_factor(30, 80)
    assert factor == "055"


def test_eagle_to_iso_transformation():
    assert TEST_EXCEL_PATH.exists()
    wb = openpyxl.load_workbook(TEST_EXCEL_PATH, data_only=True)
    logs = []
    xml_bytes = run_eagle_to_iso_mapping(wb, "CLC-all 3 Classes", log_callback=logs.append)

    assert xml_bytes is not None and len(xml_bytes) > 1000

    # Verify XML well-formedness and structure
    root = ET.fromstring(xml_bytes)
    assert "LC_Legend" in root.tag

    classes = root.findall(".//LC_Class")
    assert len(classes) == 3

    class_codes = [c.findtext("class_map_code") for c in classes]
    assert "C112" in class_codes
    assert "C212" in class_codes
    assert "C322" in class_codes

    props = root.findall(".//LC_Properties")
    assert len(props) > 0


def test_iso_to_eagle_transformation():
    assert TEST_XML_PATH.exists()
    with open(TEST_XML_PATH, "rb") as f:
        xml_data = f.read()

    logs = []
    excel_bytes = run_iso_to_eagle_mapping(xml_data, log_callback=logs.append, use_fuzzy=True)
    assert excel_bytes is not None and len(excel_bytes) > 2000

    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb.active
    assert ws.title == "EAGLE Barcoding Matrix"

    # Verify class codes in Row 1
    row1_codes = [ws.cell(1, c).value for c in [5, 7, 9]]
    assert "CLC112" in row1_codes or "C112" in row1_codes
    assert "CLC212" in row1_codes or "C212" in row1_codes


def test_roundtrip_transformation():
    wb_in = openpyxl.load_workbook(TEST_EXCEL_PATH, data_only=True)
    xml_bytes = run_eagle_to_iso_mapping(wb_in, "CLC-all 3 Classes", lambda m: None)

    excel_bytes = run_iso_to_eagle_mapping(xml_bytes, lambda m: None, use_fuzzy=True)
    wb_out = openpyxl.load_workbook(io.BytesIO(excel_bytes), data_only=True)
    ws = wb_out.active

    assert ws.cell(1, 5).value in ["C112", "CLC112"]
    assert ws.cell(1, 7).value in ["C212", "CLC212"]
    assert ws.cell(1, 9).value in ["C322", "CLC322"]


# ---------------------------------------------------------------- extensions: land use, characteristics, irrigation

from src.mapping import extensions  # noqa: E402


def _matrix(rows, factor_for=None):
    """A one-class EAGLE matrix: rows are (code, label, barcode)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "M"
    ws["A1"], ws["E1"] = "Class Code*", "CLC999"
    ws["A2"], ws["E2"] = "Name*", "Test"
    for n, (code, label, bcv) in enumerate(rows, 6):
        ws.cell(n, 2, code)
        ws.cell(n, 3, label)
        ws.cell(n, 5, bcv)
        if factor_for and code in factor_for:
            ws.cell(n, 6, factor_for[code])
    return wb


def _xml(rows, **kwargs):
    return ET.fromstring(run_eagle_to_iso_mapping(_matrix(rows, kwargs.pop("factor_for", None)), "M", lambda m: None, **kwargs))


def _irrigation(root):
    return [c for c in root.iterfind(".//LC_Characteristics") if c.findtext("CharacteristicReference") == "LC_IrrigationCharacteristic"]


def test_cover_is_a_min_max_pair_of_repeated_elements():
    root = _xml([("LCC-1_1_1", "Sealed Artificial Surfaces and Constructions", 3)], factor_for={"LCC-1_1_1": "055"})
    (prop,) = root.iterfind(".//LC_Properties")
    assert [c.text for c in prop.findall("cover")] == ["30", "80"]  # first the minimum, then the maximum


def test_generated_class_text_does_not_say_eagle():
    root = _xml([("LCC-2_1_1", "Trees", 3)])
    (cls,) = root.iterfind(".//LC_Class")
    assert "EAGLE" not in cls.findtext("class_description").upper()
    assert cls.findtext("class_description") == "Corine class CLC999"


def test_land_use_is_written_with_its_hilucs_code():
    root = _xml([("LCC-2_2_1", "Graminoids, Grass-Like", 3), ("LUA-1_1", "Agriculture", 3)])
    (use,) = root.iterfind(".//LU_LandUse")
    assert use.findtext("LandUseCode") == "LUA-1_1" and use.findtext("hilucsCode") == "1.1"
    assert use.findtext("LandUseLabel") == "Agriculture" and use.findtext("elementPresenceType") == "Fixed"
    assert use.findtext("class_id") == "1"


def test_other_characteristics_are_written_with_their_class_and_presence():
    root = _xml([("LCC-2_2_1", "Graminoids, Grass-Like", 3), ("LCH-8_1_4", "Scattered Pattern", 1), ("LCH-4_2_4", "Perennial Water Regime", "X")])
    by_code = {c.findtext("CharacteristicCode"): c for c in root.iterfind(".//LC_Characteristics")}
    assert by_code["LCH-8_1_4"].findtext("CharacteristicReference") == "LC_GeneralCharacteristic"
    assert by_code["LCH-8_1_4"].findtext("elementPresenceType") == "Conditional"
    assert by_code["LCH-8_1_4"].findtext("BlockReference") == "LC_Graminoid"
    assert by_code["LCH-4_2_4"].findtext("CharacteristicReference") == "LC_WaterRegimeCharacteristic"
    assert by_code["LCH-4_2_4"].findtext("elementPresenceType") == "Precluded"


def test_irrigation_concepts_become_one_characteristic_with_code_list_values():
    root = _xml([
        ("LCC-2_2_1", "Graminoids, Grass-Like", 3),
        ("LCH-5_1_4_5_5", "Irrigation Carousel", 3),
        ("LCH-5_1_4_5_2", "Irrigation Applied, Method Unspecified", 3),
        ("LCH-5_1_4_6_3", "Water Course", 3),
    ])
    (irr,) = _irrigation(root)
    assert irr.findtext("irrigated") == "true"
    assert [e.text for e in irr.findall("irrigationType")] == ["centerPivot"]  # "unspecified" yields to a stated method
    assert [e.text for e in irr.findall("waterSource")] == ["surfaceWater"]
    assert [e.text for e in irr.findall("CharacteristicCode")] == ["LCH-5_1_4_5_5", "LCH-5_1_4_5_2", "LCH-5_1_4_6_3"]


def test_no_irrigation_is_not_written_as_irrigation_applied():
    root = _xml([("LCC-2_2_1", "Graminoids, Grass-Like", 3), ("LCH-5_1_4_5_1", "No Irrigation", 3)])
    (irr,) = _irrigation(root)
    assert irr.findtext("irrigated") == "false" and irr.find("irrigationType") is None


def test_excluded_irrigation_says_not_irrigated_without_a_type():
    root = _xml([("LCC-2_2_1", "Graminoids, Grass-Like", 3), ("LCH-5_1_4_5_2", "Irrigation Applied, Method Unspecified", "X")])
    (irr,) = _irrigation(root)
    assert irr.findtext("elementPresenceType") == "Precluded" and irr.findtext("irrigated") == "false"
    assert irr.find("irrigationType") is None


def test_label_wording_does_not_decide_the_block():
    """A land use that mentions "land cover", or a characteristic that merely contains "rice" / "hops"."""
    root = _xml([("LUA-6_1", "Land cover monitoring site", 3), ("LCH-9_1", "Workshops and Price Tags", 3)])
    assert len(list(root.iterfind(".//LU_LandUse"))) == 1 and not list(root.iterfind(".//LC_Properties"))
    (char,) = root.iterfind(".//LC_Characteristics")
    assert char.find("speciesName") is None


def test_plain_lcml_subset_writes_only_land_cover_irrigation_and_species():
    rows = [
        ("LCC-2_2_1", "Graminoids, Grass-Like", 3),
        ("LUA-1_1", "Agriculture", 3),
        ("LCH-8_1_4", "Scattered Pattern", 3),
        ("LCH-5_1_4_5_4", "Sprinkler Irrigation", 3),
        ("LCH-5_1_6_1_1_7", "Rice Character", 3),
        ("LCH-5_1_4_5_1", "No Irrigation", 3),
    ]
    root = _xml(rows, include_extensions=False)
    assert not list(root.iterfind(".//LU_LandUse"))
    refs = [c.findtext("CharacteristicReference") for c in root.iterfind(".//LC_Characteristics")]
    assert refs == ["LC_CultivatedAndManagedVegetationCharacteristics", "LC_FloristicAspectsCharacteristic"]
    assert root.findtext(".//irrigationType") == "Sprinkler"


def test_every_mapped_irrigation_value_is_in_its_code_list():
    data = extensions.load()
    assert {"flood", "centerPivot", "subsurfaceDrip"} <= set(data["code_lists"]["IrrigationType"])
    for attrs in data["irrigation"].values():
        assert attrs.get("irrigationType", "other") in extensions.code_list("IrrigationType")
        assert attrs.get("waterSource", "unknown") in extensions.code_list("WaterSource")


def test_characteristic_class_is_chosen_on_code_segment_boundaries():
    assert extensions.characteristic_class("LCH-5_1_4_5_4") == "LC_IrrigationCharacteristic"
    assert extensions.characteristic_class("LCH-5_1_4_9") == "LC_CultivationCharacteristic"
    assert extensions.characteristic_class("LCH-5_10") == "LC_ManagementCharacteristic"  # not LCH-5_1...
    assert extensions.characteristic_class("LCH-8_1_4") == "LC_GeneralCharacteristic"


def test_roundtrip_survives_the_extension_elements():
    wb = _matrix([("LCC-2_2_1", "Graminoids, Grass-Like", 3), ("LUA-1_1", "Agriculture", 3), ("LCH-5_1_4_5_4", "Sprinkler Irrigation", 3), ("LCH-8_1_4", "Scattered Pattern", 1)])
    xml_bytes = run_eagle_to_iso_mapping(wb, "M", lambda m: None)
    assert run_iso_to_eagle_mapping(xml_bytes, lambda m: None, use_fuzzy=True)
