"""Extract the vocabulary of the FAO LChS tool that the mapper must stay inside of.

    python scripts/extract_fao_profile.py <fao-tool>/public/components/DataSources

writes src/mapping/fao_lchs_profile.json: the block names with their parents, the element presence types, the
irrigation types and the blocks the irrigation and floristic characteristics may be attached to. The mapper's tests
check the crosswalk against this file, so a name the FAO tool does not know is caught before it reaches the tool.
"""

import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(__file__).resolve().parents[1] / "src" / "mapping" / "fao_lchs_profile.json"


def load(name, key):
    return json.loads((source / name).read_text(encoding="utf-8"))[key]


blocks = {b["block_id"]: b for b in load("LC_Blocks.json", "LC_Block")}
parents = {r["block_id"]: r["parent_id"] for r in load("Block_Block_LookUp.json", "LC_Block-LC_Block")}
options = {o["option_name"]: o["options"] for o in load("LC_Options.json", "LC_Options")}
characteristics = {c["characteristic_id"]: c["characteristic_reference"].strip() for c in load("LC_Characteristics.json", "LC_Characteristics")}
hosts: dict[str, list[str]] = {}
for row in load("Block_Characteristic-LookUp.json", "LC_Block-LC_Characteristic"):
    hosts.setdefault(characteristics[row["characteristic_id"]], []).append(blocks[row["block_id"]]["block_reference"])

profile = {
    "source": "FAO LChS tool, public/components/DataSources (LC_Blocks, LC_Options, Block_Block_LookUp, Block_Characteristic-LookUp)",
    "blocks": [
        {
            "id": i,
            "reference": b["block_reference"],
            "label": b["block_label"],
            "parent": blocks[parents[i]]["block_reference"] if parents.get(i) else None,
        }
        for i, b in sorted(blocks.items())
        if b["block_reference"] != "LC_Elements"
    ],
    "element_presence_types": [{"option": o["option"], "label": o["label"]} for o in options["element_presence_types"]],
    "irrigation_types": [{"option": o["option"], "label": o["label"]} for o in options["irrigationTypes"]],
    "characteristic_ids": {
        name: next(i for i, ref in characteristics.items() if ref == name)
        for name in ("LC_CultivatedAndManagedVegetationCharacteristics", "LC_FloristicAspectsCharacteristic")
    },
    "characteristic_hosts": {
        name: sorted(hosts[name])
        for name in ("LC_CultivatedAndManagedVegetationCharacteristics", "LC_FloristicAspectsCharacteristic")
    },
}
target.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"{target}: {len(profile['blocks'])} blocks, presence types {[p['label'] for p in profile['element_presence_types']]}")
