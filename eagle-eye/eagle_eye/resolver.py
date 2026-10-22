"""Pick concrete EAGLE classes for the spans the extractor found.

The extractor knows *that* a span is land cover, land use or a characteristic and
offers candidate elements. The resolver decides *which* element, using

* the EAGLE element definitions (label, definition text, "Includes" examples),
  compared with the span and its sentence by TF-IDF cosine similarity;
* the whole text: the thematic domains (AGRI, FRST, ...) and the families of the
  other elements found make some candidates more plausible than others;
* the EAGLE hierarchy: headings cannot describe a land unit, so a heading is
  replaced by its "applied / present, unspecified" element, and a more specific
  child is taken only when the text names what sets it apart (the bar coding
  manual's rule: only explicit wording counts);
* the "Excludes" notes of the definitions, which veto an element.

Every decision carries human readable reasons for the class pane.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache

from .extractor import Item, Mention, Ranked
from .lexicon import GENERIC_WORDS, PARTICIPLE, RULES
from .textnorm import Token, lemma, lemmas, tokenize
from .vocabulary import Vocabulary, load_vocabulary

DOMAIN_NAMES = {
    "AGRI": "agriculture",
    "FRST": "forestry",
    "HABT": "habitats and ecosystems",
    "URBN": "urban / built-up areas",
    "MINE": "mining",
    "TRNS": "transportation",
    "INDU": "industry",
    "ENRG": "energy",
}

_STOPWORDS = """
a an and are as at be been being by can could for from has have if in into is it its may
of on or that the their there these this those to was were which while with within would
also often besides other such than then not no only any all each both more most some where when
"""
STOP = frozenset(_STOPWORDS.split()) | frozenset(lemma(w) for w in _STOPWORDS.split())
GENERIC = frozenset(lemma(w) for w in GENERIC_WORDS)

HIGH, MEDIUM = 0.70, 0.50
RETRIEVAL_TOP = 3
RETRIEVAL_MIN_COSINE = 0.25

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(\[])|\n+")


def content_lemmas(text: str) -> list[str]:
    return [t.lemma for t in tokenize(text) if t.lemma not in STOP and len(t.lemma) > 2 and not t.text.isdigit()]


class DefinitionIndex:
    """TF-IDF vectors over label (weighted x3), definition and "Includes" examples."""

    def __init__(self, vocab: Vocabulary):
        docs = {
            c.code: Counter(
                content_lemmas(c.label) * 3
                + content_lemmas(c.definition)
                + [t for example in c.includes for t in content_lemmas(example)]
            )
            for c in vocab.concepts
        }
        self.definition_lemmas = {
            c.code: tuple(lemmas(c.definition)) + tuple(t for example in c.includes for t in ("|",) + lemmas(example))
            for c in vocab.concepts
        }
        df = Counter(t for doc in docs.values() for t in doc)
        n = len(docs)
        self.idf = {t: math.log((n + 1) / (df[t] + 1)) + 1 for t in df}
        self.vectors = {code: self._normalise({t: (1 + math.log(f)) * self.idf[t] for t, f in doc.items()}) for code, doc in docs.items()}
        self.inverted: dict[str, list[tuple[str, float]]] = {}
        for code, vec in self.vectors.items():
            for t, w in vec.items():
                self.inverted.setdefault(t, []).append((code, w))

    @staticmethod
    def _normalise(vec: dict[str, float]) -> dict[str, float]:
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        return {t: w / norm for t, w in vec.items()}

    def query(self, weighted: Counter) -> dict[str, float]:
        return self._normalise({t: (1 + math.log(f)) * self.idf[t] for t, f in weighted.items() if t in self.idf})

    def definition_names(self, code: str, phrase: tuple[str, ...]) -> bool:
        """Does the definition (or its examples) contain the phrase word for word?"""
        text = self.definition_lemmas[code]
        return any(text[i : i + len(phrase)] == phrase for i in range(len(text) - len(phrase) + 1))

    def similarities(self, query: dict[str, float]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for t, qw in query.items():
            for code, dw in self.inverted.get(t, ()):
                scores[code] = scores.get(code, 0.0) + qw * dw
        return scores


@cache
def _index(vocab: Vocabulary) -> DefinitionIndex:
    return DefinitionIndex(vocab)


@dataclass
class _Context:
    text: str
    tokens: list[Token]
    sentences: list[tuple[int, int]]

    @classmethod
    def build(cls, text: str) -> "_Context":
        spans, start = [], 0
        for m in _SENTENCE_BREAK.finditer(text):
            spans.append((start, m.start()))
            start = m.end()
        spans.append((start, len(text)))
        return cls(text, tokenize(text), [s for s in spans if s[1] > s[0]])

    def sentence(self, pos: int) -> tuple[int, int]:
        return next((s for s in self.sentences if s[0] <= pos < s[1] or pos == s[1]), (0, len(self.text)))

    def sentence_text(self, m: Mention) -> str:
        a, b = self.sentence(m.start)
        return self.text[a:b]

    def neighbourhood(self, start: int, end: int, radius: int = 4) -> set[str]:
        """Lemmas of the span plus `radius` tokens on each side, inside the sentence."""
        a, b = self.sentence(start)
        inside = [t for t in self.tokens if a <= t.start and t.end <= b]
        idx = [i for i, t in enumerate(inside) if t.end > start and t.start < end]
        if not idx:
            return set()
        lo, hi = max(0, idx[0] - radius), min(len(inside), idx[-1] + radius + 1)
        return {t.lemma for t in inside[lo:hi]}


def _confidence(score: float) -> str:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


class Resolver:
    def __init__(self, vocab: Vocabulary | None = None):
        self.vocab = vocab or load_vocabulary()
        self.index = _index(self.vocab)

    # ------------------------------------------------------------------ public

    def resolve(self, text: str, mentions: list[Mention]) -> None:
        ctx = _Context.build(text)
        anchors = {m.evidence[0][0] for m in mentions if m.evidence and m.evidence[0][1] >= 0.9}
        domains = Counter(d for code in anchors for d in self.vocab.get(code).domains)
        family = set(anchors)
        for code in anchors:
            family.update(c.code for c in self.vocab.path(code))
            family.update(c.code for c in self.vocab.children(self.vocab.get(code).parent or "") if self.vocab.get(code).parent)

        for m in mentions:
            ranked = self._rank(m, ctx, domains, family)
            if m.negated:
                m.items = self._negated_items(m, ctx, domains, family) or self._best_item(m, ranked, ctx)
            else:
                m.items = self._best_item(m, ranked, ctx)
            shown = {i.code for i in m.items}
            m.alternatives = [r for r in ranked if r.code not in shown and not self.vocab.get(r.code).is_heading][:3]

        self._attach(mentions, ctx)

    # ------------------------------------------------------------------ ranking

    def _query(self, m: Mention, ctx: _Context, surface: str | None = None) -> dict[str, float]:
        weighted: Counter = Counter()
        for t in content_lemmas(surface or m.text):
            weighted[t] += 4
        for t in content_lemmas(ctx.sentence_text(m)):
            weighted[t] += 1
        return self.index.query(weighted)

    def _score(self, code: str, strength: float, source: str, query: dict, surface: str,
               domains: Counter, family: set[str]) -> tuple[float, list[str]]:
        concept = self.vocab.get(code)
        reasons = []
        if source == "label":
            reasons.append(f"matches the EAGLE label '{concept.label}'")
        elif source == "label-part":
            reasons.append(f"matches part of the EAGLE label '{concept.label}'")
        elif source == "retrieval":
            reasons.append("suggested only because its definition resembles the text")
        elif source == "definition":
            reasons.append(f"its definition names '{surface}'")
        else:
            reasons.append(f"the wording '{surface}' is a known term for '{concept.label}'")

        cosine = self.index.similarities(query).get(code, 0.0)
        sim = min(1.0, 2.5 * cosine)
        if sim >= 0.35 and source not in ("retrieval", "definition"):
            reasons.append(f"its definition fits the sentence ({round(sim * 100)}%)")

        if domains and concept.domains:
            overlap = [d for d in concept.domains if d in domains]
            dom = 1.0 if overlap else 0.0
            if overlap:
                reasons.append("fits the text's " + " / ".join(DOMAIN_NAMES.get(d, d) for d in overlap[:2]) + " context")
        else:
            dom = 0.5

        coherent = code in family
        if coherent and strength < 1.0:
            reasons.append("related to other elements found in the text")

        score = 0.7 * strength + 0.12 * sim + 0.08 * dom + 0.10 * (1.0 if coherent else 0.0)

        phrase = lemmas(surface)
        excluded = lemmas(concept.excludes)
        if phrase and concept.excludes and any(excluded[i : i + len(phrase)] == phrase for i in range(len(excluded))):
            score -= 0.3
            reasons.append(f"excluded by its definition ({concept.excludes.strip('. ')})")
        return max(score, 0.0), reasons

    def _rank(self, m: Mention, ctx: _Context, domains: Counter, family: set[str]) -> list[Ranked]:
        query = self._query(m, ctx)
        sources = {code: (strength, src) for code, strength, src in m.evidence}
        phrase = tuple(t for t in lemmas(m.text) if t not in STOP)
        named = 0
        for code, cosine in sorted(self.index.similarities(query).items(), key=lambda kv: -kv[1]):
            concept = self.vocab.get(code)
            if concept.block != m.block or code in sources or concept.is_heading:
                continue
            if phrase and not all(t in GENERIC for t in phrase) and named < RETRIEVAL_TOP and self.index.definition_names(code, phrase):
                sources[code] = (0.5, "definition")
                named += 1
            elif cosine >= RETRIEVAL_MIN_COSINE and sum(s[1] == "retrieval" for s in sources.values()) < RETRIEVAL_TOP:
                sources[code] = (0.0, "retrieval")
        ranked = [Ranked(code, *self._score(code, strength, src, query, m.text, domains, family))
                  for code, (strength, src) in sources.items()]
        return sorted(ranked, key=lambda r: -r.score)

    # ------------------------------------------------------------------ choosing

    def _best_item(self, m: Mention, ranked: list[Ranked], ctx: _Context) -> list[Item]:
        if not ranked:
            return [Item(None, 0.0, "none", ["type recognised, but no EAGLE element matches the wording"])]
        top = ranked[0]
        code, reasons = self._refine(top.code, m.start, m.end, ctx)
        confidence = "low" if self.vocab.get(code).is_heading else _confidence(top.score)
        return [Item(code, top.score, confidence, top.reasons + reasons)]

    def _negated_items(self, m: Mention, ctx: _Context, domains: Counter, family: set[str]) -> list[Item]:
        """Split "(not drained, irrigated, sown)" into one excluded element per activity."""
        items, seen = [], set()
        for part in re.finditer(PARTICIPLE, m.text, re.IGNORECASE):
            surface = part.group()
            code = self._code_for_wording(surface)
            if code is None:
                continue
            start = m.start + part.start()
            absent = self._absent_element(code) if re.match(r"\(?\s*non", m.text, re.IGNORECASE) else None
            if absent is not None:
                label = self.vocab.get(absent).label
                items.append(Item(absent, 0.85, "high", [f"'non-{surface}' corresponds to the element '{label}'"], text=surface))
                seen.add(absent)
                continue
            refined, reasons = self._refine(code, start, start + len(surface), ctx)
            if refined in seen:
                continue
            seen.add(refined)
            score, why = self._score(code, 0.9, "negated management", self._query(m, ctx, surface), surface, domains, family)
            items.append(
                Item(refined, score, _confidence(score), [f"'{surface}' is negated in '{m.text.strip('() ')}'"] + why[1:] + reasons,
                     negated=True, text=surface)
            )
        return items

    def _absent_element(self, code: str) -> str | None:
        """The "No <activity>" element below a heading, if EAGLE has one."""
        for child in self.vocab.descendants(code):
            if child.label.lower().startswith("no ") and not child.is_heading:
                return child.code
        return None

    def _code_for_wording(self, surface: str) -> str | None:
        for rule in RULES:
            if rule.block == "LCH" and not rule.negated and rule.codes and rule.pattern.search(surface):
                return rule.codes[0]
        return None

    # ------------------------------------------------------------------ hierarchy

    def _refine(self, code: str, start: int, end: int, ctx: _Context) -> tuple[str, list[str]]:
        """Walk down the EAGLE hierarchy as far as the text justifies."""
        concept = self.vocab.get(code)
        window = ctx.neighbourhood(start, end)
        parent_tokens = {t for c in self.vocab.path(code) for t in lemmas(c.label)}

        best, best_cover = None, 0.0
        for child in self.vocab.descendants(code):
            if child.label.lower().startswith(("no ", "other")) or child.is_heading:
                continue
            distinguishing = [t for t in lemmas(child.label) if t not in parent_tokens and t not in GENERIC and t not in STOP]
            if not distinguishing:
                continue
            hit = [t for t in distinguishing if t in window]
            cover = len(hit) / len(distinguishing)
            if hit and cover >= 0.5 and (cover, -child.level) > (best_cover, -(best.level if best else 99)):
                best, best_cover = child, cover
        if best is not None:
            return best.code, [f"the text names what sets '{best.label}' apart"]

        if concept.is_heading:
            for child in self.vocab.descendants(code):
                label = child.label.lower()
                if re.search(r"\b(applied|present)\b", label) and not label.startswith("no ") and not child.is_heading:
                    return child.code, [f"'{concept.label}' is a heading; no detail given, so the 'unspecified' element '{child.label}' is used"]
            return code, [f"'{concept.label}' is a module heading, not directly selectable in bar coding"]
        return code, []

    # ------------------------------------------------------------------ patterns and parameters

    def _attach(self, mentions: list[Mention], ctx: _Context) -> None:
        """Link patterns and parameters to the land cover they describe."""
        covers = [m for m in mentions if m.block == "LCC"]
        for m in mentions:
            if m.block != "LCH" or not m.items or not m.items[0].code:
                continue
            code = m.items[0].code
            if not (code.startswith(("LCH-3_", "LCH-8_", "LCH-9_")) or self.vocab.get(code).is_parameter):
                continue
            a, b = ctx.sentence(m.start)
            near = [c for c in covers if a <= c.start < b]
            if not near:
                continue
            gap = lambda c: (c.start - m.end) if c.start >= m.end else (m.start - c.end)
            if code.startswith("LCH-8_1"):  # "scattered trees", "patches of vegetation": the pattern comes first
                near = [c for c in near if c.start >= m.end] or near
            target = min(near, key=lambda c: (gap(c), c.start < m.start))
            m.applies_to = target.id
            target_code = target.concept or ""
            if m.note.startswith("percentage") and target_code.startswith("LCC-2_1"):
                m.items[0].code = "LCH-3_13"
                m.items[0].reasons.append("a share applying to trees / shrubs is the crown cover density")
