"""Reference texts for the tests (copies of the CLC natural grassland examples)."""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

NATURAL_GRASSLAND = (FIXTURES / "CLC 3.2.1 Natural grassland.txt").read_text(encoding="utf-8").strip()
NATURAL_GRASSLAND_GUIDE = (FIXTURES / "CLC 321 Natural grassland (illustrated guide).txt").read_text(encoding="utf-8").strip()
