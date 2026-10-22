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

Tests: `uv run pytest`

## How it works (iteration 1)

`eagle_eye/extractor.py` pools two kinds of evidence and keeps the longest,
strongest non-overlapping spans:

1. **Curated rules** (`eagle_eye/lexicon.py`): everyday wording and patterns that EAGLE
   labels do not contain, e.g. *rocky areas*, *moderate human influence*, negated
   management lists such as *(not drained, irrigated, sown, fertilized)*, percentage
   ranges, heights and areas.
2. **EAGLE matrix labels** (`data/eagle_vocabulary.json`, 979 elements of matrix v3.2):
   matched on lemmatised tokens, so *shrub clearance* beats *shrub*.

Each highlight also carries a best-guess EAGLE element and its alternatives (shown in the
*Highlight details* table). These are preliminary: choosing the concrete class from the
whole text is iteration 2. Following the bar coding manual, only wording that is actually
in the text is highlighted; nothing is inferred.

Negated management (*not drained …*) is marked as **excluded**, the hook for bar code
value X later.

## Vocabulary

`data/eagle_vocabulary.json` is generated from the EAGLE Barcoding Template 3.2 and the
3.2 change-log workbook (element types and LC/LU relevance):

```bash
uv run --group build python scripts/build_vocabulary.py [BARCODING_DIR]
```

## Layout

```
app.py                  Streamlit page
eagle_eye/extractor.py  matching, overlap resolution, class-pane entries
eagle_eye/lexicon.py    curated rules
eagle_eye/vocabulary.py EAGLE matrix loader
eagle_eye/frontend/     small component: annotated text + class pane, click handling
eagle_eye/readers.py    upload readers (txt, md; Word/PDF plug in here)
```
