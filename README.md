# Reproducible synthetic workflow for slaughterhouse supply zones

This repository is a complete Python reconstruction of the analytical workflow in:

> Brandão Jr., A., Rausch, L., Munger, J., & Gibbs, H. K. (2023). Mapping slaughterhouse supply zones in the Brazilian Amazon with cattle transit records. *Land, 12*(9), 1782. https://doi.org/10.3390/land12091782

It creates and analyzes **entirely fictitious data**. No confidential GTA, CAR, slaughterhouse, land-use, deforestation, or carbon data are included. The synthetic results are designed to exercise every analytical stage, not to reproduce the paper's empirical estimates.

## What the workflow reproduces

1. Synthetic GTA transactions, CAR-like property polygons, slaughterhouses, protected areas, land use, deforestation, and carbon-density data.
2. Strict GTA–CAR record linkage with multiple deterministic rules.
3. Selection of slaughterhouses with more than 1,000 slaughtered cattle per year and a sanitary inspection code.
4. Identification of direct and tier-1 indirect suppliers in the same year, with the 16-head transaction threshold and property-level role hierarchy.
5. Incremental spatial autocorrelation using cattle-volume-weighted Global Moran's I across increasing distance bands.
6. Supply-zone construction using an open-source equivalent of polygon aggregation.
7. Classification into CA direct, CA indirect, non-CA direct, and non-CA indirect zones.
8. Area, overlap, persistence, distance, land-use, deforestation, carbon-emission, supplier-role, and expansion-pathway analyses.
9. Main and supplementary-style figures and machine-readable tables.
10. Automated QA checks, provenance manifests, and tests.

## Quick start

Python 3.11 or 3.12 is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

The complete run writes data to `data/`, tables to `outputs/tables/`, spatial layers to `outputs/spatial/`, figures to `outputs/figures/`, and validation reports to `outputs/qa/`.

## One-command alternatives

```bash
make reproduce
```

or:

```bash
docker build -t synthetic-supply-zones .
docker run --rm -v "${PWD}/outputs:/app/outputs" synthetic-supply-zones
```

## Important methodological note

The published analysis used ArcGIS Pro 3.1.3 Incremental Spatial Autocorrelation and Aggregate Polygons. This repository uses transparent open-source analogues:

- cattle-volume-weighted Global Moran's I with deterministic permutation z-scores across distance bands;
- half-distance buffer, dissolve, and negative-buffer polygon aggregation, followed by configurable cattle-volume coverage filtering.

These implement the same analytical logic but are not guaranteed to produce byte-for-byte ArcGIS results. See `docs/METHODS.md` and `docs/ARCGIS_EQUIVALENCE.md`.

## Repository map

```text
config/                 Reproducible parameters
data/raw/               Generated fictitious source data
data/interim/           Linked records and analytical samples
docs/                   Methods, data dictionary, and limitations
outputs/figures/        Main and supplementary-style figures
outputs/spatial/        Final GeoPackage layers
outputs/tables/         Results in CSV format
outputs/qa/             Machine-readable and narrative QA reports
src/supply_zones/       Python package
tests/                  Unit and integration tests
```

## Citation and license

Use `CITATION.cff` to cite this code and the article. Code is released under the MIT License. The accompanying methodological text is provided for research reproducibility and does not change the article's CC BY license.

