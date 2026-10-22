"""Find EAGLE land cover (LCC), land use (LUA) and land characteristics (LCH) in free text.

Two evidence sources feed one candidate pool:

* curated rules (eagle_eye.lexicon): everyday wording and patterns such as
  negated management lists and percentage ranges;
* the EAGLE matrix labels themselves (eagle_eye.vocabulary), matched on
  lemmatised tokens, longest phrase first.

Overlapping candidates are resolved by span length, then by evidence score. Each
surviving span becomes a Mention that keeps its ranked candidate elements, so a
later iteration can pick the concrete class using the whole text as context.
"""

import re
from dataclasses import dataclass, field
from functools import cache

from .lexicon import GENERIC_WORDS, MODIFIERS, RULES
from .textnorm import Token, lemma, lemmas, tokenize
from .vocabulary import BLOCKS, Vocabulary, load_vocabulary

LABEL_SCORE = 1.5
LABEL_PART_SCORE = 1.0
_BREAK = re.compile(r"[.;:!?\n]")


@dataclass
class Ranked:
    """A possible EAGLE element for a mention, with the reasons behind its score."""

    code: str
    score: float  # 0..1
    reasons: list[str] = field(default_factory=list)


@dataclass
class Item:
    """One concrete EAGLE class a mention stands for.

    Usually a mention has one; a negated management list such as
    "(not drained, irrigated)" stands for several, each one excluded.
    """

    code: str | None
    score: float
    confidence: str  # high | medium | low | none | manual
    reasons: list[str] = field(default_factory=list)
    negated: bool = False
    text: str | None = None  # the part of the span this item stems from
    origin: str = "automatic"  # automatic | changed (class picked by the user) | added (manual highlight)
    bcv: str | None = None  # bar code value suggested from the text: X, 1, 2, 3, 4, 5
    bcv_reasons: list[str] = field(default_factory=list)
    bcv_basis: str = "cue"  # cue (explicit wording) | assumed (no cue) | manual


@dataclass
class Mention:
    id: int
    start: int
    end: int
    text: str
    block: str  # LCC | LUA | LCH
    evidence: list[tuple[str, float, str]]  # (code, strength 0..1, source) from the matching step
    source: str  # rule id, "label" or "label-part"
    negated: bool = False
    note: str = ""
    items: list[Item] = field(default_factory=list)  # set by the resolver
    alternatives: list[Ranked] = field(default_factory=list)
    applies_to: int | None = None  # id of the LCC mention a pattern / parameter describes

    @property
    def concept(self) -> str | None:
        return self.items[0].code if self.items else None


@dataclass
class Entry:
    """One line in the class pane: a distinct concept (or surface term) of a block."""

    key: str
    block: str
    label: str
    code: str | None
    breadcrumb: str
    mention_ids: list[int] = field(default_factory=list)
    negated: bool = False
    confidence: str = "none"
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    alternatives: list[dict] = field(default_factory=list)
    definition: str = ""
    applies_to: str = ""
    bcv: str | None = None
    bcv_reasons: list[str] = field(default_factory=list)
    bcv_basis: str = "cue"


@dataclass
class Analysis:
    text: str
    mentions: list[Mention]
    entries: list[Entry]
    summary: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        entries_of: dict[int, list[str]] = {}
        for e in self.entries:
            for m_id in e.mention_ids:
                entries_of.setdefault(m_id, []).append(e.key)
        return {
            "text": self.text,
            "summary": self.summary,
            "mentions": [
                {
                    "id": m.id,
                    "start": m.start,
                    "end": m.end,
                    "block": m.block,
                    "entries": entries_of.get(m.id, []),
                    "negated": any(i.negated for i in m.items),
                    "manual": any(i.origin != "automatic" for i in m.items),
                    "tip": " · ".join(
                        part
                        for part in (
                            m.block,
                            ", ".join(i.code for i in m.items if i.code),
                            "BCV " + "/".join(dict.fromkeys(i.bcv for i in m.items if i.bcv)) if any(i.bcv for i in m.items) else "",
                            m.note,
                        )
                        if part
                    ),
                }
                for m in self.mentions
            ],
            "entries": [
                {
                    "key": e.key,
                    "block": e.block,
                    "label": e.label,
                    "code": e.code,
                    "breadcrumb": e.breadcrumb,
                    "mentions": e.mention_ids,
                    "negated": e.negated,
                    "confidence": e.confidence,
                    "reasons": e.reasons,
                    "alternatives": e.alternatives,
                    "definition": e.definition,
                    "appliesTo": e.applies_to,
                    "bcv": e.bcv,
                    "bcvReasons": e.bcv_reasons,
                    "bcvBasis": e.bcv_basis,
                }
                for e in self.entries
            ],
        }


@dataclass
class _Candidate:
    start: int
    end: int
    block: str
    codes: tuple[str, ...]
    score: float
    source: str
    negated: bool = False
    note: str = ""
    strength: float = 0.9


_GENERIC_LEMMAS = frozenset(lemma(w) for w in GENERIC_WORDS)


@cache
def _phrase_index(vocab: Vocabulary) -> dict[str, list[tuple[tuple[str, ...], str, bool]]]:
    index: dict[str, list[tuple[tuple[str, ...], str, bool]]] = {}
    for concept in vocab.concepts:
        if concept.level == 0:
            continue
        seen = set()
        for surface, full in vocab.label_variants(concept):
            key = lemmas(surface)
            if not key or key in seen or all(t in _GENERIC_LEMMAS for t in key):
                continue
            if len(key) == 1 and len(key[0]) < 4:
                continue
            seen.add(key)
            index.setdefault(key[0], []).append((key, concept.code, full))
    return index


def _label_candidates(text: str, tokens: list[Token], vocab: Vocabulary) -> list[_Candidate]:
    index = _phrase_index(vocab)
    found = []
    for i, tok in enumerate(tokens):
        for key, code, full in index.get(tok.lemma, ()):
            window = tokens[i : i + len(key)]
            if len(window) < len(key) or tuple(t.lemma for t in window) != key:
                continue
            if any(_BREAK.search(text[a.end : b.start]) for a, b in zip(window, window[1:])):
                continue
            found.append(
                _Candidate(
                    window[0].start,
                    window[-1].end,
                    vocab.get(code).block,
                    (code,),
                    LABEL_SCORE if full else LABEL_PART_SCORE,
                    "label" if full else "label-part",
                )
            )
    return found


def _absorb_modifiers(text: str, tokens: list[Token], start: int) -> int:
    """Move `start` left over qualifying words such as "maintenance" in "maintenance mowing"."""
    pos = next((i for i, t in enumerate(tokens) if t.start == start), None)
    while pos:
        prev = tokens[pos - 1]
        if prev.text.lower() not in MODIFIERS or re.search(r"[^\s-]", text[prev.end : tokens[pos].start]):
            break
        start, pos = prev.start, pos - 1
    return start


def _rule_candidates(text: str, tokens: list[Token]) -> list[_Candidate]:
    found = []
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            start, end = m.span()
            if rule.absorb_modifiers:
                start = _absorb_modifiers(text, tokens, start)
            if rule.wrap_parens and text[start - 1 : start] == "(" and text[end : end + 1] == ")":
                start, end = start - 1, end + 1
            found.append(_Candidate(start, end, rule.block, rule.codes, rule.score, rule.id, rule.negated, rule.note, rule.strength))
    return found


EVIDENCE_STRENGTH = {"label": 1.0, "label-part": 0.75}


def _evidence(group: list[_Candidate], block: str) -> list[tuple[str, float, str]]:
    """Per element evidence of one span: rule hits (first code strongest) and label hits."""
    best: dict[str, tuple[float, str]] = {}
    for c in group:
        if c.block != block:
            continue
        for i, code in enumerate(c.codes):
            strength = EVIDENCE_STRENGTH.get(c.source, c.strength if i == 0 else c.strength * 0.65)
            if code not in best or strength > best[code][0]:
                best[code] = (strength, c.source)
    return sorted(((code, s, src) for code, (s, src) in best.items()), key=lambda e: -e[1])


def _resolve(candidates: list[_Candidate], vocab: Vocabulary) -> list[tuple[_Candidate, list[tuple[str, float, str]]]]:
    """Pick non-overlapping spans: longest first, then strongest evidence."""
    by_span: dict[tuple[int, int], list[_Candidate]] = {}
    for c in candidates:
        by_span.setdefault((c.start, c.end), []).append(c)

    def rank(c: _Candidate) -> tuple:
        level = vocab.get(c.codes[0]).level if c.codes else 0
        return (-c.score, BLOCKS.index(c.block), level)

    spans = sorted(by_span.items(), key=lambda kv: (-(kv[0][1] - kv[0][0]), rank(min(kv[1], key=rank))))
    taken: list[tuple[int, int]] = []
    chosen = []
    for (start, end), group in spans:
        if any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        group.sort(key=rank)
        best = group[0]
        chosen.append((best, _evidence(group, best.block)))
    return sorted(chosen, key=lambda pair: pair[0].start)


def extract(text: str, vocab: Vocabulary | None = None) -> list[Mention]:
    """Find the spans; the resolver (eagle_eye.resolver) then picks concrete classes."""
    vocab = vocab or load_vocabulary()
    tokens = tokenize(text)
    pool = _rule_candidates(text, tokens) + _label_candidates(text, tokens, vocab)
    return [
        Mention(
            id=i,
            start=best.start,
            end=best.end,
            text=text[best.start : best.end],
            block=best.block,
            evidence=evidence,
            source=best.source,
            negated=best.negated,
            note=best.note,
        )
        for i, (best, evidence) in enumerate(_resolve(pool, vocab))
    ]
