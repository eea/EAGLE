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
class Mention:
    id: int
    start: int
    end: int
    text: str
    block: str  # LCC | LUA | LCH
    concept: str | None  # best-guess EAGLE element code, if specific enough
    candidates: list[str]
    source: str  # rule id, "label" or "label-part"
    negated: bool = False
    note: str = ""


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


@dataclass
class Analysis:
    text: str
    mentions: list[Mention]
    entries: list[Entry]

    def to_payload(self) -> dict:
        entry_of = {m_id: e.key for e in self.entries for m_id in e.mention_ids}
        return {
            "text": self.text,
            "mentions": [
                {
                    "id": m.id,
                    "start": m.start,
                    "end": m.end,
                    "block": m.block,
                    "entry": entry_of[m.id],
                    "negated": m.negated,
                    "tip": f"{m.block}" + (f" · {m.concept}" if m.concept else "") + (f" · {m.note}" if m.note else ""),
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
            found.append(_Candidate(start, end, rule.block, rule.codes, rule.score, rule.id, rule.negated, rule.note))
    return found


def _resolve(candidates: list[_Candidate], vocab: Vocabulary) -> list[tuple[_Candidate, list[str]]]:
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
        codes = list(dict.fromkeys(code for c in group if c.block == best.block for code in c.codes))
        chosen.append((best, codes))
    return sorted(chosen, key=lambda pair: pair[0].start)


def extract(text: str, vocab: Vocabulary | None = None) -> list[Mention]:
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
            concept=codes[0] if codes else None,
            candidates=codes,
            source=best.source,
            negated=best.negated,
            note=best.note,
        )
        for i, (best, codes) in enumerate(_resolve(pool, vocab))
    ]


def _entries(mentions: list[Mention], vocab: Vocabulary) -> list[Entry]:
    entries: dict[str, Entry] = {}
    for m in mentions:
        if m.concept:
            concept = vocab.get(m.concept)
            key, label, breadcrumb = m.concept, concept.label, vocab.breadcrumb(m.concept)
        else:
            surface = " ".join(lemmas(m.text))
            key, label, breadcrumb = f"{m.block}:{surface}", m.text.strip().capitalize(), m.note
        entry = entries.setdefault(key, Entry(key, m.block, label, m.concept, breadcrumb))
        entry.mention_ids.append(m.id)
        entry.negated = entry.negated or m.negated
    return sorted(entries.values(), key=lambda e: (BLOCKS.index(e.block), e.mention_ids[0]))


def analyze(text: str, vocab: Vocabulary | None = None) -> Analysis:
    vocab = vocab or load_vocabulary()
    mentions = extract(text, vocab)
    return Analysis(text, mentions, _entries(mentions, vocab))
