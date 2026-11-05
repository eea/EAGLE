# EAGLE barcoding results library — JSON schema

This library contains  one sub-folder per dataset containing one JSON file per **class** of each  land-monitoring dataset, such as CLC 2018, Urban Atlas, Coastal Zones, the High Resolution Layers and the VLCC and CLCplus Backbone products. Each file records the dataset metadata and the class's **EAGLE barcode**: the EAGLE matrix elements that describe the class, each with a barcode value. The files are located in one sub-folder per dataset, as described below.

## Folder and file layout

```
eagle-barcoding-results-library/
  <DATASET>/                                 one sub-folder per dataset, e.g. EFFIS2021, CLC, VLCC_TCD2022_EU27
    <prefix><class code>_<class_name_slug>_barcoded.json
```

- **File name:** prefix + class code + lower-case class name (non-alphanumeric characters become `_`) + `_barcoded.json`, for example `EFFIS2021_1_index_barcoded.json` and `CLC124_airports_barcoded.json`.

- **Sub-folder name:** the dataset prefix without the trailing `_` or the dataset name if it has no prefix. Where several versions of a dataset share a name, an extra text is added (e.g. `CLC_older_ingestion`).
- All files are UTF-8 and pretty-printed with 2-space indentation.

## Top-level object

All metadata values are strings. A value is `null` when there is no information available or  if it does not apply to the respective dataset.

| Field | Type | Description | Example |
|---|---|---|---|
| `dataset_name` | string | Dataset name. | `"EFFIS 2021"` |
| `dataset_type` | string  | Data model of the dataset.  | `"vector", "raster"` |
| `spatial_coverage` | string | Geographic coverage of the dataset. | `"European Union (27)"`, `"Netherlands/Nederland"` |
| `reference_year` | string | Reference year of the dataset, `YYYY`. | `"2021"` |
| `time_range` | string | Period covered, `DD.MM.YYYY - DD.MM.YYYY`. | `"01.01.2017 - 31.12.2018"` |
| `class_resolution` | string \| null | Resolution of the class. Only applies to raster datasets | `"10 m", "100 m"` |
| `class_mmu` | string \| null | Minimum mapping unit. Only applies for vector datasets. | `"25 ha"` |
| `class_code` | string | Class code, without the class name. | `"1"`, `"1.2.4"`, `"42100"` |
| `class_label` | string | Class name. | `"index"`, `"Airports"`, `"Semi-natural grassland"` |
| `class_description_source` | string | URL of the class definition text. | CLC nomenclature guideline page |
| `class_description` | string | Class definition: plain text with `\n` line breaks and `- ` list items. |"Definition:\nThe continuous urban fabric class is assigned when urban structures and transport networks are dominating..." |
| `barcoding_created_by` | string | Person or account that created the barcoding. | `"User Admin/Support CLCplus Core"` |
| `barcoding_created_at` | string | Date the barcoding was created, `DD.MM.YYYY`. | `"27.02.2024"` |
| `EAGLE_matrix_version` | string | EAGLE matrix version used | `"3.2"` |
| `EAGLE_matrix_url` | string | Download URL of the EAGLE matrix used. | `"https://land.copernicus.eu/en/technical-library/eagle-matrix-3_2/@@download/file"` |
| `barcoding_source` | string | Where the barcoding result comes from. | `"CLCplus Core"` |
| `barcoding_source_url` | string | URL of the dataset's catalogue entry. | `"https://clcplus-core.land.copernicus.eu/datacatalogue/ingestion/<uuid>"` |
| `barcoding_result` | array of objects | The class's EAGLE barcode; see the next section. | |




## `barcoding_result` entries

Each entry is one EAGLE matrix element assigned to the class (first LCC, then LUA, then LCH).

| Field | Type | Description |
|---|---|---|
| `code` | string | EAGLE element code, `<BLOCK>-<n>[_<n>...]`. |
| `name` | string | EAGLE element name. A given `code` always has the same `name`. |
| `bcv` | integer \| null | Barcode value, 1 to 5. A higher value means a stronger association; see the EAGLE barcoding template for the exact meaning. `null` when `excluded` is `true`. |
| `excluded` | boolean | `true` when the element is explicitly excluded from the class (`X` in the Excel sheet). In that case `bcv` is `null`. |
| `factor` | number \| null | Factor value of the barcode entry. `null` when the Factor cell is empty in the Excel sheet.  |

Only elements that have a value are listed. An EAGLE element that does not appear in `barcoding_result` is not used for that class.

Every entry carries the `factor` field, as the last key.

### EAGLE code blocks

| Prefix | EAGLE block | Example |
|---|---|---|
| `LCC` | Land Cover Components | `LCC-1_1_1` Sealed Artificial Surfaces and Constructions |
| `LUA` | Land Use Attributes | `LUA-5_1` Permanent Residential |
| `LCH` | Land Characteristics | `LCH-6_2_3_1` Forest Fire, Wildfire |

The underscore-separated numbers give the position in the EAGLE hierarchy. For example, `LCC-1` is the parent of `LCC-1_1`, which is the parent of `LCC-1_1_1`. 

## Example

`CLC/CLC123_port_areas_barcoded.json´:

```json
{
  "dataset_name": "Corine Land Cover (CLC) 2018",
  "dataset_type": "vector",
  "spatial_coverage": "European Environment Agency (38+UK)",
  "reference_year": "2018",
  "time_range": "01.01.2017 - 31.12.2018",
  "class_resolution": null,
  "class_mmu": "25 ha",
  "class_code": "1.2.3",
  "class_label": "Port areas",
  "class_description_source": "https://land.copernicus.eu/content/corine-land-cover-nomenclature-guidelines/html/index-clc-123.html",
  "class_description": "Definition:\nInfrastructure of port areas (land and water surface), including quays, dockyards and marinas.\nThis class is applicable for:\n- sea ports, river ports, lake ports\n- commercial and military ports;\n- shipyards;\n- fishing ports;\n- yachts ports, sport and recreation ports;\n- oil terminals inside port area.\nThis class includes:\n- shipping and infrastructure port facilities;\n- harbour stations, dock houses, buildings associated to port activities;\n- tanks and pipelines;\n- dockyards, wet and dry docks;\n- roads, railways and parking lots within the port area;\n- sealed or non-sealed storage and loading areas;\n- piers, quays and breakwaters wider than 100 m;\n- harbour basins shirted by quays if the area of infrastructure of the port (firm land part) is smaller than 25 ha\n- strips of industrial units below 25 ha adjacent to the harbour.\nThis class is not applicable for:\n- industrial and commercial units > 25 ha associated with port activities (class 121).\nThis class excludes:\n- water surfaces inside port areas > 25 ha or wider than 100 m (class 511 or 512 or 523).",
  "barcoding_created_by": "Renner Thomas",
  "barcoding_created_at": "08.10.2026",
  "EAGLE_matrix_version": "3.2",
  "EAGLE_matrix_url": "https://land.copernicus.eu/en/technical-library/eagle-matrix-3_2/@@download/file",
  "barcoding_source": "CLCplus Core",
  "barcoding_source_url": "https://clcplus-core.land.copernicus.eu/datacatalogue/ingestion/91a20905-e4c0-47ab-badb-9866ab9d1d99",
  "barcoding_result": [
    {
      "code": "LCC-1_1_1",
      "name": "Sealed Artificial Surfaces and Constructions",
      "bcv": 3,
      "excluded": false,
      "factor": 1.0
    },
    {
      "code": "LCC-1_1_2_1",
      "name": "Open Non-Sealed Artificial Surfaces",
      "bcv": 1,
      "excluded": false,
      "factor": 1.0
    },
    {
      "code": "LCC-3_1",
      "name": "Liquid Water Bodies",
      "bcv": 1,
      "excluded": false,
      "factor": 1.0
    },
    {
      "code": "LUA-4_1_4",
      "name": "Water Transport",
      "bcv": 3,
      "excluded": false,
      "factor": 1.0
    }
  ]

}
```

## Next steps

- Include all barcoding results from CLCplus Core platform
- Extract descriptions from CLMS PUM documents
- Include barcoding results from other known sources
