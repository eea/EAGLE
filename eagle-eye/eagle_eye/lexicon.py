"""Curated extraction rules on top of the EAGLE label matching.

EAGLE labels are matrix terms ("Bushes, Shrubs"); class definitions use everyday
language ("rocky areas", "not drained, irrigated", "moderate human influence").
Each Rule maps such wording onto an EAGLE block (LCC / LUA / LCH) and, where the
wording is specific enough, onto candidate matrix elements. Codes are checked
against the vocabulary by the test suite.

The block assignment follows the EAGLE bar coding manual (step 2): land cover and
land use terms go to LCC / LUA; parameters, thresholds, patterns, management types
and status go to LCH.
"""

import re
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Rule:
    block: str
    pattern: re.Pattern
    codes: tuple[str, ...] = ()
    score: float = 2.0
    absorb_modifiers: bool = False  # pull a preceding "maintenance"/"extensive" into the span
    negated: bool = False  # the span states that something is NOT the case
    wrap_parens: bool = False  # include enclosing "(" ")" when the span fills them
    note: str = ""
    id: str = field(default="", compare=False)


def _rule(block: str, regex: str, *codes: str, **options) -> Rule:
    return Rule(block, re.compile(regex, re.IGNORECASE), codes, **options)


# Single words that are too generic to count as a hit when they come from label parts.
GENERIC_WORDS = frozenset(
    """
    natural other unspecified applied type types use used land area areas management
    status condition mixed present value values method methods factor source
    characteristic characteristics element elements parameter parameters open closed
    high low medium small large long short dry wet cover covered level age
    water-regime activity activities product products structure structures
    surface surfaces object objects service services
    """.split()
)

# Words that qualify a management activity ("maintenance mowing", "extensive grazing").
MODIFIERS = frozenset(
    """
    maintenance regular regularly annual annually biannual extensive intensive
    occasional periodic periodically mechanical chemical manual selective minimal
    light heavy low-intensity continuous seasonal repeated
    """.split()
)

_NEG = r"(?:not|never|without|no|non|neither|nor)"
_PARTICIPLE = (
    r"(?:drained|irrigated|sown|seeded|fertili[sz]ed|ploughed|plowed|tilled|mown|mowed|cut|grazed"
    r"|burnt|burned|planted|harvested|cultivated|managed|treated|limed|pruned|cleared|sprayed"
    r"|fenced|stocked|used|farmed|logged|thinned)"
)
_SEP = r"(?:\s*,\s*(?:or\s+|and\s+|nor\s+)?|\s+(?:or|and|nor)\s+)"
_NUM = r"\d+(?:[.,]\d+)?"
_RANGE_OPEN = r"(?:more|less|greater|higher|lower|larger|smaller|taller)\s+than|at\s+least|at\s+most|up\s+to|over|under|above|below|exceeding|minimum\s+of|maximum\s+of|[<>≤≥]=?"

_RULES = (
            # ---------------------------------------------------------------- LCC
            _rule("LCC", r"(?:\(semi-?\)-?|\bsemi-?)?\bnatural\s+vegetation\b|\bvegetation\b|\bvegetated\b", "LCC-2", note="vegetation"),
            _rule("LCC", r"\bherbaceous(?:\s+(?:vegetation|plants?|cover|layer))?\b", "LCC-2_2"),
            _rule("LCC", r"\bwoody\s+(?:vegetation|plants?|species|overgrowth|growth|regeneration|encroachment)\b", "LCC-2_1"),
            _rule("LCC", r"\b(?:grass(?:es|land|lands)?|meadows?|pastures?|steppes?|savann?ahs?|prairies?|sedges?|reeds?)\b", "LCC-2_2_1"),
            _rule("LCC", r"\b(?:trees?|forests?|woodlands?|woods|copses?|stands\s+of\s+trees)\b", "LCC-2_1_1"),
            _rule("LCC", r"\b(?:shrubs?|shrublands?|bush(?:es)?|scrub|thickets?)\b", "LCC-2_1_2"),
            _rule("LCC", r"\b(?:heath(?:er|lands?)?|moors?|moorlands?)\b", "LCC-2_1_2_2", "LCH-7_1_6"),
            _rule("LCC", r"\b(?:rock(?:y|s)?(?:\s+(?:areas?|surfaces?|ground|terrain|faces?|outcrops?))?|cliffs?|(?:mineral\s+|rock\s+)?outcrops?)\b", "LCC-1_2_1_1"),
            _rule("LCC", r"\b(?:screes?|gravel|pebbles?|boulders?|stones?)\b", "LCC-1_2_2_1"),
            _rule("LCC", r"\b(?:sand(?:y)?|dunes?|beach(?:es)?)\b", "LCC-1_2_2_1_3"),
            _rule("LCC", r"\bbare\s+(?:soils?|ground|land|earth)\b", "LCC-1_2_2_2"),
            _rule("LCC", r"\bpeat\b", "LCC-1_2_2_3_2"),
            _rule("LCC", r"\b(?:lakes?|ponds?|reservoirs?|standing\s+water|water\s+bod(?:y|ies)|inland\s+waters?)\b", "LCC-3_1_1_2"),
            _rule("LCC", r"\b(?:rivers?|streams?|creeks?|canals?|water\s*courses?|brooks?)\b", "LCC-3_1_1_1"),
            _rule("LCC", r"\b(?:sea|seas|ocean|oceans|marine\s+waters?|sea\s+water)\b", "LCC-3_1_2"),
            _rule("LCC", r"\bsnow\b", "LCC-3_2_1"),
            _rule("LCC", r"\b(?:ice|glaciers?)\b", "LCC-3_2_2"),
            _rule("LCC", r"\b(?:buildings?|houses?|dwellings?)\b", "LCC-1_1_1_1"),
            _rule("LCC", r"\b(?:roads?|pavements?|paved|asphalt|concrete|impervious|sealed\s+(?:surfaces?|areas?|soils?)|car\s+parks?)\b", "LCC-1_1_1_3"),
            _rule("LCC", r"\b(?:built-?up|urban\s+fabric|artificial\s+surfaces?|constructions?)\b", "LCC-1_1"),
            # ---------------------------------------------------------------- LUA
            _rule("LUA", r"\b(?:(?:no|low|moderate|minimal|little|high|strong|intensive|heavy|limited|slight|reduced)\s+)human\s+(?:influence|impact|intervention|disturbance|interference|activity|pressure)\b",
                  "LUA-6_3", note="degree of human influence"),
            _rule("LUA", r"\bhuman\s+(?:influence|impact|intervention|disturbance|interference|activity|use)\b", note="human influence"),
            _rule("LUA", r"\b(?:agricultur(?:e|al)|farming|farmland|farms?|arable(?:\s+(?:land|farming))?|crop\s+production|livestock|animal\s+husbandry|horticultur(?:e|al))\b", "LUA-1_1"),
            _rule("LUA", r"\b(?:forestry|silviculture|timber\s+(?:production|harvesting)|logging)\b", "LUA-1_2"),
            _rule("LUA", r"\b(?:mining|quarry(?:ing)?|quarries|extraction\s+sites?|open-?cast)\b", "LUA-1_3"),
            _rule("LUA", r"\b(?:industry|industrial|manufactur(?:e|ing)|factor(?:y|ies))\b", "LUA-2"),
            _rule("LUA", r"\b(?:energy\s+production|power\s+(?:plants?|stations?)|solar\s+(?:farms?|parks?)|wind\s+(?:farms?|parks?))\b", "LUA-2_2"),
            _rule("LUA", r"\b(?:commercial|retail|offices?|services?\s+sector)\b", "LUA-3_1"),
            _rule("LUA", r"\b(?:recreation(?:al)?|leisure|sports?|tourism|tourist|golf|camping|parks?)\b", "LUA-3_4"),
            _rule("LUA", r"\b(?:transport(?:ation)?|railways?|airports?|harbou?rs?|ports|motorways?|highways?)\b", "LUA-4_1"),
            _rule("LUA", r"\b(?:waste\s+(?:disposal|treatment)|landfills?|sewage|utilit(?:y|ies))\b", "LUA-4_3"),
            _rule("LUA", r"\b(?:residential|housing|settlements?|dwelling\s+use)\b", "LUA-5"),
            _rule("LUA", r"\b(?:economic\s+use|land\s+use|land-use)\b", note="land use"),
            _rule("LUA", r"\b(?:no|without)\s+(?:economic|agricultural|forestry)\s+use\b", "LUA-6_3"),
            # ---------------------------------------------------------------- LCH
            Rule("LCH", re.compile(rf"\b{_NEG}\s+{_PARTICIPLE}(?:{_SEP}{_PARTICIPLE})*", re.IGNORECASE),
                 ("LCH-5_1_4",), score=3.0, negated=True, wrap_parens=True, note="management explicitly excluded"),
            _rule("LCH", r"\b(?:mow(?:ing|n|ed)?|cutting|haymaking)\b", "LCH-5_1_4_8", absorb_modifiers=True),
            _rule("LCH", r"\b(?:fertili[sz](?:ation|ed|er|ers|ing)|manur(?:e|ed|ing))\b", "LCH-5_1_4_2", absorb_modifiers=True),
            _rule("LCH", r"\b(?:irrigat(?:ion|ed|ing)|sprinklers?)\b", "LCH-5_1_4_5", absorb_modifiers=True),
            _rule("LCH", r"\b(?:drain(?:age|ed|ing))\b", "LCH-5_1_4_7", absorb_modifiers=True),
            _rule("LCH", r"\b(?:plough(?:ing|ed)|plow(?:ing|ed)|tillage|tilled)\b", "LCH-5_1_4_1", absorb_modifiers=True),
            _rule("LCH", r"\b(?:pesticides?|herbicides?|weed\s+control)\b", "LCH-5_1_4_3", absorb_modifiers=True),
            _rule("LCH", r"\b(?:grazing|grazed)\b", "LCH-5_1_11", absorb_modifiers=True),
            _rule("LCH", r"\b(?:sown|sowing|seeding)\b", "LCH-5_1_7_1"),
            _rule("LCH", r"\b(?:fallow(?:\s+land)?|set-?aside)\b", "LCH-5_1_6_98"),
            _rule("LCH", r"\bcrops?\b", "LCH-5_1_6"),
            _rule("LCH", r"\b(?:wheat|barley|rye|oats?|maize|rice|millet)\b", "LCH-5_1_6_1_1"),
            _rule("LCH", r"\b(?:burning|burnt)\b", "LCH-5_1_4_10", absorb_modifiers=True),
            _rule("LCH", r"\b(?:nature\s+(?:conservation|protection|reserves?)|protected\s+areas?|national\s+parks?|conservation\s+areas?)\b", "LCH-5_5_2_1", "LCH-5_5_2"),
            _rule("LCH", r"\bnatura\s*2000\b", "LCH-5_5_2_3"),
            _rule("LCH", r"\b(?:scattered|dispersed|sporadic|isolated)\b", "LCH-8_1_4"),
            _rule("LCH", r"\b(?:patch(?:es|y)|mosaics?)\b", "LCH-8_1_3"),
            _rule("LCH", r"\b(?:homogeneous|uniform)\b", "LCH-8_1_1"),
            _rule("LCH", r"\b(?:heterogeneous)\b", "LCH-8_1_2"),
            _rule("LCH", r"\b(?:rows?\s+of\s+trees|tree\s+lines?)\b", "LCH-8_2_2", score=2.5),
            _rule("LCH", r"\b(?:evergreen)\b", "LCH-3_2_1"),
            _rule("LCH", r"\b(?:deciduous)\b", "LCH-3_2_2"),
            _rule("LCH", r"\b(?:broad-?\s?lea(?:f|ved)|needle-?\s?lea(?:f|ved)|coniferous|conifers?)\b", "LCH-3_1"),
            _rule("LCH", r"\b(?:wetlands?|marsh(?:es|land)?|bogs?|fens?|swamps?|mires?)\b", "LCH-7_1_4"),
            _rule("LCH", r"\b(?:abandoned|abandonment|disused)\b", "LCH-6_1_4"),
            _rule("LCH", r"\b(?:(?:tree|crown|canopy)\s+cover(?:age)?(?:\s+density)?)\b", "LCH-3_13", score=2.5),
            # Parameters and thresholds: ranges, comparisons and measured quantities.
            _rule("LCH", rf"{_NUM}\s*(?:%|per\s?cent)?\s*(?:-|–|to)\s*{_NUM}\s*(?:%|per\s?cent)", "LCH-9_2_1", score=3.0, note="percentage range"),
            _rule("LCH", rf"(?:(?:{_RANGE_OPEN})\s*)?{_NUM}\s*(?:%|per\s?cent)", "LCH-9_2_1", score=2.5, note="percentage"),
            _rule("LCH", rf"(?:(?:{_RANGE_OPEN})\s*)?{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?\s*(?:m|meters?|metres?|cm|km)\b", "LCH-9_1_4", score=2.5, note="length / height"),
            _rule("LCH", rf"(?:(?:{_RANGE_OPEN})\s*)?{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?\s*(?:ha|hectares?|km²|km2|m²|m2)\b", "LCH-9_1_5", score=2.5, note="area"),
            _rule("LCH", rf"(?:(?:{_RANGE_OPEN})\s*)?{_NUM}(?:\s*(?:-|–|to)\s*{_NUM})?\s*(?:mm|years?|months?|days?|weeks?)\b", score=2.5, note="quantity"),
)

RULES: tuple[Rule, ...] = tuple(replace(r, id=f"{r.block}:{i}") for i, r in enumerate(_RULES))
