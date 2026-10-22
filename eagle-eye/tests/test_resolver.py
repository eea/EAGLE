"""Iteration 2: concrete EAGLE classes, checked against the bar coding manual's worked examples."""

import pytest

from eagle_eye.analysis import analyze
from eagle_eye.samples import NATURAL_GRASSLAND
from eagle_eye.vocabulary import load_vocabulary

# Manual, Figure 9 ("Natural Grassland"): the elements the bar coders assigned, as far as the
# class text names them. Code values follow matrix v3.2.
GRASSLAND_GOLD = {
    "LCC-2_2_1": "Graminoids, Grass-Like",
    "LCC-1_2_1_1": "Bare Rock",
    "LCC-2_1_1": "Trees",
    "LCC-2_1_2": "Bushes, Shrubs",
    "LCH-8_1_4": "Scattered Pattern",
    "LCH-5_5_2_1": "Nature Conservation Area",
    "LCH-5_1_4_9": "Shrub Clearance",
}
GRASSLAND_EXCLUDED = {  # BCV X in the manual
    "LCH-5_1_4_7_2": "Drainage Applied",
    "LCH-5_1_4_5_2": "Irrigation Applied",
    "LCH-5_1_4_2_2": "Fertilization Applied",
}


def items(text):
    return [(i, m) for m in analyze(text).mentions for i in m.items]


def codes(text, negated=False):
    return {i.code for i, _ in items(text) if i.negated == negated and i.code}


def test_grassland_matches_the_manuals_bar_code():
    found = codes(NATURAL_GRASSLAND)
    assert set(GRASSLAND_GOLD) <= found, set(GRASSLAND_GOLD) - found


def test_grassland_negated_management_is_split_into_excluded_elements():
    assert codes(NATURAL_GRASSLAND, negated=True) >= set(GRASSLAND_EXCLUDED)


def test_headings_are_replaced_by_selectable_elements():
    vocab = load_vocabulary()
    for _, m in items(NATURAL_GRASSLAND):
        for item in m.items:
            if item.code and item.confidence != "low":
                assert not vocab.get(item.code).is_heading, item.code


def test_mowing_without_detail_uses_the_unspecified_element():
    (item, _), *_ = items("Regular mowing is applied.")
    assert item.code == "LCH-5_1_4_8_1_2"
    assert any("heading" in r for r in item.reasons)


def test_text_naming_the_detail_selects_the_specific_element():
    assert "LCH-5_1_11_1_3" in codes("Extensive grazing takes place.")


def test_non_wording_maps_to_the_no_element():
    # Manual, Figure 10: "can be non-irrigated or permanently irrigated" -> No Irrigation + Irrigation Applied
    found = codes("Fields can be non-irrigated or permanently irrigated.")
    assert {"LCH-5_1_4_5_1", "LCH-5_1_4_5_2"} <= found


def test_definition_that_names_the_wording_is_offered_as_alternative():
    (analysis,) = [analyze("Arable land is used.")]
    arable = next(m for m in analysis.mentions if m.text.lower() == "arable land")
    assert "LUA-1_1_1" in {a.code for a in arable.alternatives}


def test_percentage_applying_to_trees_is_crown_cover_density():
    found = codes("Trees cover more than 30 % of the area.")
    assert "LCH-3_13" in found


def test_pattern_and_parameter_are_linked_to_the_land_cover_they_describe():
    analysis = analyze("Areas with scattered trees.")
    scattered = next(m for m in analysis.mentions if m.text == "scattered")
    trees = next(m for m in analysis.mentions if m.text == "trees")
    assert scattered.applies_to == trees.id


def test_context_domain_is_summarised():
    summary = analyze("Irrigated arable land with wheat, fertilised and drained.").summary
    assert "agriculture" in summary["domains"]


def test_excludes_note_vetoes_an_element():
    # "Reeds and bamboo" are excluded from LCC-2_2_1_1 (Grasses, Sedges, Rushes, Cereals).
    analysis = analyze("Reeds along the lake shore.")
    reeds = next(m for m in analysis.mentions if m.text.lower() == "reeds")
    assert reeds.items[0].code == "LCC-2_2_1_2"


def test_wording_without_an_element_stays_type_only():
    (item, mention), *_ = items("Land under moderate human influence.")
    assert mention.block == "LUA" and item.code is None and item.confidence == "none"


@pytest.mark.parametrize("text", ["", "   ", "No relevant wording here at all."])
def test_empty_and_irrelevant_text(text):
    assert analyze(text).entries == []


def test_entries_carry_definition_and_reasons():
    analysis = analyze("Mowing applied once per year on grassland.")
    entry = next(e for e in analysis.entries if e.code and e.code.startswith("LCC-2_2_1"))
    assert entry.definition and entry.reasons
