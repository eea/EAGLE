"""Streamlit bridge for the annotator front end (eagle_eye/frontend).

One small component renders both panes (annotated text, class pane) so they share
look, colours and click handling. Clicks come back as the new selection.
"""

from pathlib import Path

import streamlit.components.v1 as components

_annotator = components.declare_component(
    "eagle_annotator", path=str(Path(__file__).resolve().parent / "frontend")
)


def annotator(payload: dict, view: str, selection: dict | None, key: str, pending: dict | None = None) -> dict | None:
    """Render `view` ("text" or "classes").

    Returns after a click {"selection", "nonce"}, or after the user marks some text
    {"range": {"start", "end"}, "selection": None, "nonce"}. `pending` is such a
    marked range that is still waiting for a class.
    """
    return _annotator(payload=payload, view=view, selection=selection, pending=pending, key=key, default=None)
