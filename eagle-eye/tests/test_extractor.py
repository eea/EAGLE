import pytest

from eagle_eye.analysis import analyze
from eagle_eye.extractor import extract
from eagle_eye.lexicon import RULES
from eagle_eye.samples import NATURAL_GRASSLAND
from eagle_eye.vocabulary import load_vocabulary

# What the reference illustration highlights in the CLC 3.2.1 definition.
ILLUSTRATION = {
    "Grasslands": "LCC",
    "moderate human influence": "LUA",
    "rocky areas": "LCC",
    "(semi-)natural vegetation": "LCC",
    "herbaceous vegetation": "LCC",
    "shrub": "LCC",
    "scattered": "LCH",
    "trees": "LCC",
    "mineral outcrops": "LCC",
    "nature conservation": "LCH",
    "(not drained, irrigated, sown, fertilized)": "LCH",
    "Maintenance mowing": "LCH",
    "shrub clearance": "LCH",
}


def spans(text):
    return {m.text: m.block for m in extract(text)}


def test_vocabulary_has_all_three_blocks():
    vocab = load_vocabulary()
    blocks = {c.block for c in vocab.concepts}
    assert blocks == {"LCC", "LUA", "LCH"}
    assert len(vocab.concepts) == 979


def test_every_rule_code_exists_in_vocabulary():
    vocab = load_vocabulary()
    missing = [(r.id, c) for r in RULES for c in r.codes if c not in vocab]
    assert not missing


def test_every_rule_block_matches_its_codes():
    vocab = load_vocabulary()
    # Rules may list a cross-block alternative after the primary code, never before it.
    wrong = [r.id for r in RULES if r.codes and vocab.get(r.codes[0]).block != r.block]
    assert not wrong


@pytest.mark.parametrize("text,block", ILLUSTRATION.items())
def test_illustration_highlights(text, block):
    found = spans(NATURAL_GRASSLAND)
    assert found.get(text) == block, f"{text!r} not found as {block}; got {found}"


def test_mentions_do_not_overlap_and_match_text():
    a = analyze(NATURAL_GRASSLAND)
    for m in a.mentions:
        assert a.text[m.start : m.end] == m.text
    ordered = sorted(a.mentions, key=lambda m: m.start)
    assert all(x.end <= y.start for x, y in zip(ordered, ordered[1:]))


def test_longest_label_wins_over_shorter_rule():
    found = spans("Shrub clearance is applied.")
    assert found == {"Shrub clearance": "LCH"}


def test_negated_management_is_flagged_and_wrapped():
    (m,) = [m for m in extract("Arable land (not drained, irrigated or fertilised).") if m.negated]
    assert m.text == "(not drained, irrigated or fertilised)"
    assert m.block == "LCH"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("covers 30-80 % of the area", "30-80 %"),
        ("more than 50 % and less than 80%", "more than 50 %"),
        ("covers 30 % to 80 % of the area", "30 % to 80 %"),
        ("trees taller than 5 m", "taller than 5 m"),
        ("larger than 25 ha", "larger than 25 ha"),
    ],
)
def test_parameters_become_lch(text, expected):
    found = spans(text)
    assert found.get(expected) == "LCH", found


def test_modifier_is_absorbed_into_management_term():
    assert spans("Extensive grazing occurs.").get("Extensive grazing") == "LCH"


def test_plurals_and_hyphens_match_labels():
    found = spans("Fields with broad-leaved trees and grass-like plants.")
    assert found["trees"] == "LCC"


def test_entries_group_mentions_by_concept():
    a = analyze(NATURAL_GRASSLAND)
    grass = next(e for e in a.entries if e.code == "LCC-2_2_1")
    assert len(grass.mention_ids) >= 2
    assert grass.breadcrumb.startswith("Biotic, Vegetation")


def test_empty_text():
    assert analyze("").mentions == []
