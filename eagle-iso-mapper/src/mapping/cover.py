"""Cover ranges of one stratum: together they cover 100% of it, never more.

Every element of a stratum has a cover range (min, max percent). A stratum can only be filled if
some choice of values inside the ranges adds up to exactly 100, which needs

    sum of the minima <= 100 <= sum of the maxima.

Elements of a stratum are not all additive:
* a precluded element covers nothing: (0, 0);
* an element with a more specific element in the same stratum (LCC-2 Vegetation next to LCC-2_2_1
  Graminoids) is the sum of those, so only the most specific ones are added up;
* exclusive elements (either-or) are alternatives: one of them occurs, so the largest minimum counts once.

A range is clamped to 0..100. Minima that add up to more than 100% are scaled down in proportion
(a stratum can never be required to cover more than itself). Maxima that cannot reach 100% are
reported but not invented: the rest of the stratum is simply not described.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class CoverItem:
    code: Optional[str]  # EAGLE code, to find the elements that are summed up by a more general one
    presence: str  # ISO presence type: Fixed, Conditional, Optional, Exclusive, Precluded
    min_cover: Optional[int]
    max_cover: Optional[int]


def _clamp(item: CoverItem) -> Tuple[int, int]:
    low = 0 if item.min_cover is None else max(0, min(100, int(item.min_cover)))
    high = 100 if item.max_cover is None else max(0, min(100, int(item.max_cover)))
    return low, max(low, high)


def _specific(items: List[CoverItem], active: List[int]) -> List[int]:
    """The active elements without a more specific active element in the same stratum."""
    codes = {i: (items[i].code or "").strip() for i in active}
    result = []
    for i in active:
        code = codes[i]
        if code and any(j != i and codes[j].startswith(code + "_") for j in active):
            continue
        result.append(i)
    return result


def balance_stratum(items: List[CoverItem]) -> Tuple[List[Tuple[int, int]], List[str]]:
    """The cover range of every item, adjusted so the stratum can not exceed 100%, and warnings."""
    ranges: Dict[int, Tuple[int, int]] = {}
    for n, item in enumerate(items):
        ranges[n] = (0, 0) if item.presence == "Precluded" else _clamp(item)
    active = [n for n, item in enumerate(items) if item.presence != "Precluded"]
    leaves = _specific(items, active)
    alternatives = [n for n in leaves if items[n].presence == "Exclusive"]
    additive = [n for n in leaves if items[n].presence != "Exclusive"]
    warnings: List[str] = []

    minima = sum(ranges[n][0] for n in additive) + max((ranges[n][0] for n in alternatives), default=0)
    if minima > 100:
        scale = 100 / minima
        for n in additive + alternatives:
            low, high = ranges[n]
            ranges[n] = (int(low * scale), high)
        warnings.append(f"the minimum covers add up to {minima}%: scaled down to fit 100%")

    maxima = sum(ranges[n][1] for n in additive) + max((ranges[n][1] for n in alternatives), default=0)
    if leaves and maxima < 100:
        warnings.append(f"the maximum covers add up to {maxima}%: the stratum cannot reach 100%")
    return [ranges[n] for n in range(len(items))], warnings
