"""Bar code values suggested from the logic of the text (EAGLE bar coding manual, table 3)."""

import pytest

from eagle_eye.analysis import analyze
from eagle_eye.samples import NATURAL_GRASSLAND


def bcv(text):
    """{wording: bar code value} of the classified highlights."""
    result = {}
    for m in analyze(text).mentions:
        for item in m.items:
            if item.code and item.bcv:
                result.setdefault(m.text.lower(), item.bcv)
    return result


# Manual, Figure 9: bar coding of the CLC class "Natural Grassland".
def test_natural_grassland_matches_the_manuals_values():
    found = {}
    for m in analyze(NATURAL_GRASSLAND).mentions:
        for item in m.items:
            if item.code:
                found[item.code] = item.bcv
    assert found["LCC-2_2_1"] == "3"  # the defining grassland
    for optional in ("LCC-1_2_1_1", "LCC-2_1_1", "LCC-2_1_2", "LCH-8_1_4", "LCH-5_5_2_1", "LCH-5_1_4_9"):
        assert found[optional] == "1", optional
    for excluded in ("LCH-5_1_4_7_2", "LCH-5_1_4_5_2", "LCH-5_1_4_2_2"):
        assert found[excluded] == "X", excluded


def test_plain_statement_is_defining_but_flagged_as_assumed():
    item = analyze("Areas covered by grassland.").mentions[0].items[0]
    assert item.bcv == "3" and item.bcv_basis == "assumed"


def test_and_is_cumulative_mandatory():
    values = bcv("Buildings and roads cover the area.")
    assert values["buildings"] == values["roads"] == "3"


def test_or_is_selective_mandatory():
    values = bcv("Either forest or shrubs dominate.")
    assert values["forest"] == values["shrubs"] == "2"


def test_only_is_exclusive():
    assert bcv("Land covered only by trees.")["trees"] == "5"


def test_only_one_exclusive_value_per_block():
    values = bcv("Only trees. Only grassland.")
    assert sorted(values.values()) == ["3", "5"]


def test_at_least_two_is_paired_mandatory():
    values = bcv("At least two of grassland, shrubs and trees occur together.")
    assert set(values.values()) == {"4"}


@pytest.mark.parametrize(
    "text,word",
    [
        ("Land without trees.", "trees"),
        ("Rocky areas are excluded.", "rocky areas"),
        ("The class does not include sporadically irrigated land.", "irrigated"),
    ],
)
def test_exclusion_cues_give_x(text, word):
    assert bcv(text)[word] == "X"


def test_exclusion_covers_the_whole_coordinated_group():
    values = bcv("Areas without trees or shrubs.")
    assert values["trees"] == values["shrubs"] == "X"


@pytest.mark.parametrize(
    "text,word",
    [
        ("Frequently including rocky areas.", "rocky areas"),
        ("Water bodies, e.g. lakes and rivers.", "lakes"),
        ("Shrubs also occur.", "shrubs"),
        ("Mowing is tolerated.", "mowing"),
    ],
)
def test_optional_cues_give_1(text, word):
    assert bcv(text)[word] == "1"


def test_no_or_moderate_is_a_degree_not_an_exclusion():
    # "no or moderate human influence" must not exclude the wording after "no or"
    assert "x" not in bcv("Grasslands under no or moderate influence with trees.").values()


def test_modal_with_or_is_either_or():
    # Manual, Figure 10: "can be non-irrigated or permanently irrigated" -> No Irrigation / Irrigation Applied, both 2
    values = [i.bcv for m in analyze("Fields can be non-irrigated or permanently irrigated.").mentions for i in m.items]
    assert values == ["2", "2"]


def test_parameter_values_carry_no_bar_code_value():
    analysis = analyze("Trees cover more than 30 % of the area.")
    parameter = [i for m in analysis.mentions for i in m.items if i.code == "LCH-3_13"]
    assert parameter and parameter[0].bcv is None


def test_entry_reports_the_strongest_value_and_the_reasons():
    analysis = analyze("Trees. Trees may also occur.")
    entry = next(e for e in analysis.entries if e.code == "LCC-2_1_1")
    assert entry.bcv == "3" and entry.bcv_reasons
