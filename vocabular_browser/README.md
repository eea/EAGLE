# EAGLE Vocabulary Browser

Static site for GitHub Pages: `index.html` plus the tooltip texts in `tips/`.

## Tooltip languages

The texts behind the "?" icons are loaded from one file per language:

| File            | Language        |
|-----------------|-----------------|
| `tips/en.json`  | English         |
| `tips/de.json`  | Deutsch         |
| `tips/no.json`  | Norsk (bokmål)  |

Each entry looks like this:

```json
"LCC-1": {
  "label": "Abiotic, Non-Vegetated Surfaces and Objects",
  "tip": "Surfaces without plants, either built by people (e.g. roads, buildings) or made of natural materials like rock, sand or soil."
}
```

To change a text, edit only the `"tip"` value and commit. `label` is the official class name and is there for reference only. Keys starting with `_` are notes and are ignored.

If an entry is missing or empty in `de.json` or `no.json`, the English text is shown instead.

### Adding a language

1. Copy `tips/en.json` to e.g. `tips/fr.json` and translate the `"tip"` values.
2. In `index.html`, add the language to `LANGS` (search for `const LANGS`) and add a button next to the others (search for `data-lang="no"`).

## Notes

- The tip files are fetched by the browser, so they only load when the page is served over http(s), e.g. on GitHub Pages. Opened directly from disk, the page falls back to the English texts built into `index.html`.
- All tip texts were drafted by AI from the official EAGLE definitions and still need expert review.
