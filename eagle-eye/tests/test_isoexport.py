"""ISO 19144-2 LChS XML export through the eagle-iso-mapper."""

import xml.etree.ElementTree as ET

import pytest

from eagle_eye import isoexport
from eagle_eye.analysis import analyze
from eagle_eye.samples import NATURAL_GRASSLAND
from eagle_eye.vocabulary import load_vocabulary

TEXT = "Land covered by grassland, with trees that may also occur, without bare soil."

needs_mapper = pytest.mark.skipif(not isoexport.available(), reason="eagle-iso-mapper not found next to eagle-eye")


def test_plan_separates_what_the_mapper_can_write():
    plan = isoexport.plan_export(analyze(NATURAL_GRASSLAND))
    assert {"LCC-2_2_1", "LCC-2_1_1", "LCC-1_2_1_1"} <= set(plan.written)
    reasons = " ".join(plan.not_written)
    assert "LCH-8_1_4 Scattered Pattern" in reasons  # a characteristic the mapper does not write
    assert "LCH-5_1_4_5_2" in reasons and "excluded" in reasons  # excluded irrigation must not turn into irrigation


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
def test_excluded_irrigation_is_not_written_as_a_characteristic():
    export = isoexport.to_lchs_xml(analyze("Arable land that is not irrigated."))
    assert b"irrigationType" not in export.xml
