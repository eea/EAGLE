"""CLC guide sections, wording variants (case, number, spelling) and stemming."""

import pytest

from eagle_eye.analysis import analyze
from eagle_eye.extractor import extract
from eagle_eye.overrides import Override
from tests.texts import NATURAL_GRASSLAND, NATURAL_GRASSLAND_GUIDE
from eagle_eye.sections import EXCLUDED, GENERALISATION, PARTICULARITY, find_sections
from eagle_eye.textnorm import lemma


def where(analysis, word, section=None):
    return [m for m in analysis.mentions if m.text.lower() == word.lower() and (section is None or m.section == section)]


# ---------------------------------------------------------------- sections


def test_sections_are_found_with_their_extent():
    text = NATURAL_GRASSLAND_GUIDE
    sections = find_sections(text)
    found = {s.kind: s for s in sections}
    assert [s.kind for s in sections] == [EXCLUDED, EXCLUDED, GENERALISATION, PARTICULARITY]
    not_applicable, excludes = sections[0], sections[1]
    assert "fallow land" in text[not_applicable.start : not_applicable.end]
    assert text[excludes.start : excludes.end].strip() == "No entry"
    assert "heathlands" in text[found[GENERALISATION].start : found[GENERALISATION].end]
    # the particularity's own headings do not end it
    particularity = text[found[PARTICULARITY].start : found[PARTICULARITY].end]
    assert "Alpine grasslands" in particularity and "livestock units" in particularity


def test_headings_need_their_colon():
    assert find_sections("The generalisation of areas below 25 ha. This class excludes trees.") == []


def test_headings_can_stand_inline():
    (section,) = find_sections("Forest. This class excludes: orchards (class 222).")
    assert section.kind == EXCLUDED


def test_not_applicable_wording_is_excluded_unless_the_class_states_it():
    analysis = analyze(NATURAL_GRASSLAND_GUIDE)
    (fallow,) = where(analysis, "fallow land")
    assert fallow.items[0].bcv == "X" and fallow.items[0].negated and not fallow.muted
    assert any(e.code == "LCH-5_1_6_98" and e.negated for e in analysis.entries)
    # "grassland" is the class itself: named in the list as part of an instance of another class
    for m in where(analysis, "grassland", EXCLUDED):
        assert m.muted and m.items[0].bcv is None


def test_muted_wording_makes_no_class_entry():
    analysis = analyze(NATURAL_GRASSLAND_GUIDE)
    muted_ids = {m.id for m in analysis.mentions if m.muted}
    assert muted_ids
    for entry in analysis.entries:
        assert not muted_ids & set(entry.mention_ids)


def test_generalisation_is_mapping_advice_not_class_content():
    analysis = analyze(NATURAL_GRASSLAND_GUIDE)
    (heath,) = where(analysis, "heathlands")
    assert heath.section == GENERALISATION and heath.muted and heath.items[0].bcv is None
    assert not any(e.code == "LCC-2_1_2_2" for e in analysis.entries)


def test_particularity_is_optional():
    analysis = analyze(NATURAL_GRASSLAND_GUIDE)
    inside = [i for m in analysis.mentions if m.section == PARTICULARITY for i in m.items if i.code]
    assert inside and {i.bcv for i in inside} == {"1"}
    assert all(not m.muted for m in analysis.mentions if m.section == PARTICULARITY)


def test_text_without_headings_is_unchanged():
    assert all(m.section is None and not m.muted for m in analyze(NATURAL_GRASSLAND).mentions)


def test_class_wording_outside_the_sections_keeps_its_values():
    analysis = analyze(NATURAL_GRASSLAND_GUIDE)
    grass = next(e for e in analysis.entries if e.code == "LCC-2_2_1")
    assert grass.bcv == "3"
    drained = {e.code: e for e in analysis.entries if e.negated}
    assert {"LCH-5_1_4_7_2", "LCH-5_1_4_5_2", "LCH-5_1_4_8_1_2"} <= set(drained)


# ---------------------------------------------------------------- human influence


def test_minimum_human_interference_is_one_land_use_span():
    spans = {m.text: m.block for m in extract(NATURAL_GRASSLAND)}
    assert spans.get("moderate human influence") == "LUA"
    assert spans.get("minimum human\ninterference", spans.get("minimum human interference")) == "LUA"
    assert "human interference" not in spans


@pytest.mark.parametrize("degree", ["moderate", "minimum", "minimal", "low", "considerable", "no"])
def test_degrees_of_human_influence_belong_to_the_span(degree):
    (m,) = [m for m in extract(f"Land under {degree} human influence.") if m.block == "LUA"]
    assert m.text == f"{degree} human influence"


# ---------------------------------------------------------------- case, number, stemming


def test_stems_ignore_case_number_and_spelling():
    assert lemma("Grasslands") == lemma("grassland") == lemma("GRASSLAND")
    assert lemma("fertilised") == lemma("fertilized") == lemma("Fertilization")
    assert lemma("irrigated") == lemma("irrigation")
    assert lemma("Shrubs") == lemma("shrub")


def test_same_wording_gets_the_same_class_and_confidence_in_any_form():
    results = {}
    for form in ("grassland", "Grasslands", "GRASSLAND", "grasslands"):
        analysis = analyze(f"Areas with {form} and lakes, and, elsewhere, other things. {form.capitalize()} dominates.")
        items = [i for m in analysis.mentions if m.text.lower() == form.lower() for i in m.items]
        assert items
        results[form] = {(i.code, i.confidence, round(i.score, 3)) for i in items}
    assert len({frozenset(r) for r in results.values()}) == 1, results


def test_confidence_does_not_depend_on_the_sentence():
    analysis = analyze(NATURAL_GRASSLAND)
    grass = [i for m in analysis.mentions if m.text.lower().startswith("grassland") for i in m.items]
    assert len(grass) >= 3 and len({(i.code, i.confidence, round(i.score, 3)) for i in grass}) == 1


def test_inflected_forms_reach_the_eagle_label():
    # label "Afforestation" (LCH-5_2_10_4)
    hits = {m.items[0].code for m in analyze("The land was afforested in 1990.").mentions if m.items}
    assert "LCH-5_2_10_4" in hits


# ---------------------------------------------------------------- manual and expert reading of lists

AIRPORT = """Airports installations.
This class is applicable for:
- civil airports with sealed runway;
This class includes:
- terminals, hangars and buildings;
- technical installations (radars, antennas, towers);
This class is not applicable for:
- sport airports in agriculture and forestry.
"""


def plain(analysis, word):
    return next(i for m in analysis.mentions if m.text.lower() == word for i in m.items if i.code)


def test_lists_are_found_only_on_request():
    assert [s.kind for s in find_sections(AIRPORT)] == [EXCLUDED]
    assert [s.kind for s in find_sections(AIRPORT, lists=True)] == ["applicable", "includes", EXCLUDED]


def test_the_manual_value_is_kept_and_the_clcplus_practice_noted():
    analysis = analyze(AIRPORT)
    item = plain(analysis, "buildings")
    assert (item.bcv, item.bcv_basis) == ("3", "assumed")
    assert (item.other_bcv, item.other_label) == ("2", "CLCplus practice")
    assert "of 64 cases" in item.other_note and "follows the bar coding manual" in item.other_note
    entry = next(e for e in analysis.entries if e.code == item.code)
    assert (entry.bcv, entry.other_bcv, entry.other_label) == ("3", "2", "CLCplus practice")


def test_no_note_for_cues_exclusions_and_the_definition():
    analysis = analyze(AIRPORT)
    for word in ("agriculture", "forestry", "airports"):  # excluded, or in the definition sentence
        assert plain(analysis, word).other_bcv is None
    cue = analyze("This class includes:\n- trees, e.g. oaks and shrubs.")
    shrubs = plain(cue, "shrubs")  # "e.g." is an explicit cue (optional, 1)
    assert (shrubs.bcv, shrubs.bcv_basis, shrubs.other_bcv) == ("1", "cue", None)


def test_text_without_lists_has_no_note():
    assert all(i.other_bcv is None for m in analyze(NATURAL_GRASSLAND).mentions for i in m.items)


def test_value_2_alone_is_flagged_but_kept():
    pair = analyze("Land with trees or shrubs.")
    assert [e.bcv for e in pair.entries] == ["2", "2"]
    assert not any("selective" in r for e in pair.entries for r in e.bcv_reasons)

    start = "Land with trees.".index("trees")
    forced = analyze("Land with trees.", overrides=[Override(start, start + 5, "trees", "bcv", "2")])
    (entry,) = forced.entries
    assert entry.bcv == "2" and any("selective" in r for r in entry.bcv_reasons)
    assert any("selective" in r for m in forced.mentions for i in m.items for r in i.bcv_reasons)
