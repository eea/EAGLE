"""Sections of a CLC class description (CLC2018 Nomenclature illustrated guide).

Each class of the guide is written in the same structure; the headings tell how to read
the wording below them:

* "This class is not applicable for:" / "This class excludes:": instances and land cover
  types that do not belong to the class. What they name is excluded (bar code value X)
  unless the class names the same element as part of itself elsewhere; then the line only
  describes an instance of another class.
* "Generalisation:": advice for mapping (minimum widths, areas below 25 ha, how to merge
  neighbouring polygons). It is not about what the class is, so its wording is set aside.
* "Particularities:" / "Particularity of class 321: ...": special cases of the class,
  i.e. optional variants.

Other headings (Clarification, applicable for, includes, typical visible characteristics)
are part of the class and read as usual; they only end the section before them.
"""

import re
from dataclasses import dataclass

EXCLUDED = "excluded"
GENERALISATION = "generalisation"
PARTICULARITY = "particularity"

_HEADINGS = (
    (EXCLUDED, r"this\s+class\s+is\s+not\s+applicable\s+for"),
    (EXCLUDED, r"this\s+class\s+excludes"),
    (GENERALISATION, r"generali[sz]ations?"),
    (PARTICULARITY, r"particularit(?:y|ies)[^:\n]{0,80}?"),
    (None, r"clarification"),
    (None, r"this\s+class\s+is\s+applicable\s+for"),
    (None, r"this\s+heading\s+is\s+applicable\s+for"),
    (None, r"this\s+class\s+includes"),
    (None, r"typical\s+visible\s+characteristics"),
)
_HEADING = re.compile(
    r"(?<![\w-])(?P<title>" + "|".join(f"(?P<h{i}>{p})" for i, (_, p) in enumerate(_HEADINGS)) + r")\s*:",
    re.IGNORECASE,
)
_CLASS_TITLE = re.compile(r"^[ \t]*\d{3}[ \t]+\S[^\n]*$", re.MULTILINE)  # "322 Moors and heathland"

LABELS = {
    EXCLUDED: "excluded from the class",
    GENERALISATION: "generalisation advice",
    PARTICULARITY: "particularity (special case)",
}


@dataclass(frozen=True)
class Section:
    kind: str  # EXCLUDED | GENERALISATION | PARTICULARITY
    title: str  # the heading as written
    start: int  # first character after the heading's colon
    end: int


def find_sections(text: str) -> list[Section]:
    """The sections that change how their wording is read, each up to the next heading."""
    marks = [(m.start(), m.end(), next(i for i in range(len(_HEADINGS)) if m.group(f"h{i}")), m.group("title")) for m in _HEADING.finditer(text)]
    titles = {m.start() for m in _CLASS_TITLE.finditer(text)}
    sections = []
    for start, after, which, title in marks:
        kind = _HEADINGS[which][0]
        if kind is None:
            continue
        # A particularity has headings of its own ("This heading is applicable for", "This class
        # includes"): they belong to it. Any other section ends at the next heading.
        ends = titles | {s for s, _, w, _ in marks if kind != PARTICULARITY or _HEADINGS[w][0] is not None}
        end = next((b for b in sorted(ends) if b > after), len(text))
        sections.append(Section(kind, " ".join(title.split()), after, end))
    return sections


def section_of(sections: list[Section], position: int) -> Section | None:
    return next((s for s in sections if s.start <= position < s.end), None)
