"""Suggest EAGLE bar code values (BCV) from the logic of the text.

The bar coding manual defines the values by the role an element plays in a class
definition:

  X  excluded by definition                       "not drained", "without trees"
  1  optional, typical, not mandatory             "frequently including", "e.g.", "also occur", "tolerated"
  2  selective mandatory, EITHER-OR               "A or B" (at least one must be present)
  3  cumulative mandatory, AND                    "A and B", or a plainly stated element
  4  paired mandatory, at least two of a group    "at least two of A, B, C"
  5  exclusive mandatory, ONLY-THIS-ONE           "only A", "exclusively A"

Wording is read per clause (sentence, or part of one split at ";", "but", "however"):
cues in front of an element apply to it and what follows in the clause, cues after it
apply to what came before ("... also occur"). Elements joined by "and" / "or" / commas
form a group that shares its logic. Without any cue an explicitly named element is taken
as defining (3) and flagged as assumed.
"""

import re

from .extractor import Item, Mention
from .vocabulary import load_vocabulary

_BREAK = re.compile(r"(?<!e\.g\.)(?<!i\.e\.)(?<=[.!?])\s|[;:\n]")  # "e.g. lakes" does not end a sentence
_SOFT_BREAK = re.compile(r"\b(?:but|however|whereas|while|although|though)\b", re.IGNORECASE)

_STRONG_OPTIONAL = (
    r"frequently|often|sometimes|occasionally|typically|usually|commonly|rarely|exceptionally|"
    r"e\.g\.|such as|for example|for instance|besides|in addition|tolerated|allowed|permitted|"
    r"(?:also |may |can |could |might )?occurs?|are possible|is possible"
)
_MODAL = r"may|might|can|could|possibly|optionally|possible"
_EXCLUDING = (
    r"no|not|without|excluding|except|excludes?|never|free of|devoid of|absence of|lack of|"
    r"does not include|do not include|not including"
)
_ONLY = r"only|exclusively|solely|purely|merely|nothing but|nothing else than"
_PAIRED = r"at least two|two or more|at least 2"

_LEAD_TAIL = 60  # characters in front of an element that cues about it can live in

# "occur" alone is a weak hint ("...which occur in..."), so it counts only with "also / may / can / ..."
_STRONG_LEAD = re.compile(rf"(?<!\w)(?:{_STRONG_OPTIONAL})(?!\w)", re.IGNORECASE)  # \b fails after "e.g."
_STRONG_TRAIL = re.compile(
    r"\b(?:also occurs?|occurs? (?:occasionally|sometimes)|(?:may|can) occur|is tolerated|are tolerated|tolerated|allowed|"
    r"permitted|are possible|is possible|(?:may|can) be present)\b",
    re.IGNORECASE,
)
# A trailing cue ("... also occur") belongs to the phrase it ends; ", with trees that may occur" opens a new one.
_NEW_PHRASE = re.compile(r",\s*(?:with|which|that|where|while|whose|in|on|under)\b", re.IGNORECASE)
_MODAL_ANY = re.compile(rf"\b(?:{_MODAL})\b", re.IGNORECASE)
_EXCLUDING_LEAD = re.compile(rf"\b(?P<cue>{_EXCLUDING})\W+(?:[\w-]+\W+){{0,2}}$", re.IGNORECASE)
_EXCLUDING_TRAIL = re.compile(
    r"^\W*(?:[\w-]+\W+){0,1}(?:is|are|being)?\s*(?:excluded|not included|not part|absent|not allowed|not permitted)\b", re.IGNORECASE
)
_ONLY_LEAD = re.compile(rf"\b(?P<cue>{_ONLY})\W+(?:[\w-]+\W+){{0,2}}$", re.IGNORECASE)
_ONLY_TRAIL = re.compile(rf"^\W*(?:[\w-]+\W+){{0,2}}(?:{_ONLY})\b", re.IGNORECASE)
_PAIRED_LEAD = re.compile(rf"\b(?:{_PAIRED})(?: of)?\W+(?:[\w-]+\W+){{0,3}}$", re.IGNORECASE)
_NO_OR = re.compile(r"\bno\s+or\s+\w+\W*$", re.IGNORECASE)  # "under no or moderate influence": a degree, not an exclusion
_CONNECTOR = re.compile(
    r"^[\s,]*(?:(?:(?:and/or|and|or|as well as|plus|&|either)\b[\s,]*)+)?(?:(?:of|with|the|a|an|other)\s+)*(?:\w+ly\s+)?$",
    re.IGNORECASE,
)

STRENGTH = {"5": 5, "3": 4, "4": 3, "2": 2, "1": 1}


def _clauses(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in _BREAK.finditer(text):
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(text)))
    return [s for s in spans if s[1] > s[0]]


def _subclause(text: str, clause: tuple[int, int], mention: Mention) -> tuple[int, int]:
    """Bounds of the part of the clause the mention stands in (split at "but", "however", ...)."""
    start, end = clause
    for m in _SOFT_BREAK.finditer(text, clause[0], clause[1]):
        if m.end() <= mention.start:
            start = m.end()
        elif m.start() >= mention.end:
            end = min(end, m.start())
            break
    return start, end


def _state(text: str, clause: tuple[int, int], m: Mention) -> tuple[str, str]:
    """Role of one wording: X excluded, E only, O optional, W modal (weak optional), M plain."""
    if any(i.negated for i in m.items):
        return "X", "negated in the text"
    start, end = _subclause(text, clause, m)
    lead, trail = text[max(start, m.start - _LEAD_TAIL) : m.start], text[m.end : end]
    before, after = text[start : m.start], trail

    if not _NO_OR.search(lead):
        if cue := _EXCLUDING_LEAD.search(lead):
            return "X", f"excluded by '{cue.group('cue')}'"
    if cue := _EXCLUDING_TRAIL.search(after):
        return "X", f"excluded: '{cue.group().strip(' ,.')}'"
    if cue := _ONLY_LEAD.search(lead):
        return "E", f"'{cue.group('cue')}' limits the class to this element"
    if cue := _ONLY_TRAIL.search(after):
        return "E", "'only' limits the class to this element"
    cue = _STRONG_TRAIL.search(after)
    if cue and not _NEW_PHRASE.search(after[: cue.start()]):
        return "O", f"optional: '{cue.group()}'"
    if cue := _STRONG_LEAD.search(before):
        word = cue.group().strip()
        if word.lower() not in {"occur", "occurs"}:
            return "O", f"optional: '{word}'"
    own_phrase = after[: boundary.start()] if (boundary := _NEW_PHRASE.search(after)) else after
    if cue := _MODAL_ANY.search(before) or _MODAL_ANY.search(own_phrase):
        return "W", f"modal '{cue.group()}'"
    return "M", ""


def _connector(text: str, a: Mention, b: Mention) -> str | None:
    """'and' / 'or' when two neighbouring wordings are directly coordinated, else None."""
    between = text[a.end : b.start]
    if not between.strip() or not _CONNECTOR.match(between):
        return None
    return "or" if re.search(r"\bor\b", between, re.IGNORECASE) else "and"


def _groups(text: str, members: list[Mention]) -> list[list[tuple[Mention, str | None]]]:
    """Runs of directly coordinated wordings: [(mention, connector to the previous one)]."""
    groups: list[list[tuple[Mention, str | None]]] = []
    current: list[tuple[Mention, str | None]] = []
    for m in members:
        link = _connector(text, current[-1][0], m) if current else None
        if current and link is None:
            groups.append(current)
            current = []
        current.append((m, link))
    if current:
        groups.append(current)
    return groups


def _set(m: Mention, bcv: str, reason: str, basis: str = "cue") -> None:
    vocab = load_vocabulary()
    for item in m.items:
        if item.code and not vocab.get(item.code).is_parameter:
            item.bcv, item.bcv_reasons, item.bcv_basis = bcv, [reason] if reason else [], basis
            item.negated = bcv == "X"  # an excluded element is listed as such, apart from a stated one


def assign(text: str, mentions: list[Mention]) -> None:
    """Set `bcv`, `bcv_reasons` and `bcv_basis` on the classified items of every mention."""
    vocab = load_vocabulary()
    classed = [m for m in mentions if any(i.code and not vocab.get(i.code).is_parameter for i in m.items)]
    for clause in _clauses(text):
        members = [m for m in classed if clause[0] <= m.start < clause[1]]
        if not members:
            continue
        state = {m.id: _state(text, clause, m) for m in members}
        for group in _groups(text, members):
            _resolve_group(text, clause, group, state)

    # BCV 5 "kills all other elements of its block": only one per block can stand.
    seen: set[str] = set()
    for m in sorted(classed, key=lambda m: m.start):
        for item in m.items:
            if item.bcv == "5":
                block = (item.code or "")[:3]
                if block in seen:
                    item.bcv, item.bcv_basis = "3", "assumed"
                    item.bcv_reasons.append("only one element per block can be exclusive (5)")
                seen.add(block)


def _resolve_group(text, clause, group, state) -> None:
    mentions = [m for m, _ in group]
    names = {m.id: next((i.text or m.text for i in m.items if i.code), m.text).strip() for m in mentions}
    op = "or" if any(link == "or" for _, link in group[1:]) else "and" if len(group) > 1 else None

    # an exclusion ("without trees or shrubs") covers the whole coordinated group
    excluded = next((state[m.id] for m in mentions if state[m.id][0] == "X"), None)
    if excluded:
        for m in mentions:
            _set(m, "X", excluded[1] if state[m.id][0] == "X" else f"{excluded[1]} (same group)")
        return

    first = mentions[0]
    lead = text[max(clause[0], first.start - _LEAD_TAIL) : first.start]
    paired = bool(_PAIRED_LEAD.search(lead)) and len(group) > 1

    eligible = [m for m in mentions if state[m.id][0] in ("M", "W")]
    for m in mentions:
        role, reason = state[m.id]
        others = ", ".join(f"'{names[o.id]}'" for o in mentions if o is not m)
        if role == "E":
            _set(m, "5", reason)
        elif role == "O":
            _set(m, "1", reason)
        elif paired and m in eligible and len(eligible) > 1:
            _set(m, "4", f"paired: at least two of {others or 'the group'}")
        elif op == "or" and m in eligible and len(eligible) > 1:
            _set(m, "2", f"either-or: 'or' with {others}")
        elif role == "W":
            _set(m, "1", reason)
        elif op == "and" and len(group) > 1:
            _set(m, "3", f"cumulative: 'and' with {others}")
        else:
            _set(m, "3", "no optional cue: taken as defining", basis="assumed")


def combine(entries_bcv: list[str]) -> str | None:
    """The strongest requirement among several mentions of the same element."""
    return max(entries_bcv, key=lambda b: STRENGTH.get(b, 0), default=None)
