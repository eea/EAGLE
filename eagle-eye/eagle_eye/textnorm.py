"""Tokenising and stemming shared by vocabulary and text matching.

Everything is compared case-insensitively on stems, so "Grasslands", "grassland" and
"GRASSLAND" are one token, and "irrigated" / "irrigation", "fertilised" / "fertilization"
meet. `lemma` is kept as the name of the normal form used throughout.
"""

import re
from functools import lru_cache
from typing import NamedTuple

import snowballstemmer

# Hyphens and punctuation separate tokens, so "Grass-Like" and "grass like" match alike.
_WORD = re.compile(r"[^\W_]+")

_STEMMER = snowballstemmer.stemmer("english")
_IRREGULAR = {"leaves": "leaf", "mown": "mow", "lichens": "lichen", "algae": "algae", "analyses": "analysis"}
_BRITISH = re.compile(r"is(e|ed|es|ing|ation|ations|er|ers)$")
_NOT_BRITISH = frozenset("otherwise promise promised promises exercise exercised exercises comprise comprised surprise advise".split())
# "grassland", "woodland": the first part is what the EAGLE labels and definitions talk about
_COMPOUND = re.compile(r"^(\w{4,})lands?$")


class Token(NamedTuple):
    text: str
    lemma: str
    start: int
    end: int


@lru_cache(maxsize=50_000)
def lemma(word: str) -> str:
    """Case-insensitive stem: plural and verb endings, "-ise" / "-ize" spellings."""
    w = word.lower()
    if w in _IRREGULAR:
        return _IRREGULAR[w]
    if len(w) > 6 and w not in _NOT_BRITISH:
        w = _BRITISH.sub(lambda m: "iz" + m.group(1), w)
    return _STEMMER.stemWord(w)


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(), lemma(m.group()), m.start(), m.end()) for m in _WORD.finditer(text)]


def lemmas(phrase: str) -> tuple[str, ...]:
    return tuple(t.lemma for t in tokenize(phrase))


def compound_heads(word: str) -> list[str]:
    """Stems of the parts a compound is made of ("grassland" -> "grass"), for similarity matching."""
    m = _COMPOUND.match(word.lower())
    return [lemma(m.group(1))] if m else []
