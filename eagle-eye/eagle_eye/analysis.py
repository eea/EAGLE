"""Text in, annotated EAGLE analysis out: extraction, resolution, class pane entries."""

from collections import Counter

from .extractor import Analysis, Entry, Mention, extract
from .resolver import DOMAIN_NAMES, Resolver
from .vocabulary import BLOCKS, Vocabulary, load_vocabulary

DEFINITION_LIMIT = 420


def _definition(vocab: Vocabulary, code: str) -> str:
    concept = vocab.get(code)
    text = concept.definition
    if len(text) > DEFINITION_LIMIT:
        text = text[:DEFINITION_LIMIT].rsplit(" ", 1)[0] + " …"
    if concept.includes:
        text += f" Includes: {', '.join(concept.includes)}."
    if concept.excludes:
        text += f" Excludes: {concept.excludes}"
    return text.strip()


def _entries(mentions: list[Mention], vocab: Vocabulary) -> list[Entry]:
    entries: dict[str, Entry] = {}
    by_id = {m.id: m for m in mentions}
    for m in mentions:
        for item in m.items:
            if item.code:
                concept = vocab.get(item.code)
                key = item.code + ("|excluded" if item.negated else "")
                label, breadcrumb, definition = concept.label, vocab.breadcrumb(item.code), _definition(vocab, item.code)
            else:
                key = f"{m.block}:{m.text.lower()}"
                label, breadcrumb, definition = m.text.strip().capitalize(), m.note, ""
            entry = entries.get(key)
            if entry is None:
                entry = entries[key] = Entry(
                    key, vocab.get(item.code).block if item.code else m.block, label, item.code, breadcrumb,
                    negated=item.negated, confidence=item.confidence, score=item.score,
                    reasons=item.reasons, definition=definition,
                    alternatives=[
                        {"code": a.code, "label": vocab.get(a.code).label, "score": round(a.score, 2)}
                        for a in m.alternatives
                    ],
                )
            if m.id not in entry.mention_ids:
                entry.mention_ids.append(m.id)
            if item.score > entry.score:
                entry.score, entry.confidence, entry.reasons = item.score, item.confidence, item.reasons
            if m.applies_to is not None and not entry.applies_to:
                target = by_id[m.applies_to]
                entry.applies_to = vocab.get(target.concept).label if target.concept else target.text
    return sorted(entries.values(), key=lambda e: (BLOCKS.index(e.block), e.mention_ids[0]))


def _summary(entries: list[Entry], vocab: Vocabulary) -> dict:
    # An element tagged with a single domain is a stronger hint than one tagged with several.
    weight: Counter = Counter()
    for e in entries:
        if e.code and e.confidence in ("high", "medium"):
            domains = vocab.get(e.code).domains
            for d in domains:
                weight[d] += 1 / len(domains)
    top = max(weight.values(), default=0)
    shown = [d for d, w in weight.most_common(3) if w >= 1.5 and w >= 0.25 * top]
    return {
        "domains": [DOMAIN_NAMES.get(d, d) for d in shown],
        "confidence": dict(Counter(e.confidence for e in entries)),
    }


def analyze(text: str, vocab: Vocabulary | None = None) -> Analysis:
    vocab = vocab or load_vocabulary()
    mentions = extract(text, vocab)
    Resolver(vocab).resolve(text, mentions)
    entries = _entries(mentions, vocab)
    return Analysis(text, mentions, entries, _summary(entries, vocab))
