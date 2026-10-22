"""Streamlit bridge for the annotator front end (eagle_eye/frontend).

One small component renders both panes (annotated text, class pane) so they share
look, colours and click handling. Clicks come back as the new selection.
"""

from pathlib import Path

import streamlit.components.v1 as components

_annotator = components.declare_component(
    "eagle_annotator", path=str(Path(__file__).resolve().parent / "frontend")
)


def annotator(payload: dict, view: str, selection: dict | None, key: str) -> dict | None:
    """Render `view` ("text" or "classes"); returns {"selection", "nonce"} after a click."""
    return _annotator(payload=payload, view=view, selection=selection, key=key, default=None)
