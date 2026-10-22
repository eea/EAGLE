"""The EAGLE matrix (v3.2) as a searchable vocabulary of LCC / LUA / LCH elements."""

import json
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "eagle_vocabulary.json"

BLOCKS = ("LCC", "LUA", "LCH")

BLOCK_NAMES = {
    "LCC": "Land Cover Components",
    "LUA": "Land Use Attributes",
    "LCH": "Land Characteristics",
}


@dataclass(frozen=True)
class Concept:
    code: str
    uri: str
    label: str
    level: int
    block: str
    parent: str | None
    element_type: str | None  # Heading / Character / Parameter (LCH only)
    relevance: str | None  # LC / LU / Gen

    @property
    def is_heading(self) -> bool:
        return self.element_type == "Heading"


class Vocabulary:
    def __init__(self, concepts: list[Concept]):
        self.concepts = concepts
        self._by_code = {c.code: c for c in concepts}

    def __contains__(self, code: str) -> bool:
        return code in self._by_code

    def get(self, code: str) -> Concept:
        return self._by_code[code]

    def path(self, code: str) -> list[Concept]:
        """Concepts from the block root down to `code`."""
        chain = []
        node: Concept | None = self._by_code.get(code)
        while node is not None:
            chain.append(node)
            node = self._by_code.get(node.parent) if node.parent else None
        return chain[::-1]

    def breadcrumb(self, code: str) -> str:
        return " › ".join(c.label for c in self.path(code)[1:])

    def label_variants(self, concept: Concept) -> list[tuple[str, bool]]:
        """Surface forms of a label as (text, is_full_label) pairs.

        Compound labels such as "Bushes, Shrubs" also yield their parts, so a
        text saying "shrubs" can reach the concept. Headings are structural
        (they "can't be chosen to characterize a land unit"), so only their
        complete label counts.
        """
        label = concept.label
        variants = [(label, True)]
        no_paren = re.sub(r"\s*\([^)]*\)", "", label).strip()
        if no_paren != label and no_paren:
            variants.append((no_paren, True))
        if concept.is_heading or concept.level == 0:
            return variants
        for part in re.split(r",|\band\b|\bor\b", no_paren):
            part = part.strip()
            if part and part.lower() != no_paren.lower() and not part.lower().startswith(("other", "unspecified")):
                variants.append((part, False))
        return variants


@cache
def load_vocabulary(path: Path = DATA_FILE) -> Vocabulary:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return Vocabulary([Concept(**c) for c in payload["concepts"]])
