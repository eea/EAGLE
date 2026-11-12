"""ISO 19144-2 LChS XML export through the eagle-iso-mapper."""

import xml.etree.ElementTree as ET

import pytest

from eagle_eye import isoexport
from eagle_eye.analysis import analyze
from tests.texts import NATURAL_GRASSLAND
from eagle_eye.vocabulary import load_vocabulary

TEXT = "Land covered by grassland, with trees that may also occur, without bare soil."

needs_mapper = pytest.mark.skipif(not isoexport.available(), reason="eagle-iso-mapper not found next to eagle-eye")


def test_every_bar_coded_element_is_sent_to_the_mapper():
    plan = isoexport.plan_export(analyze(NATURAL_GRASSLAND))
    assert {"LCC-2_2_1", "LCC-2_1_1", "LCH-8_1_4", "LCH-5_1_4_5_2"} <= set(plan.written)  # land cover, a characteristic, an excluded one
    assert plan.to_send["LCH-5_1_4_5_2"] == "X"


def test_matrix_has_the_layout_the_mapper_reads():
    vocab = load_vocabulary()
    wb = isoexport.build_matrix({"LCC-2_1_1": "3", "LCC-1_2_2_2": "X"}, vocab, "C1", "My class")
    ws = wb[isoexport.SHEET]
    assert "Class Code" in ws["A1"].value and ws["E1"].value == "C1" and ws["E2"].value == "My class"
    rows = [(r[1], r[4]) for r in ws.iter_rows(min_row=6, values_only=True) if r[1]]
    assert rows == [("LCC-1_2_2_2", "X"), ("LCC-2_1_1", "3")]  # matrix order


def test_stated_and_excluded_element_keeps_the_stated_value():
    plan = isoexport.plan_export(analyze("Trees. Areas without trees."))
    assert plan.to_send["LCC-2_1_1"] == "3"
    assert any("stated and excluded" in n for n in plan.notes)


@needs_mapper
def test_lchs_xml_from_the_mapper():
    export = isoexport.to_lchs_xml(analyze(TEXT), class_code="C99", class_name="Test class")
    root = ET.fromstring(export.xml)
    assert root.tag == "LC_Legend"
    (cls,) = root.iterfind(".//LC_Class")
    assert cls.find("class_map_code").text == "C99" and cls.find("class_name").text == "Test class"
    presence = {p.find("BlockReference").text: p.find("elementPresenceType").text for p in root.iterfind(".//LC_Properties")}
    assert presence["LC_Graminoid"] == "Fixed"  # grassland: a plainly stated element, BCV 3
    assert presence["LC_Tree"] == "Conditional"  # "may also occur": BCV 1
    assert "Precluded" in presence.values()  # "without bare soil": BCV X must not become "Exclusive"
    assert "Exclusive" not in presence.values()


@needs_mapper
def test_excluded_irrigation_is_not_written_as_irrigation():
    export = isoexport.to_lchs_xml(analyze("Arable land that is not irrigated."))
    assert b"irrigationType" not in export.xml


@needs_mapper
def test_land_use_and_characteristics_reach_the_xml():
    root = ET.fromstring(isoexport.to_lchs_xml(analyze(NATURAL_GRASSLAND)).xml)
    assert any(c.findtext("CharacteristicCode") == "LCH-8_1_4" for c in root.iterfind(".//LC_Characteristics"))


@needs_mapper
def test_generated_class_texts_say_corine_not_eagle():
    export = isoexport.to_lchs_xml(analyze(TEXT))
    (cls,) = ET.fromstring(export.xml).iterfind(".//LC_Class")
    assert cls.findtext("class_name") == "Corine class"
    assert "EAGLE" not in (cls.findtext("class_name") + cls.findtext("class_description")).upper()


@needs_mapper
def test_cover_is_written_as_a_min_max_pair():
    export = isoexport.to_lchs_xml(analyze(TEXT))
    for prop in ET.fromstring(export.xml).iterfind(".//LC_Properties"):
        low, high = (int(c.text) for c in prop.findall("cover"))  # exactly two <cover>: minimum, maximum
        assert 0 <= low <= high <= 100
