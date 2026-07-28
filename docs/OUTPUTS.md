# Output guide

| Output | Analytical purpose |
|---|---|
| `zone_area_summary.csv` | Zone area distribution by agreement, state, inspection, and supplier type |
| `cumulative_zone_area.csv` | Annual and six-year union areas |
| `zone_overlap.csv` | Pairwise intersection, denominator-specific overlap, and Jaccard overlap |
| `ca_direct_persistence.csv` | One-to-six-year coverage persistence |
| `land_use_by_zone.csv` | Land-use area and coverage within each cumulative zone type |
| `deforestation_carbon_by_zone.csv` | Deforestation and committed emissions by period and year |
| `distance_analysis.csv` | Tier-1-to-direct and CA-to-non-CA nearest distances |
| `ca_direct_supplier_flows.csv` | Destinations of movements originating at CA direct suppliers |
| `expansion_pathways.csv` | Zone, property, slaughter, and farm-movement coverage under three pathways |
| `alternative_zone_methods.csv` | Radial-buffer and supplier-hull comparisons |
| `incremental_moran.csv` | Every tested distance and selected distance for each analytical group |
| `qa_checks.csv` | Machine-readable validation gates |

The original six PNG files mirror the topics of Figures 1–3 and Supplementary Figures S1–S3. Their values remain entirely synthetic.

## Report-oriented outputs

| Output | Analytical purpose |
|---|---|
| `figure_4_land_use_composition.png` | Land-cover share inside each supply-zone type |
| `figure_5_moran_correlogram.png` | Distance-selection correlogram for four example plants |
| `figure_6_expansion_pathways.png` | Monitored area and slaughter-volume coverage under four scenarios |
| `figure_7_supplier_flows.png` | Destination of cattle heads leaving CA-linked direct properties |
| `figure_8_distance_distribution.png` | Distribution of tier-1-to-direct and CA-to-non-CA distances |
| `figure_9_alternative_methods.png` | Zone area under the incremental-autocorrelation method vs. two simpler proxies |
| `figure_10_zone_overlap_heatmap.png` | Pairwise Jaccard overlap between the four zone types |
| `figure_11_state_coverage_map.png` | Share of each state's area inside the cumulative CA-direct zone |
| `report/REPORT.md` | A single, plain-language Markdown report assembling every figure and table above with interpretation for a non-specialist reader |
| `report/REPORT.pdf` | The same report rendered to PDF via `pandoc` + `wkhtmltopdf` (skipped with a message if either is not installed; the Markdown report is the source of truth either way) |

Run `python -m supply_zones report` to rebuild only the report and its dedicated figures from already-computed tables, or `python -m supply_zones all` to regenerate everything from scratch.

Figures carry no in-image titles or disclaimer footers; captions live in `outputs/report/REPORT.md`. Geographic figures (`figure_1`, `figure_2`, `figure_3`, `figure_s3`, `figure_11`) draw a real OpenStreetMap tile basemap behind the synthetic data when `geography.mode: osm` resolves real boundaries (see `src/supply_zones/mapping.py`); this is skipped automatically in the offline fallback.

