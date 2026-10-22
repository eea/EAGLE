# 🦅 EAGLE Eye

Paste or upload a land cover / land use class description and see which parts of it
speak about the three EAGLE building blocks:

| Block | Meaning | Colour |
| --- | --- | --- |
| **LCC** | Land Cover Components | green |
| **LUA** | Land Use Attributes | purple |
| **LCH** | Land Characteristics (parameters, patterns, management, status) | gold |

Left: the text, with every recognised term highlighted. Right: the class pane with the
EAGLE elements found. Click a highlight to light up its class on the right, or click a
class to light up all its mentions in the text.

## Run

```bash
uv run streamlit run app.py
```

Tests: `uv run pytest` (they include the bar coding manual's worked examples)

## How it works

**Step 1, spotting (`eagle_eye/extractor.py`).** Two kinds of evidence are pooled and the
longest, strongest non-overlapping spans win:

1. **Curated rules** (`eagle_eye/lexicon.py`): everyday wording and patterns that EAGLE
   labels do not contain, e.g. *rocky areas*, *no human influence*, negated management
   lists such as *(not drained, irrigated, sown, fertilized)*, percentage ranges, heights.
2. **EAGLE matrix labels** (`data/eagle_vocabulary.json`, 979 elements of matrix v3.2),
   matched on lemmatised tokens, so *shrub clearance* beats *shrub*.

**Step 2, choosing the concrete class (`eagle_eye/resolver.py`).** Each span becomes one
or more EAGLE elements, with a confidence (●●●/●●○/●○○) and the reasons behind it:

* **Definitions.** Every element carries its Eionet definition. The resolver compares the
  span and its sentence with the definitions (TF-IDF), offers elements whose definition
  names the wording (*arable land* → Commercial Crop Production), and lets the
  *Excludes* notes veto an element (reeds are excluded from "Grasses, Sedges, Rushes, Cereals").
* **Whole text.** Thematic domains (AGRI, FRST, ...) and the families of the other
  elements found make some candidates more plausible; the class pane summarises the context.
* **Hierarchy.** Headings cannot describe a land unit, so *mowing* becomes "Mowing Applied,
  Frequency Unspecified"; a more specific child is taken only when the text names what sets
  it apart (*extensive grazing* → "Extensive, Freerange Grazing"). This follows the bar
  coding manual: only explicit wording counts, nothing is inferred.
* **Negation.** *(not drained, irrigated, sown, fertilized)* becomes one excluded element
  per activity (bar code value X in the manual's "Natural Grassland" example), while
  *non-irrigated* becomes the element "No Irrigation".
* **Patterns and parameters** are linked to the land cover they describe (*scattered* →
  Trees); a share applying to trees becomes Crown Cover Density.

The class pane shows each element's confidence, a "why this class" panel (reasons,
definition, alternatives) and the context. Wording without a matching element (e.g.
*moderate human influence*) stays "type only".

## Vocabulary

`data/eagle_vocabulary.json` is generated from the EAGLE Barcoding Template 3.2, the
3.2 change-log workbook (element types, LC/LU relevance) and the Eionet EAGLE vocabulary
(definitions, includes/excludes notes, thematic domains, parameter units):

```bash
uv run --group build python scripts/build_vocabulary.py [BARCODING_DIR] [EIONET_CSV]
```

Without `EIONET_CSV` the vocabulary is downloaded from dd.eionet.europa.eu.

## Layout

```
app.py                  Streamlit page
eagle_eye/extractor.py  step 1: matching, overlap resolution, data model
eagle_eye/resolver.py   step 2: concrete class, confidence, reasons
eagle_eye/analysis.py   text in, annotated analysis (class pane entries) out
eagle_eye/lexicon.py    curated rules
eagle_eye/vocabulary.py EAGLE matrix loader
eagle_eye/frontend/     small component: annotated text + class pane, click handling
eagle_eye/readers.py    upload readers (txt, md; Word/PDF plug in here)
```
