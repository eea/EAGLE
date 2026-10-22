"""The Streamlit page: picking a class for a highlight, adding a highlight, export."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from eagle_eye.analysis import analyze

APP = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture
def app():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    return at


def picker(at):
    return next(s for s in at.selectbox if s.key and s.key.startswith("pick_"))


def select_highlight(at, word):
    m = next(m for m in analyze(at.session_state["doc"]).mentions if m.text == word)
    at.session_state["selection"] = {"entries": [m.items[0].code], "mention": m.id}
    at.run()
    return m


def test_changing_the_class_of_an_active_highlight(app):
    select_highlight(app, "trees")
    picker(app).select("LCC-2_1").run()
    (override,) = app.session_state["overrides"]
    assert (override.action, override.code, override.text) == ("replace", "LCC-2_1", "trees")
    # the changed highlight stays selected, so the user sees the result
    sel = app.session_state["selection"]
    assert sel["entries"] == ["LCC-2_1"] and sel["mention"] is not None


def test_picker_offers_suggestions_first(app):
    select_highlight(app, "shrub")
    first = picker(app).options[0]
    assert first.startswith("★")


def test_marked_text_gets_a_manual_highlight(app):
    doc = app.session_state["doc"]
    start = doc.index("low productivity")
    app.session_state["pending"] = {"start": start, "end": start + len("low productivity")}
    app.run()
    picker(app).select("LCH-3_13").run()
    (override,) = app.session_state["overrides"]
    assert (override.action, override.code, override.text) == ("add", "LCH-3_13", "low productivity")
    assert app.session_state["pending"] is None


def test_remove_and_reset(app):
    m = select_highlight(app, "trees")
    next(b for b in app.button if b.label == "Remove highlight").click().run()
    assert [o.action for o in app.session_state["overrides"]] == ["remove"]
    assert app.session_state["selection"] is None

    app.session_state["overrides"] = []
    select_highlight(app, "trees")
    picker(app).select("LCC-2_1").run()
    next(b for b in app.button if b.label == "Reset to automatic").click().run()
    assert app.session_state["overrides"] == []


def test_new_document_clears_manual_changes(app):
    select_highlight(app, "trees")
    picker(app).select("LCC-2_1").run()
    app.session_state["mode"] = "✏️ Edit"
    app.run()
    app.text_area[0].set_value(app.session_state["doc"] + " Extra words.").run()
    assert len(app.session_state["overrides"]) == 1
    app.text_area[0].set_value("Completely different text without trees.").run()
    assert len(app.session_state["overrides"]) == 1  # re-anchored on the one remaining "trees"
    app.text_area[0].set_value("Nothing relevant.").run()
    assert app.session_state["overrides"] == [] and app.warning


def test_bar_code_value_can_be_set_and_cleared_by_hand(app):
    select_highlight(app, "trees")
    box = next(s for s in app.selectbox if s.key and s.key.startswith("bcv_"))
    assert box.value == "automatic"
    box.select("5").run()
    (override,) = app.session_state["overrides"]
    assert (override.action, override.code, override.text) == ("bcv", "5", "trees")
    box = next(s for s in app.selectbox if s.key and s.key.startswith("bcv_"))
    assert box.value == "5"
    box.select("automatic").run()
    assert app.session_state["overrides"] == []


def test_export_panel_lists_what_the_xml_cannot_carry(app):
    captions = " ".join(c.value for c in app.caption)
    assert "bar coded elements go into the XML" in captions
