"""Assemble a single, high-level Markdown report from every analytical table.

The report is written in academic English for a lay audience: it explains
what was done and why it matters without assuming prior expertise in
supply-chain traceability or spatial statistics. All figures and tables are
derived exclusively from the synthetic outputs already produced by
``characterize.py``, ``figures.py``, and ``report_charts.py``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import geopandas as gpd
import pandas as pd

from supply_zones.config import ensure_directories
from supply_zones.report_charts import ZONE_LABELS, create_report_charts

DISCLAIMER = (
    "> **A note on the data.** Every figure, table, and number in this report is "
    "computed from a fictitious dataset built specifically for this repository. "
    "No confidential cattle-transit (GTA), rural property registry (CAR), or "
    "slaughterhouse record is used or reproduced anywhere in this document. The "
    "workflow reconstructs the *analytical logic* of Brandão Jr. et al. (2023, "
    "*Land*, 12(9), 1782) in open-source tools, not its empirical findings."
)


def _fmt_int(value: float) -> str:
    return f"{value:,.0f}"


def _fmt_1(value: float) -> str:
    return f"{value:,.1f}"


def _fmt_pct(value: float) -> str:
    return f"{value:,.1f}%"


def _zone_label(zone_type: str) -> str:
    return ZONE_LABELS.get(zone_type, zone_type.replace("_", " "))


def _markdown_table(df: pd.DataFrame) -> str:
    """Render a small DataFrame as a GitHub-flavored Markdown table."""
    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    divider = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = "\n".join(
        "| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)
    )
    return f"{header}\n{divider}\n{body}"


def _image(path: str, caption: str) -> str:
    return f'![{caption}]({path})\n\n*{caption}*'


def _table_zone_overview(zones: gpd.GeoDataFrame) -> str:
    summary = (
        zones.groupby("zone_type")
        .agg(
            zone_years=("area_ha", "size"),
            mean_area_million_ha=("area_ha", lambda s: s.mean() / 1_000_000),
            median_area_million_ha=("area_ha", lambda s: s.median() / 1_000_000),
            mean_supplier_count=("supplier_count", "mean"),
        )
        .reindex(list(ZONE_LABELS))
        .reset_index()
    )
    out = pd.DataFrame(
        {
            "Zone type": summary["zone_type"].map(_zone_label),
            "Zone-years observed": summary["zone_years"].map(_fmt_int),
            "Mean annual area (million ha)": summary["mean_area_million_ha"].map(_fmt_1),
            "Median annual area (million ha)": summary["median_area_million_ha"].map(_fmt_1),
            "Mean number of properties": summary["mean_supplier_count"].map(_fmt_1),
        }
    )
    return _markdown_table(out)


def _table_overlap(overlap: pd.DataFrame) -> str:
    out = pd.DataFrame(
        {
            "Zone type A": overlap["zone_type_a"].map(_zone_label),
            "Zone type B": overlap["zone_type_b"].map(_zone_label),
            "Share of A inside B (%)": overlap["percent_of_a"].map(_fmt_pct),
            "Share of B inside A (%)": overlap["percent_of_b"].map(_fmt_pct),
            "Overlap index, Jaccard (%)": overlap["jaccard_percent"].map(_fmt_pct),
        }
    )
    return _markdown_table(out)


def _table_persistence(persistence: pd.DataFrame) -> str:
    subset = persistence[persistence["state"] == "ALL"].copy()
    out = pd.DataFrame(
        {
            "Years covered out of 6": subset["years_present"],
            "Cumulative area (thousand ha)": (subset["area_ha"] / 1_000).map(_fmt_1),
            "Share of the ever-covered footprint (%)": subset["percent_of_ever_covered"].map(
                _fmt_pct
            ),
        }
    )
    return _markdown_table(out)


def _table_deforestation(deforestation: pd.DataFrame) -> str:
    annual = deforestation[deforestation["period"] == "annual_2008_2018"]
    totals = (
        annual.groupby("zone_type")[["deforestation_ha", "emissions_mtco2e"]]
        .sum()
        .reindex(list(ZONE_LABELS))
        .reset_index()
    )
    out = pd.DataFrame(
        {
            "Zone type": totals["zone_type"].map(_zone_label),
            "Deforestation, 2008-2018 (thousand ha)": (totals["deforestation_ha"] / 1_000).map(
                _fmt_1
            ),
            "Committed emissions, 2008-2018 (MtCO2e)": totals["emissions_mtco2e"].map(_fmt_1),
        }
    )
    return _markdown_table(out)


def _table_expansion(expansion: pd.DataFrame) -> str:
    labels = {
        "current_CA_direct": "Current (signatory direct only)",
        "pathway_1_add_CA_tier1": "Add signatory tier-1 indirect",
        "pathway_2_add_non_CA_direct": "Add non-signatory direct",
        "pathway_3_all_direct_and_tier1": "All direct and tier-1 suppliers",
    }
    data = expansion.set_index("scenario").loc[list(labels)].reset_index()
    out = pd.DataFrame(
        {
            "Monitoring scenario": data["scenario"].map(labels),
            "Zone area (million ha)": (data["zone_area_ha"] / 1_000_000).map(_fmt_1),
            "Properties covered": data["monitored_property_count"].map(_fmt_int),
            "Slaughter volume covered (%)": data["slaughter_volume_coverage_percent"].map(
                _fmt_pct
            ),
        }
    )
    return _markdown_table(out)


def _table_alternative_methods(alternatives: pd.DataFrame) -> str:
    means = alternatives[
        ["paper_analogue_area_ha", "radial_buffer_area_ha", "supplier_hull_proxy_area_ha"]
    ].mean()
    median_overestimate = alternatives["radial_overestimate_percent"].median()
    out = pd.DataFrame(
        {
            "Method": [
                "Incremental spatial-autocorrelation (this workflow)",
                "Simple radial buffer around the plant",
                "Supplier convex-hull proxy",
            ],
            "Mean zone area (million ha)": [
                _fmt_1(means["paper_analogue_area_ha"] / 1_000_000),
                _fmt_1(means["radial_buffer_area_ha"] / 1_000_000),
                _fmt_1(means["supplier_hull_proxy_area_ha"] / 1_000_000),
            ],
            "Median overestimate vs. this workflow (%)": [
                "-",
                _fmt_pct(median_overestimate),
                "-",
            ],
        }
    )
    return _markdown_table(out)


def build_report(cfg: dict, zones: gpd.GeoDataFrame, results: dict) -> Path:
    paths = ensure_directories(cfg)
    report_dir = paths["root"] / "outputs" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    create_report_charts(cfg, results)

    figures_relative = "../figures"
    persistence = results["persistence"]
    overlap = pd.read_csv(paths["tables"] / "zone_overlap.csv")
    deforestation = results["deforestation"]
    expansion = results["expansion"]
    alternatives = results["alternatives"]

    n_states = zones["state"].nunique()
    n_plants = zones["slaughterhouse_id"].nunique()
    years = f"{int(zones['year'].min())}-{int(zones['year'].max())}"
    n_years = len(cfg["project"]["years"])
    ca_direct_area = (
        zones.loc[zones["zone_type"] == "CA_direct", "area_ha"].mean() / 1_000_000
    )
    try:
        states_layer = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
        name_column = "state_name" if "state_name" in states_layer.columns else "state"
        place_names = states_layer[name_column].map(lambda n: n.split(",")[0].strip()).tolist()
    except Exception:
        place_names = []
    place_phrase = ", ".join(place_names) if place_names else f"{n_states} configured regions"

    sections = []

    sections.append(
        f"""# Mapping Slaughterhouse Supply Zones: A Reproducible, Geographically Generic Walkthrough

**A plain-language companion to Brandão Jr., Rausch, Munger & Gibbs (2023), *Land*, 12(9), 1782**

{DISCLAIMER}

## Executive summary

Cattle can travel through several properties before reaching a slaughterhouse,
which makes it hard to know exactly where the animals a company buys actually
came from. This report walks through a complete, open-source, geographically
generic workflow that estimates the area, or **supply zone**, that feeds each
slaughterhouse, and separates that area into farms that sell cattle directly
to the plant from farms that sell only through an intermediary. The workflow
can be pointed at any region in the world by naming it in the project
configuration; real administrative boundaries are then fetched from
OpenStreetMap or the public-domain Natural Earth dataset, both open and
globally available, or a deterministic offline layout is used when neither
can be reached. Using an
illustrative synthetic dataset configured for {place_phrase}, across
{n_states} regions, {n_plants} slaughterhouses, and the years {years}, the
workflow finds that the average direct supply zone of a signatory plant (a
plant that has joined a public sourcing commitment) covers about
{_fmt_1(ca_direct_area)} million hectares, that roughly a quarter of that area
is natural vegetation, and that extending monitoring to indirect suppliers or
non-signatory plants would substantially widen coverage of the cattle trade
at the cost of a much larger area to monitor. Every number below comes from
fictitious data; the value of the exercise is the method, not the estimate."""
    )

    sections.append(
        """## 1. Why supply zones matter

Companies, regulators, and civil-society groups that want to know whether
cattle products are linked to deforestation face a basic geographic problem:
purchase records name a slaughterhouse, not a location on a map. A supply
zone translates the plant's likely catchment area for cattle into an
explicit polygon, so it can be overlaid with land use, deforestation, and
protected-area data to ask questions such as: how much of a plant's likely
sourcing area still has forest cover, and how does that compare between
plants that have signed a public sourcing commitment (referred to here as
"signatory" plants, after Brazil's Cattle Agreement, the case this workflow
was originally built around) and plants that have not.

The original study built these zones from confidential cattle-transit permits
(GTA) and rural property registrations (CAR) using proprietary ArcGIS
routines. This repository asks a narrower question with synthetic stand-in
data: can the same analytical logic be reproduced end to end with transparent,
open-source tools, and does doing so change how the results should be read.
Full methodological detail is in `docs/METHODS.md`; this report focuses on
what each result means for a non-specialist reader."""
    )

    sections.append(
        f"""## 2. Study design in brief

The workflow simulates {n_years} years of fictitious cattle-transit records, rural
property boundaries, slaughterhouse locations, land use, and deforestation
across {n_states} regions. It then:

1. Links each transit record to a property using deterministic matching rules.
2. Classifies slaughterhouses as eligible when they process more than 1,000
   head per year and hold a sanitary inspection code, matching the
   thresholds used in the source study.
3. Identifies **direct suppliers** (properties that sell straight to an
   eligible plant) and **tier-1 indirect suppliers** (properties that sell to
   a direct supplier, using the same 16-head minimum transaction threshold).
4. Chooses, separately for every plant and year, the distance at which
   cattle-volume-weighted spatial clustering (Global Moran's I) peaks, and
   uses that distance to aggregate supplier properties into a single supply
   zone (an open-source analogue of the original ArcGIS Aggregate Polygons
   step).
5. Cross-tabulates the resulting zones against land use, deforestation,
   carbon density, and protected or military areas.

{_image(f'{figures_relative}/figure_1_study_area.png', 'Figure 1. Synthetic study area, slaughterhouse locations, and linked properties.')}"""
    )

    sections.append(
        f"""## 3. How large are supply zones, and how much do they overlap

{_table_zone_overview(zones)}

Signatory plants have direct supply zones that are, on average, larger
than their non-signatory counterparts in this synthetic dataset, largely
because signatory plants tend to source from more properties. The zones are
not mutually exclusive: a property can appear inside more than one plant's
catchment, and different zone types partly cover the same territory.

{_table_overlap(overlap)}

{_image(f'{figures_relative}/figure_2_zone_overlap.png', f'Figure 2. Cumulative overlap of all four supply-zone types, {years}.')}

{_image(f'{figures_relative}/figure_10_zone_overlap_heatmap.png', 'Figure 10. Pairwise spatial overlap between zone types, summarized as a Jaccard index.')}"""
    )

    sections.append(
        f"""## 4. Does the same area stay in the supply zone every year

A property that supplies a plant only once is a weaker basis for monitoring
than one that supplies it consistently. The workflow tracks, pixel by pixel,
how many of the {n_years} years a location falls inside the signatory direct
supply zone.

{_table_persistence(persistence)}

{_image(f'{figures_relative}/figure_3_persistence.png', 'Figure 3. Number of years each location falls inside the signatory direct supply zone.')}"""
    )

    sections.append(
        f"""## 5. What land cover is inside each supply zone

{_image(f'{figures_relative}/figure_4_land_use_composition.png', 'Figure 4. Land-cover composition inside each supply-zone type.')}

Natural vegetation, pasture, soybean cropland, and a residual "other" class
are cross-tabulated against each zone type, after excluding officially
protected and military areas from the denominator for the natural-vegetation
figure so that it reflects land that is legally available for conversion."""
    )

    sections.append(
        f"""## 6. Deforestation and carbon inside the signatory direct zone

{_table_deforestation(deforestation)}

{_image(f'{figures_relative}/figure_s2_deforestation_carbon.png', 'Figure S2. Annual synthetic deforestation and committed carbon emissions inside the signatory direct zone.')}"""
    )

    sections.append(
        f"""## 7. How the supply-zone radius is chosen for each plant and year

Rather than applying one fixed radius to every plant, the workflow tests a
range of distances for each plant-year and keeps the one at which
cattle-volume-weighted spatial clustering is strongest. This makes zones
larger around plants with a spatially concentrated supplier base and smaller
around plants whose suppliers are scattered.

{_image(f'{figures_relative}/figure_5_moran_correlogram.png', "Figure 5. Correlogram of Moran's I against distance for four example slaughterhouses; the marked point is the distance actually used to build that plant-year's zone.")}"""
    )

    sections.append(
        f"""## 8. Where does the cattle that leaves a signatory property end up

{_image(f'{figures_relative}/figure_7_supplier_flows.png', 'Figure 7. Destination of cattle heads that leave signatory direct properties.')}

Only part of the cattle that leaves a signatory direct property is
slaughtered at a signatory plant; the remainder is either slaughtered
elsewhere or moved to another property first, which is exactly the kind of
leakage that indirect-supplier monitoring is designed to catch."""
    )

    sections.append(
        f"""## 9. How far apart are direct suppliers, indirect suppliers, and rival plants

{_image(f'{figures_relative}/figure_8_distance_distribution.png', 'Figure 8. Distribution of two distance measures: tier-1 indirect supplier to nearest direct supplier, and signatory plant to nearest non-signatory plant.')}"""
    )

    sections.append(
        f"""## 10. What would happen if monitoring were extended

{_table_expansion(expansion)}

{_image(f'{figures_relative}/figure_6_expansion_pathways.png', 'Figure 6. Monitored area and slaughter-volume coverage under four expansion scenarios.')}

Adding non-signatory direct suppliers to the monitored footprint captures far
more of the slaughter volume in this synthetic scenario than adding tier-1
indirect suppliers of signatory plants does, but it also requires monitoring
a substantially larger area, illustrating the coverage-versus-scope trade-off
that any traceability system has to navigate."""
    )

    sections.append(
        f"""## 11. Does the choice of method matter

{_table_alternative_methods(alternatives)}

{_image(f'{figures_relative}/figure_9_alternative_methods.png', 'Figure 9. Zone area under the incremental spatial-autocorrelation method compared with two simpler distance-based proxies.')}

Simple proxies, such as a fixed-radius buffer around the plant, tend to
overestimate the true supply zone because they ignore the actual geographic
spread of a plant's supplier base; the overestimate is largest, sometimes by
more than an order of magnitude, in plant-years where the true supply zone is
small and tightly clustered. The median is reported above rather than the
mean because a handful of these small-zone plant-years produce extreme
percentage overestimates that would otherwise dominate the average. This is a
methodological caution for anyone tempted to shortcut the distance-selection
step to save computation time."""
    )

    sections.append(
        f"""## 12. Where the supply zone sits geographically, region by region

{_image(f'{figures_relative}/figure_11_state_coverage_map.png', "Figure 11. Share of each region's territory that falls inside the cumulative signatory direct supply zone.")}"""
    )

    sections.append(
        """## 13. Limitations

- **All data are synthetic.** Every property boundary, transaction, and
  slaughterhouse in this repository was generated for testing purposes and
  carries no relationship to actual locations, companies, or individuals.
- **The open-source distance-selection and aggregation methods are declared
  analogues, not certified reproductions,** of the original study's ArcGIS
  Pro routines; see `docs/ARCGIS_EQUIVALENCE.md` for a line-by-line
  comparison of assumptions.
- **Land-use and deforestation layers are simplified** into four classes and
  a single annual raster; the original study's underlying data sources are
  richer.
- **Supplier-hull and radial-buffer comparisons are illustrative proxies**
  built for this repository; they should not be read as a critique of any
  specific commercial GIS workflow.

## 14. How to reproduce every number in this report

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

This regenerates the synthetic input data, reruns every analytical step
described above, rebuilds every figure and table referenced in this report
(including this document itself), and runs the automated QA gates in
`outputs/qa/QA_REPORT.md`.

## Citation

Please cite the original article for the underlying method, and
`CITATION.cff` in this repository for the synthetic reproduction code."""
    )

    report_path = report_dir / "REPORT.md"
    report_path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    build_pdf_report(report_path)
    return report_path


def build_pdf_report(report_path: Path) -> Path | None:
    """Render ``REPORT.md`` to a matching ``REPORT.pdf`` alongside it.

    Uses ``pandoc`` (with the ``wkhtmltopdf`` PDF engine) so the Markdown's
    tables and embedded figures render as they would in a browser, styled
    with ``report_style.css``. This is a visual convenience on top of the
    Markdown source, not a separate source of truth: if ``pandoc`` or
    ``wkhtmltopdf`` is not installed, PDF generation is skipped with a clear
    message rather than failing the pipeline, since the Markdown report
    alone already satisfies full reproducibility.
    """
    if shutil.which("pandoc") is None or shutil.which("wkhtmltopdf") is None:
        print(
            "[report] Skipping PDF export: `pandoc` and `wkhtmltopdf` are both "
            "required on PATH. Install them (e.g. `apt-get install pandoc "
            "wkhtmltopdf`) to enable it; the Markdown report is unaffected."
        )
        return None

    css_path = Path(__file__).resolve().parent / "report_style.css"
    pdf_path = report_path.with_suffix(".pdf")
    try:
        subprocess.run(
            [
                "pandoc",
                report_path.name,
                "-o",
                pdf_path.name,
                "--pdf-engine=wkhtmltopdf",
                "--css",
                str(css_path),
                "--metadata",
                "title=Mapping Slaughterhouse Supply Zones",
                "--quiet",
            ],
            cwd=report_path.parent,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[report] PDF export failed ({exc.stderr.strip()[:500]}); the Markdown report is unaffected.")
        return None
    print(f"[report] Wrote {pdf_path}")
    return pdf_path
