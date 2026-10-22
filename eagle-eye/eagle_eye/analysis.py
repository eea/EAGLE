"""Text in, annotated EAGLE analysis out: extraction, resolution, class pane entries."""

from collections import Counter

from . import barcode
from .extractor import Analysis, Entry, Item, Mention, extract
from .overrides import Override
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
            if item.bcv and barcode.combine([item.bcv, entry.bcv or ""]) == item.bcv and (
                entry.bcv is None or barcode.STRENGTH.get(item.bcv, 0) > barcode.STRENGTH.get(entry.bcv, 0) or item.bcv_basis == "manual"
            ):
                entry.bcv, entry.bcv_reasons, entry.bcv_basis = item.bcv, item.bcv_reasons, item.bcv_basis
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


def _apply_overrides(text: str, mentions: list[Mention], overrides: list[Override], vocab: Vocabulary) -> list[Mention]:
    """Apply the user's corrections: drop, re-class, then add manual highlights."""
    removed = {(o.start, o.end) for o in overrides if o.action == "remove"}
    result = [m for m in mentions if (m.start, m.end) not in removed]

    for ov in (o for o in overrides if o.action == "replace"):
        target = next((m for m in result if (m.start, m.end) == (ov.start, ov.end)), None)
        if target is None or not ov.code or ov.code not in vocab:
            continue
        if not target.items:
            target.items = [Item(None, 0.0, "none")]
        index = min(ov.index, len(target.items) - 1)
        old = target.items[index]
        was = vocab.get(old.code).label if old.code else "no class"
        target.items[index] = Item(
            ov.code, 1.0, "manual", [f"chosen manually (automatic match: {was})"],
            negated=old.negated, text=old.text, origin="changed",
        )
        if len(target.items) == 1:
            target.block = vocab.get(ov.code).block

    for ov in (o for o in overrides if o.action == "add"):
        if not ov.code or ov.code not in vocab or not text[ov.start : ov.end].strip():
            continue
        result = [m for m in result if m.end <= ov.start or m.start >= ov.end]
        concept = vocab.get(ov.code)
        result.append(
            Mention(
                id=-1, start=ov.start, end=ov.end, text=text[ov.start : ov.end], block=concept.block,
                evidence=[], source="manual",
                items=[Item(ov.code, 1.0, "manual", ["added manually"], origin="added")],
            )
        )

    result.sort(key=lambda m: m.start)
    new_id = {m.id: i for i, m in enumerate(result) if m.id >= 0}
    for i, m in enumerate(result):
        m.applies_to = new_id.get(m.applies_to) if m.applies_to is not None else None
        m.id = i
    return result


def _apply_bcv(mentions: list[Mention], ov: Override) -> None:
    target = next((m for m in mentions if (m.start, m.end) == (ov.start, ov.end)), None)
    if target is None or ov.index >= len(target.items) or not target.items[ov.index].code:
        return
    item = target.items[ov.index]
    item.bcv, item.bcv_basis, item.bcv_reasons = ov.code, "manual", ["set manually"]
    item.negated = ov.code == "X"


def analyze(text: str, vocab: Vocabulary | None = None, overrides: list[Override] | None = None) -> Analysis:
    vocab = vocab or load_vocabulary()
    mentions = extract(text, vocab)
    Resolver(vocab).resolve(text, mentions)
    if overrides:
        mentions = _apply_overrides(text, mentions, overrides, vocab)
    barcode.assign(text, mentions)
    for ov in (o for o in overrides or () if o.action == "bcv"):
        _apply_bcv(mentions, ov)
    entries = _entries(mentions, vocab)
    return Analysis(text, mentions, entries, _summary(entries, vocab))
