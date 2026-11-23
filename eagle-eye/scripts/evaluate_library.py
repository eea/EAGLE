"""Compare EAGLE Eye with the expert barcodes of the eagle-barcoding-results library.

For every class file the class description is analysed and the result is compared with the
library's barcode:

* found     reference elements that EAGLE Eye has, or has a parent / child of
* exact     reference elements that EAGLE Eye has with the same code
* bcv equal exact elements with the same bar code value
* related   EAGLE Eye elements that are, or are related to, a reference element
            (the rest are elements the expert did not bar code)

Usage:
    uv run python scripts/evaluate_library.py [LIBRARY_DIR] [-v] [--lists]

LIBRARY_DIR defaults to ../eagle-barcoding-results/CLC; -v lists every difference.
--lists shows which bar code values the experts gave to elements that the text only states
plainly (no cue) inside the guide's "applicable for" and "includes" lists: the figures behind
the note on "CLCplus practice" (eagle_eye.analysis.CLCPLUS_LISTS).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collections import Counter  # noqa: E402

from eagle_eye.analysis import CLCPLUS_LISTS, analyze  # noqa: E402
from eagle_eye.sections import find_sections, section_of  # noqa: E402
from eagle_eye.vocabulary import load_vocabulary  # noqa: E402

DEFAULT = Path(__file__).resolve().parents[2] / "eagle-barcoding-results" / "CLC"


def main(argv: list[str]) -> None:
    verbose = "-v" in argv
    lists = "--lists" in argv
    args = [a for a in argv if not a.startswith("-")]
    folder = Path(args[0]) if args else DEFAULT
    vocab = load_vocabulary()

    def family(code: str) -> set[str]:
        return {c.code for c in vocab.path(code)}

    by_list: dict[str, Counter] = {kind: Counter() for kind in CLCPLUS_LISTS}
    totals = dict(reference=0, found=0, exact=0, bcv_equal=0, ours=0, related=0)
    for path in sorted(folder.glob("*_barcoded.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        reference = {r["code"]: str(r["bcv"]) for r in data["barcoding_result"]}
        analysis = analyze(data["class_description"])
        ours = {e.code: e.bcv for e in analysis.entries if e.code and e.bcv}
        sections = [x for x in find_sections(data["class_description"], lists=True) if x.kind in CLCPLUS_LISTS]
        counted = set()  # an element counts once per class and kind of list
        for m in analysis.mentions:
            section = section_of(sections, m.start) if m.section is None and not m.muted else None
            for item in m.items:
                if section and item.code in reference and item.bcv == "3" and item.bcv_basis == "assumed":
                    if (item.code, section.kind) not in counted:
                        counted.add((item.code, section.kind))
                        by_list[section.kind][reference[item.code]] += 1
        exact = [c for c in reference if c in ours]
        found = [c for c in reference if c in ours or any(c in family(o) or o in family(c) for o in ours)]
        equal = [c for c in exact if ours[c] == reference[c]]
        related = [o for o in ours if o in reference or any(o in family(r) or r in family(o) for r in reference)]
        print(
            f"{data['class_code']:7} {data['class_label'][:34]:34} reference={len(reference):2} found={len(found):2} "
            f"exact={len(exact):2} bcv equal={len(equal):2}  ours={len(ours):2} related={len(related):2}"
        )
        if verbose:
            for c in reference:
                state = "exact" if c in exact else "related" if c in found else "missing"
                print(f"    reference {c:16} bcv {reference[c]:>2}  {state}" + (f"  ours {ours[c]}" if c in ours else ""))
            for o in ours:
                if o not in related:
                    print(f"    extra     {o:16} bcv {ours[o]:>2}  {vocab.get(o).label}")
        for key, value in zip(totals, (len(reference), len(found), len(exact), len(equal), len(ours), len(related))):
            totals[key] += value
    if lists:
        print("\nExpert values of elements stated plainly (manual reading: 3) in a list, same code in the reference:")
        for kind, counter in by_list.items():
            n = sum(counter.values())
            print(f"  '{kind}' lists, n={n}: " + ", ".join(f"{v}: {c} ({c / n:.0%})" for v, c in sorted(counter.items())))
    r = totals["reference"] or 1
    print(
        f"\nTotal: {totals['found']}/{r} reference elements found ({totals['found'] / r:.0%}), {totals['exact']} exact, "
        f"{totals['bcv_equal']} with the same bar code value; EAGLE Eye suggests {totals['ours']} elements, "
        f"{totals['related']} of them related to a reference element ({totals['related'] / max(totals['ours'], 1):.0%})."
    )


if __name__ == "__main__":
    main(sys.argv[1:])
