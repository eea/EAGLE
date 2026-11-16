"""Extract the EAGLE concepts the mapper needs from the shared EAGLE vocabulary JSON.

    python scripts/extract_eagle_concepts.py <path>/eagle_vocabulary.json

writes src/mapping/eagle_concepts.json: code, Eionet URI, label, level and block of every EAGLE element, so the matrix
the mapper writes (ISO -> EAGLE) has the URI, the official label and the level of every row. The mapper keeps its own
small copy to stay independent; set EAGLE_VOCABULARY to use the full shared file instead (same field names).
"""

import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(__file__).resolve().parents[1] / "src" / "mapping" / "eagle_concepts.json"
data = json.loads(source.read_text(encoding="utf-8"))
slim = {
    "source": data.get("source"),
    "version": data.get("version"),
    "concepts": [{k: c[k] for k in ("code", "uri", "label", "level", "block")} for c in data["concepts"]],
}
target.write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(f"{target}: {len(slim['concepts'])} concepts, version {slim['version']}, {target.stat().st_size // 1024} KB")
