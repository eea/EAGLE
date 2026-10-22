# 🦅 EAGLE tools

Prototypes around the **EAGLE concept** (EEA / EIONET): a model that decomposes land cover
and land use class definitions into reusable building blocks, so that classes from
different nomenclatures can be compared in a machine-readable way.

The EAGLE matrix has three blocks:

| Block | Meaning | Example |
| --- | --- | --- |
| **LCC** | Land Cover Components | Trees, Bare Rock, Graminoids |
| **LUA** | Land Use Attributes | Agriculture, Forestry, Residential |
| **LCH** | Land Characteristics (parameters, patterns, management, status) | Scattered Pattern, Irrigation, Mowing |

A class definition is *bar coded* by assigning bar code values (X, 1–5) to matrix elements.
See the EAGLE Matrix Bar-Coding Manual (v3.2) for the method.

## Projects

| Project | What it does | Status |
| --- | --- | --- |
| [`eagle-eye`](eagle-eye/README.md) | Text analysis web app: paste or upload a class description and see the LCC / LUA / LCH terms highlighted, resolved to concrete EAGLE elements with confidence, reasons and definitions. | `v0.2.0` |
| [`eagle-iso-mapper`](eagle-iso-mapper/README.md) | Bidirectional mapping between EAGLE barcoding matrices (Excel) and ISO 19144-2 (LCML) XML as exported by the FAO LChS tool, built on LinkML and SSSOM. | prototype 2 |

Both are Streamlit applications managed with [uv](https://docs.astral.sh/uv/) and need
Python 3.13.

## Quick start

EAGLE Eye:

```bash
cd eagle-eye
uv run streamlit run app.py
```

EAGLE ISO Mapper:

```bash
cd eagle-iso-mapper
uv run run.py
```

Each project has its own tests (`uv run pytest`) and README with details.

## Repository layout

```
eagle-eye/          text analysis: extractor, resolver, Streamlit UI, EAGLE vocabulary
eagle-iso-mapper/   EAGLE <-> ISO 19144-2 mapping: LinkML schema, SSSOM crosswalk, UI, test data
```

The FAO Land Characterisation System (LChS) tool, which produces and consumes the ISO
19144-2 files, is an external tool and not part of this repository.

## Sources

* EAGLE matrix v3.2 and the Bar-Coding Manual, EEA / EIONET
* [EAGLE vocabulary](https://dd.eionet.europa.eu/vocabulary/landcover/eagle/) in the Eionet Data Dictionary (element definitions)
* ISO 19144-2 (Land Cover Meta Language), FAO LChS tool

## Versions

Releases are tagged per project, e.g. `eagle-eye-v0.1.0`, `eagle-eye-v0.2.0`.
