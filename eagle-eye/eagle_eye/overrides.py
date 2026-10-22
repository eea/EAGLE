"""Manual corrections of the automatic analysis.

An override is anchored to a span of the text:

* ``replace``: the user picked a different class for a highlight (``index`` says
  which of its classes, for a highlight that stands for several);
* ``bcv``: the user set the bar code value of a highlight's class (``code`` holds it);
* ``remove``: the user dropped a highlight;
* ``add``: the user marked a span of text and assigned a class (a manual highlight).

Overrides survive edits of the text: they are re-anchored on the text they were
made on and dropped only if that wording is gone.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Override:
    start: int
    end: int
    text: str  # the wording at [start, end): lets the override follow edits
    action: str  # replace | remove | add | bcv
    code: str | None = None
    index: int = 0

    @property
    def key(self) -> tuple:
        return (self.start, self.end, self.action, self.index if self.action in ("replace", "bcv") else 0)


def put(overrides: list[Override], new: Override) -> list[Override]:
    """Add `new`, replacing whatever it supersedes on the same span."""
    span = (new.start, new.end)
    kept = []
    for old in overrides:
        if (old.start, old.end) != span:
            kept.append(old)
        elif new.action == "bcv":
            if not (old.action == "bcv" and old.index == new.index):
                kept.append(old)
        elif new.action == "replace":
            # a new class keeps the bar code values the user set, and the other classes of the highlight
            if old.action == "bcv" or (old.action == "replace" and old.index != new.index):
                kept.append(old)
        # "add" and "remove" supersede everything on the span
    kept.append(new)
    return kept


def reanchor(overrides: list[Override], text: str) -> tuple[list[Override], int]:
    """Follow the overrides onto an edited text; returns (kept, number dropped)."""
    kept, dropped = [], 0
    for ov in overrides:
        if text[ov.start : ov.end] == ov.text:
            kept.append(ov)
            continue
        hits, pos = [], text.find(ov.text)
        while pos != -1 and ov.text:
            hits.append(pos)
            pos = text.find(ov.text, pos + 1)
        if not hits:
            dropped += 1
            continue
        start = min(hits, key=lambda h: abs(h - ov.start))
        kept.append(Override(start, start + len(ov.text), ov.text, ov.action, ov.code, ov.index))
    return kept, dropped


def remove(overrides: list[Override], start: int, end: int, text: str) -> list[Override]:
    """Drop the highlight at a span: a manual one vanishes, an automatic one is suppressed."""
    manual = any(o.action == "add" and (o.start, o.end) == (start, end) for o in overrides)
    kept = [o for o in overrides if (o.start, o.end) != (start, end)]
    return kept if manual else kept + [Override(start, end, text, "remove")]


def reset(overrides: list[Override], start: int, end: int) -> list[Override]:
    """Forget the manual changes at a span (automatic highlights return to their automatic class)."""
    return [o for o in overrides if (o.start, o.end) != (start, end) or o.action == "add"]


def clear_bcv(overrides: list[Override], start: int, end: int, index: int = 0) -> list[Override]:
    """Back to the bar code value suggested from the text."""
    return [o for o in overrides if not (o.action == "bcv" and (o.start, o.end, o.index) == (start, end, index))]
