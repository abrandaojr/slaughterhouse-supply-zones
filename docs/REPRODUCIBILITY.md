# Reproducibility protocol

## Clean execution

From the repository root:

```bash
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

The fixed random seed is `1782`. Running the workflow twice with the same dependency versions and configuration should reproduce the same source tables and substantively identical spatial results. GeoPackage byte hashes may change because container metadata and feature ordering can vary across GDAL versions.

## Continuous integration

`.github/workflows/reproduce.yml` runs the full pipeline (including PDF export via `pandoc`/`wkhtmltopdf`) and the test suite on every push and pull request. On pushes to `main`, it also commits any regenerated files under `data/` and `outputs/` (including `outputs/report/REPORT.pdf`) back to the branch, so the committed outputs never drift out of sync with the code that produced them. That auto-commit carries `[skip ci]` in its message to avoid re-triggering the workflow on itself.

## Recommended archive record

Record:

- Git commit hash;
- Python version;
- `python -m pip freeze`;
- operating system;
- GDAL, GEOS, PROJ, Rasterio, GeoPandas, and Shapely versions;
- `config/config.yml`;
- `data/raw/source_manifest.csv`;
- `outputs/qa/qa_report.json`.

## Applying the code to confidential empirical data

Do not overwrite the synthetic source files. Create an external data directory, map the empirical columns to the data dictionary, preserve access controls, and modify the configuration or loaders on a protected branch. GTA person-level identifiers must not be committed to a public repository. Validation should compare a spatially diverse sample with the original ArcGIS workflow before full execution.

