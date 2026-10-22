"""Manual corrections of the analysis."""

from eagle_eye.analysis import analyze
from eagle_eye.overrides import Override, clear_bcv, put, reanchor, remove, reset
from eagle_eye.samples import NATURAL_GRASSLAND

TEXT = "Trees and scattered shrubs, not drained or irrigated, under moderate human influence."


def span(text, word):
    start = text.index(word)
    return start, start + len(word)


def mention(analysis, word):
    return next(m for m in analysis.mentions if m.text == word)


def test_replace_changes_the_class_and_marks_it_manual():
    start, end = span(TEXT, "Trees")
    analysis = analyze(TEXT, overrides=[Override(start, end, "Trees", "replace", "LCC-2_1")])
    m = mention(analysis, "Trees")
    assert m.items[0].code == "LCC-2_1"
    assert m.items[0].confidence == "manual" and m.items[0].origin == "changed"
    assert any("automatic match" in r for r in m.items[0].reasons)


def test_replace_in_another_block_recolours_the_highlight():
    start, end = span(TEXT, "Trees")
    analysis = analyze(TEXT, overrides=[Override(start, end, "Trees", "replace", "LUA-1_2")])
    assert mention(analysis, "Trees").block == "LUA"


def test_replace_one_class_of_a_negated_list():
    start, end = span(TEXT, "not drained or irrigated")
    analysis = analyze(TEXT, overrides=[Override(start, end, "not drained or irrigated", "replace", "LCH-5_1_4_7_3", index=0)])
    items = mention(analysis, "not drained or irrigated").items
    assert items[0].code == "LCH-5_1_4_7_3" and items[0].negated  # exclusion is a property of the wording
    assert items[1].origin == "automatic"


def test_remove_drops_the_highlight():
    start, end = span(TEXT, "scattered")
    analysis = analyze(TEXT, overrides=[Override(start, end, "scattered", "remove")])
    assert "scattered" not in [m.text for m in analysis.mentions]


def test_manual_highlight_is_added_and_overrides_what_it_covers():
    start, end = span(TEXT, "moderate human influence")
    analysis = analyze(TEXT, overrides=[Override(start, end, "moderate human influence", "add", "LUA-6_3")])
    m = mention(analysis, "moderate human influence")
    assert m.source == "manual" and m.items[0].code == "LUA-6_3" and m.block == "LUA"
    assert any(e.code == "LUA-6_3" and e.confidence == "manual" for e in analysis.entries)


def test_manual_highlight_replaces_overlapping_automatic_ones():
    start = TEXT.index("Trees")
    end = TEXT.index("shrubs") + len("shrubs")
    analysis = analyze(TEXT, overrides=[Override(start, end, TEXT[start:end], "add", "LCC-2_1")])
    texts = [m.text for m in analysis.mentions]
    assert TEXT[start:end] in texts and "Trees" not in texts and "scattered" not in texts


def test_mention_ids_and_links_stay_consistent_after_overrides():
    start, end = span(TEXT, "Trees")
    analysis = analyze(TEXT, overrides=[Override(start, end, "Trees", "remove")])
    assert [m.id for m in analysis.mentions] == list(range(len(analysis.mentions)))
    scattered = mention(analysis, "scattered")
    shrubs = mention(analysis, "shrubs")
    assert scattered.applies_to == shrubs.id


def test_put_remove_reset():
    a = Override(0, 5, "Trees", "replace", "LCC-2_1")
    b = Override(0, 5, "Trees", "replace", "LCC-2_1_1")
    assert put([a], b) == [b]
    assert remove([a], 0, 5, "Trees") == [Override(0, 5, "Trees", "remove")]
    add = Override(0, 5, "Trees", "add", "LCC-2_1")
    assert remove([add], 0, 5, "Trees") == []
    assert reset([a, add], 0, 5) == [add]


def test_reanchor_follows_edits_and_drops_lost_wording():
    ov = [Override(4, 9, "trees", "replace", "LCC-2_1"), Override(0, 4, "gone", "remove")]
    kept, dropped = reanchor(ov, "Old trees and shrubs")
    assert kept == [Override(4, 9, "trees", "replace", "LCC-2_1")] and dropped == 1
    kept, dropped = reanchor(ov[:1], "Some more words before the trees")
    assert kept[0].start == "Some more words before the trees".index("trees") and dropped == 0


def test_bcv_override_sets_the_value_and_survives_a_class_change():
    start, end = span(TEXT, "Trees")
    bcv = Override(start, end, "Trees", "bcv", "5")
    analysis = analyze(TEXT, overrides=[bcv])
    item = mention(analysis, "Trees").items[0]
    assert (item.bcv, item.bcv_basis) == ("5", "manual")
    kept = put([bcv], Override(start, end, "Trees", "replace", "LCC-2_1"))
    assert bcv in kept
    assert mention(analyze(TEXT, overrides=kept), "Trees").items[0].bcv == "5"
    assert clear_bcv(kept, start, end) == [kept[1]]


def test_bcv_x_override_marks_the_class_as_excluded():
    start, end = span(TEXT, "Trees")
    analysis = analyze(TEXT, overrides=[Override(start, end, "Trees", "bcv", "X")])
    assert any(e.code == "LCC-2_1_1" and e.negated and e.bcv == "X" for e in analysis.entries)
