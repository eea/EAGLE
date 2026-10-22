"""Tokenising and light-weight lemmatising shared by vocabulary and text matching."""

import re
from typing import NamedTuple

# Hyphens and punctuation separate tokens, so "Grass-Like" and "grass like" match alike.
_WORD = re.compile(r"[^\W_]+")

_IRREGULAR = {"leaves": "leaf", "lichens": "lichen", "algae": "algae", "analyses": "analysis"}


class Token(NamedTuple):
    text: str
    lemma: str
    start: int
    end: int


def lemma(word: str) -> str:
    """Strip plural endings; good enough for matching land cover vocabulary."""
    w = word.lower()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) <= 3 or w.endswith(("ss", "us", "is")):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("sses", "ches", "shes", "xes", "zes")):
        return w[:-2]
    if w.endswith("s"):
        return w[:-1]
    return w


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(), lemma(m.group()), m.start(), m.end()) for m in _WORD.finditer(text)]


def lemmas(phrase: str) -> tuple[str, ...]:
    return tuple(t.lemma for t in tokenize(phrase))
