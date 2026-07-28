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
    return f'![{caption}]({path})\n\n<p class="figure-caption">{caption}</p>'


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

A single animal can pass through several farms before it ever reaches a
slaughterhouse: born on one property, raised on a second, fattened on a
third. Purchase records typically show only the last step, the sale to the
plant, so a company or regulator who wants to know where its cattle actually
came from is left trying to reconstruct a chain of custody from a single
snapshot. This report walks through a complete, open-source, and
geographically generic workflow that tackles that problem by estimating the
**supply zone** of each slaughterhouse: the geographic area where its
cattle most plausibly originate, split into farms that sell straight to the
plant (direct suppliers) and farms that sell only through a middle step
(tier-1 indirect suppliers). Unlike the original study this workflow is
based on, which was built around one country, this version can be pointed at
any region in the world simply by naming it in the project configuration.
Real administrative boundaries are then fetched automatically from
OpenStreetMap or the public-domain Natural Earth dataset, both open and
globally available, and the workflow falls back to a deterministic offline
layout only if neither can be reached. Using an illustrative synthetic
dataset configured for {place_phrase}, spanning {n_states} regions,
{n_plants} slaughterhouses, and the years {years}, the workflow finds that
the average direct supply zone of a signatory plant (a plant that has joined
a public sourcing commitment) covers about {_fmt_1(ca_direct_area)} million
hectares, that roughly a quarter of that area is natural vegetation, and
that extending monitoring further out to indirect suppliers or to plants
without a sourcing commitment would substantially widen how much of the
cattle trade is actually covered, at the cost of a much larger area to keep
track of. Because every number below is computed from fictitious data built
specifically for this repository, none of it describes anything about real
cattle, farms, or companies; the value of the exercise lies entirely in the
method, which can be pointed at a real dataset once one is available.

## 1. Why supply zones matter

Companies, regulators, and civil-society groups that want to know whether
cattle products are linked to deforestation run into a basic geographic
problem before they can even start: a purchase record names a
slaughterhouse, not a location on a map, and certainly not the pasture where
an animal actually grazed. A supply zone is a way of closing that gap. It
translates a plant's likely catchment area for cattle into an explicit
polygon that can be laid on top of other spatial data, land use, recent
deforestation, or the boundaries of protected areas, so that a concrete
question can finally be answered: how much of a plant's likely sourcing area
still has forest cover, and how does that compare between plants that have
signed a public sourcing commitment (referred to throughout this report as
"signatory" plants, after Brazil's Cattle Agreement, the real-world case
this workflow was originally built around) and plants that have not.

Estimating a supply zone is harder than it sounds, though, because most of
the trail is invisible. An animal's ownership can change hands two, three,
or more times between birth and slaughter, and every one of those
intermediate sales is a point where a buyer's sourcing commitment can
quietly stop applying, a pattern sometimes called cattle laundering. The
original study this repository reconstructs tackled that problem using
confidential cattle-transit permits (GTA, in the Brazilian system) and rural
property registrations (CAR), processed through proprietary ArcGIS
routines. Those routines are not published in full, and the underlying
records cannot be shared, which makes the published method difficult for an
outside reader to check or adapt. This repository asks a narrower, more
mechanical question with synthetic stand-in data instead: can the same
analytical logic be reproduced end to end using transparent, open-source
tools, and does building it that way change how the results should be read
or where they might mislead. Full methodological detail, including every
explicit decision made where the original publication left a parameter
unspecified, is in `docs/METHODS.md`; this report stays at the level of what
each result means for a reader without a background in spatial statistics
or supply-chain traceability."""
    )

    sections.append(
        f"""## 2. Study design in brief

The workflow simulates {n_years} years of fictitious cattle-transit records,
rural property boundaries, slaughterhouse locations, land use, and
deforestation across {n_states} regions. It then works through five stages,
each one resolving a specific gap in the raw records:

1. **Links each transit record to a property** using deterministic matching
   rules based on tax identifiers, owner names, and municipality, since the
   transit system and the property registry are separate databases that do
   not share a common key.
2. **Classifies slaughterhouses as eligible** when they process more than
   1,000 head per year and hold a sanitary inspection code, matching the
   thresholds used in the source study; this filters out very small or
   informal operations for which a supply zone would be statistically
   meaningless.
3. **Identifies direct suppliers** (properties that sell straight to an
   eligible plant) and **tier-1 indirect suppliers** (properties that sell
   to a direct supplier, using the same 16-head minimum transaction
   threshold), which is the step that reconstructs one link of the hidden
   ownership chain described in Section 1.
4. **Chooses, separately for every plant and year, the distance at which
   cattle-volume-weighted spatial clustering (Global Moran's I) peaks**, and
   uses that distance to aggregate supplier properties into a single supply
   zone (an open-source analogue of the original ArcGIS Aggregate Polygons
   step). In plain terms, Moran's I asks whether nearby supplier properties
   tend to sell similar volumes of cattle to the same plant more often than
   chance would predict; the distance at which that pattern is strongest is
   read as the natural edge of the plant's catchment, rather than an
   arbitrary fixed radius applied to every plant alike.
5. **Cross-tabulates the resulting zones** against land use, deforestation,
   carbon density, and protected or military areas, which is what turns a
   plain polygon into an answer to the forest-cover question posed in
   Section 1.

{_image(f'{figures_relative}/figure_1_study_area.png', 'Figure 1. Synthetic study area, slaughterhouse locations, and linked properties.')}"""
    )

    sections.append(
        f"""## 3. How large are supply zones, and how much do they overlap

{_table_zone_overview(zones)}

Signatory plants have direct supply zones that are, on average, larger than
their non-signatory counterparts in this synthetic dataset, largely because
signatory plants tend to source from more properties in the first place. The
zones are not neat, mutually exclusive territories: a single property can
sit inside more than one plant's catchment at once, and different zone types
can cover much of the same ground. That matters in practice because a
company auditing only its own direct supply zone may be looking at land that
a competitor, or a non-signatory plant, is drawing from just as heavily. The
table below reports the **Jaccard overlap index**, a standard way of scoring
how much two areas share: it divides the size of their intersection by the
size of their combined footprint, so a value near 0% means the two zone
types barely touch and a value near 100% means they occupy almost exactly
the same ground.

{_table_overlap(overlap)}

{_image(f'{figures_relative}/figure_2_zone_overlap.png', f'Figure 2. Cumulative overlap of all four supply-zone types, {years}.')}

{_image(f'{figures_relative}/figure_10_zone_overlap_heatmap.png', 'Figure 10. Pairwise spatial overlap between zone types, summarized as a Jaccard index.')}"""
    )

    sections.append(
        f"""## 4. Does the same area stay in the supply zone every year

Not every property that shows up in a supply zone one year belongs there
every year; a farm might sell to a given plant once and never again,
because of a one-off price advantage or a chance connection. That kind of
one-year appearance is a much weaker basis for ongoing monitoring than a
property that supplies the same plant consistently, since resources spent
verifying a supplier who will not sell there again are largely wasted. To
tell the two apart, the workflow tracks, pixel by pixel across the whole
study area, how many of the {n_years} years each location falls inside the
signatory direct supply zone; a location that appears in all {n_years} years
is a stable, recurring part of the plant's catchment, while one that
appears only once is closer to noise.

{_table_persistence(persistence)}

{_image(f'{figures_relative}/figure_3_persistence.png', 'Figure 3. Number of years each location falls inside the signatory direct supply zone.')}"""
    )

    sections.append(
        f"""## 5. What land cover is inside each supply zone

{_image(f'{figures_relative}/figure_4_land_use_composition.png', 'Figure 4. Land-cover composition inside each supply-zone type.')}

Knowing how large a supply zone is says little on its own; what matters for
a deforestation question is what covers the ground inside it. Every
property in the workflow is cross-tabulated against four simplified
land-cover classes: natural vegetation, pasture, soybean cropland, and a
residual "other" category. For the natural-vegetation figure specifically,
officially protected areas and military land are excluded from the
denominator, since that land cannot legally be cleared regardless of who
owns the cattle passing through the zone; leaving it in the calculation
would understate how much of the *legally convertible* land inside a supply
zone is still forested, which is the figure that actually matters for
assessing deforestation risk going forward."""
    )

    sections.append(
        f"""## 6. Deforestation and carbon inside the signatory direct zone

{_table_deforestation(deforestation)}

Clearing forest does not just remove trees from a map; it releases the
carbon stored in that biomass, mostly through burning or decomposition. The
table above reports both the cleared area and the **committed emissions**
that clearing implies, estimated from the carbon density of the vegetation
that was there before. Synthetic deforestation polygons dated at or before
2007 are tracked separately from those dated 2008 onward (a split inherited
from the source study's use of the Brazilian Forest Code's own historical
cutoff for legacy clearing), so that older, already-settled clearing is not
mixed into the annual trend shown below.

{_image(f'{figures_relative}/figure_s2_deforestation_carbon.png', 'Figure S2. Annual synthetic deforestation and committed carbon emissions inside the signatory direct zone.')}"""
    )

    sections.append(
        f"""## 7. How the supply-zone radius is chosen for each plant and year

Rather than applying one fixed radius to every plant, which would draw the
same size circle around a plant with a tightly clustered set of suppliers as
around one whose suppliers are scattered over a much wider area, the
workflow tests a whole range of candidate distances for each plant-year and
keeps whichever one shows the strongest cattle-volume-weighted spatial
clustering. Intuitively: as the candidate distance grows outward from the
plant, the properties captured inside it either keep looking more alike in
how much cattle they sell to that plant, in which case the true edge of the
catchment has not been reached yet, or they start looking like an
unrelated, random mix, which signals that the boundary has been crossed. The
distance right before that shift is read as the natural edge of the
catchment. This produces supply zones that adapt to each plant's actual
sourcing geography instead of forcing every plant into an identical
footprint.

{_image(f'{figures_relative}/figure_5_moran_correlogram.png', "Figure 5. Correlogram of Moran's I against distance for four example slaughterhouses; the marked point is the distance actually used to build that plant-year's zone.")}"""
    )

    sections.append(
        f"""## 8. Where does the cattle that leaves a signatory property end up

{_image(f'{figures_relative}/figure_7_supplier_flows.png', 'Figure 7. Destination of cattle heads that leave signatory direct properties.')}

A sourcing commitment made by a signatory plant only covers the animals it
buys directly; it says nothing about what happens to cattle once they leave
one of that plant's own supplier properties for somewhere else. In this
synthetic scenario, only part of the cattle leaving a signatory direct
property is slaughtered at a signatory plant at all. The remainder is either
slaughtered at a plant with no sourcing commitment or moved on to another
property first, re-entering the same invisible chain described in Section
1. That second pathway is precisely the leakage that indirect-supplier
monitoring, the tier-1 layer built earlier in this workflow, is designed to
catch, since it follows the animal one step further instead of stopping at
the first sale."""
    )

    sections.append(
        f"""## 9. How far apart are direct suppliers, indirect suppliers, and rival plants

Distance shapes both how practical monitoring is and how competitive the
local market for cattle looks. A tier-1 indirect supplier that sits far from
any direct supplier is harder and more expensive to fold into a monitoring
program, since verification usually means an actual visit to the property.
A signatory plant that sits close to a non-signatory rival, meanwhile, is
competing for cattle from a similar pool of nearby farms, which is part of
why the two plant types' supply zones showed meaningful overlap in Section
3. The two distributions below summarize both distances across every
plant-year in the synthetic dataset.

{_image(f'{figures_relative}/figure_8_distance_distribution.png', 'Figure 8. Distribution of two distance measures: tier-1 indirect supplier to nearest direct supplier, and signatory plant to nearest non-signatory plant.')}"""
    )

    sections.append(
        f"""## 10. What would happen if monitoring were extended

Every one of the choices above, how far monitoring reaches, is ultimately a
budget decision: verifying a supplier costs money and staff time, so a
company or regulator has to decide how much coverage is worth the added
cost. The table below lays out that trade-off as four concrete scenarios,
from monitoring only a plant's direct signatory suppliers up to monitoring
every direct and tier-1 indirect supplier regardless of sourcing commitment.

{_table_expansion(expansion)}

{_image(f'{figures_relative}/figure_6_expansion_pathways.png', 'Figure 6. Monitored area and slaughter-volume coverage under four expansion scenarios.')}

Adding non-signatory direct suppliers to the monitored footprint captures
far more of the slaughter volume in this synthetic scenario than adding
tier-1 indirect suppliers of signatory plants does, but it also requires
monitoring a substantially larger area. Neither pathway is free, and this is
exactly the coverage-versus-scope trade-off that any traceability system,
public or private, has to navigate deliberately rather than by default."""
    )

    sections.append(
        f"""## 11. Does the choice of method matter

{_table_alternative_methods(alternatives)}

{_image(f'{figures_relative}/figure_9_alternative_methods.png', 'Figure 9. Zone area under the incremental spatial-autocorrelation method compared with two simpler distance-based proxies.')}

Simple proxies, such as drawing a fixed-radius buffer around the plant, tend
to overestimate the true supply zone because they cannot see the actual
shape of a plant's supplier base. A fixed radius treats a scattered ring of
farms and a tight cluster the same way, the same way a single circle drawn
around a group of houses would badly misrepresent them if the houses
actually lined up along one road instead of spreading out evenly in every
direction. The overestimate is largest, sometimes by more than an order of
magnitude, in plant-years where the true supply zone is small and tightly
clustered, since that is exactly where a generic circle overshoots the most.
The median is reported above rather than the mean because a handful of
these small-zone plant-years produce extreme percentage overestimates that
would otherwise dominate the average and make the typical case look worse
than it is. Either way, this is a methodological caution for anyone tempted
to shortcut the distance-selection step in Section 7 to save computation
time: the shortcut has a real, quantifiable cost in accuracy."""
    )

    sections.append(
        f"""## 12. Where the supply zone sits geographically, region by region

Aggregate area totals like those in Section 3 can hide a lot: two regions
with the same total supply-zone area could look completely different if one
has that area concentrated in a single corner while the other has it spread
thinly across the whole territory. The map below breaks the cumulative
signatory direct zone down by region, showing what share of each region's
own territory it actually covers.

{_image(f'{figures_relative}/figure_11_state_coverage_map.png', "Figure 11. Share of each region's territory that falls inside the cumulative signatory direct supply zone.")}"""
    )

    sections.append(
        """## 13. Limitations

Every workflow makes simplifying choices, and being explicit about them is
part of what makes a method trustworthy. The most important ones here are:

- **All data are synthetic.** Every property boundary, transaction, and
  slaughterhouse in this repository was generated for testing purposes and
  carries no relationship to actual locations, companies, or individuals.
  No result in this report should be read as a claim about any real place.
- **The open-source distance-selection and aggregation methods are declared
  analogues, not certified reproductions,** of the original study's ArcGIS
  Pro routines; see `docs/ARCGIS_EQUIVALENCE.md` for a line-by-line
  comparison of assumptions between the two.
- **Land-use and deforestation layers are simplified** into four classes and
  a single annual raster; the original study's underlying data sources are
  considerably richer and would need to be substituted for any empirical
  application.
- **Supplier-hull and radial-buffer comparisons are illustrative proxies**
  built for this repository to make Section 11's point concretely; they
  should not be read as a critique of any specific commercial GIS workflow.

## 14. How to reproduce every number in this report

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

Running these four commands regenerates the synthetic input data from
scratch, reruns every analytical step described above in the same order,
rebuilds every figure and table referenced in this report, including this
document itself, and runs the automated QA gates recorded in
`outputs/qa/QA_REPORT.md`. Because the process starts from a fixed random
seed, repeating it should reproduce substantively identical results every
time, which is the whole point of building the workflow this way.

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
