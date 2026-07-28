"""Publication-quality charts and maps that complete the analytical picture.

This module complements ``figures.py``. It does not repeat the six figures
already produced by the core pipeline; it adds the visual analyses a reader
needs to understand zone composition, the distance-selection procedure,
supplier flows, expansion scenarios, and methodological sensitivity, all
plotted with a consistent, colorblind-safe, editorial style (Economist/Nature
conventions: title-as-insight, minimal chartjunk, direct labeling over
legends where practical).
"""

from __future__ import annotations

import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-supply-zones")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from supply_zones.config import cumulative_scope_label, ensure_directories, year_range_label

ZONE_ORDER = ["CA_direct", "CA_tier1_indirect", "non_CA_direct", "non_CA_tier1_indirect"]
ZONE_LABELS = {
    "CA_direct": "Signatory direct",
    "CA_tier1_indirect": "Signatory tier-1 indirect",
    "non_CA_direct": "Non-signatory direct",
    "non_CA_tier1_indirect": "Non-signatory tier-1 indirect",
}
ZONE_COLORS = {
    "CA_direct": "#1B7837",
    "CA_tier1_indirect": "#7FBF7B",
    "non_CA_direct": "#B2182B",
    "non_CA_tier1_indirect": "#EF8A62",
}
LAND_USE_COLORS = {
    "natural_vegetation": "#2E6F40",
    "pasture": "#E8C25A",
    "soybean": "#C77A2F",
    "other": "#B0B0B0",
}
LAND_USE_LABELS = {
    "natural_vegetation": "Natural vegetation",
    "pasture": "Pasture",
    "soybean": "Soybean",
    "other": "Other",
}

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#555555",
        "axes.labelcolor": "#333333",
        "text.color": "#222222",
        "xtick.color": "#333333",
        "ytick.color": "#333333",
        "figure.dpi": 220,
    }
)


def _finish(fig, path) -> None:
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _footer(ax, text: str = "Illustrative synthetic data. No confidential GTA, CAR, or slaughterhouse records are used.") -> None:
    ax.annotate(
        text,
        xy=(0, -0.14),
        xycoords="axes fraction",
        fontsize=7.5,
        color="#777777",
        ha="left",
    )


def _short_label(name: str) -> str:
    """Shorten a place name (e.g. 'Rondônia, Brazil') to its first segment for compact map labels."""
    return name.split(",")[0].strip()


def chart_landuse_composition(cfg: dict, land_use: pd.DataFrame) -> None:
    """Stacked bar chart of land-cover composition inside each zone type."""
    paths = ensure_directories(cfg)
    data = land_use[land_use["state"] == "ALL"].copy()
    order = ["natural_vegetation", "pasture", "soybean", "other"]
    pivot = data.pivot(index="zone_type", columns="land_use", values="coverage_percent").reindex(
        ZONE_ORDER
    )[order]

    fig, ax = plt.subplots(figsize=(9, 5))
    left = np.zeros(len(pivot))
    for land_use_class in order:
        values = pivot[land_use_class].to_numpy()
        ax.barh(
            [ZONE_LABELS[z] for z in pivot.index],
            values,
            left=left,
            color=LAND_USE_COLORS[land_use_class],
            label=LAND_USE_LABELS[land_use_class],
            height=0.62,
        )
        for y_position, (value, offset) in enumerate(zip(values, left)):
            if value >= 3:
                ax.text(
                    offset + value / 2,
                    y_position,
                    f"{value:.0f}%",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white" if land_use_class != "pasture" else "#3A2E00",
                    weight="bold",
                )
        left += values

    ax.set_xlim(0, max(left.max() * 1.02, 100))
    ax.set_xlabel("Share of zone area covered by each land-cover class (%)")
    ax.set_title(
        "Figure 4. Natural vegetation covers about a quarter of signatory direct\n"
        "supply zones, roughly the same share as in non-signatory zones",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=4,
        frameon=False,
        fontsize=9,
    )
    _footer(ax, "Illustrative synthetic data. Coverage is computed against the full study area, not only the mapped zone.")
    _finish(fig, paths["figures"] / "figure_4_land_use_composition.png")


def chart_moran_correlogram(cfg: dict, incremental_moran: pd.DataFrame) -> None:
    """Correlogram showing how the peak-Moran's-I distance is selected."""
    paths = ensure_directories(cfg)
    direct = incremental_moran[incremental_moran["supplier_type"] == "direct"].copy()
    counts = direct.groupby("slaughterhouse_id")["year"].nunique()
    example_plants = counts.sort_values(ascending=False).index[:4]

    fig, axes = plt.subplots(1, len(example_plants), figsize=(4.4 * len(example_plants), 4.2), sharey=True)
    if len(example_plants) == 1:
        axes = [axes]
    for ax, plant in zip(axes, example_plants):
        subset = direct[direct["slaughterhouse_id"] == plant]
        for year, group in subset.groupby("year"):
            group = group.sort_values("distance_km")
            ax.plot(group["distance_km"], group["moran_i"], color="#6096BA", alpha=0.5, linewidth=1.2)
            peak = group.loc[group["selected"]]
            if not peak.empty:
                ax.scatter(peak["distance_km"], peak["moran_i"], color="#B2182B", s=26, zorder=5)
        ax.set_title(plant, fontsize=10)
        ax.set_xlabel("Distance band (km)")
        ax.axhline(0, color="#AAAAAA", linewidth=0.8)
    axes[0].set_ylabel("Global Moran's I (cattle-volume weighted)")
    fig.suptitle(
        "Figure 5. Each supply zone's radius is chosen at its own peak of spatial autocorrelation,\n"
        "not from a single fixed distance",
        x=0.01,
        ha="left",
        fontsize=12,
        weight="bold",
    )
    legend_elements = [
        Line2D([0], [0], color="#6096BA", label="Annual correlogram"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#B2182B", markersize=7, label="Selected distance (peak I)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center", ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.12))
    fig.text(
        0.01, -0.2,
        "Illustrative synthetic data. Four slaughterhouses with the most complete annual series are shown.",
        fontsize=7.5, color="#777777", ha="left",
    )
    fig.tight_layout(rect=[0, 0.05, 1, 0.92])
    _finish(fig, paths["figures"] / "figure_5_moran_correlogram.png")


def chart_expansion_pathways(cfg: dict, expansion: pd.DataFrame) -> None:
    """Grouped bars comparing monitoring coverage under expansion scenarios."""
    paths = ensure_directories(cfg)
    labels = {
        "current_CA_direct": "Current\n(CA direct only)",
        "pathway_1_add_CA_tier1": "+ Signatory tier-1\nindirect",
        "pathway_2_add_non_CA_direct": "+ Non-signatory\ndirect",
        "pathway_3_all_direct_and_tier1": "All direct\n+ tier-1",
    }
    data = expansion.set_index("scenario").loc[list(labels)]

    fig, ax = plt.subplots(figsize=(9.5, 5))
    x = np.arange(len(data))
    width = 0.38
    bars_area = ax.bar(
        x - width / 2,
        data["zone_area_ha"] / 1_000_000,
        width,
        color="#2166AC",
        label="Monitored zone area (million ha)",
    )
    ax2 = ax.twinx()
    bars_volume = ax2.bar(
        x + width / 2,
        data["slaughter_volume_coverage_percent"],
        width,
        color="#EF8A62",
        label="Slaughter volume covered (%)",
    )
    ax2.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels([labels[item] for item in data.index], fontsize=9)
    ax.set_ylabel("Monitored zone area (million ha)", color="#2166AC")
    ax2.set_ylabel("Slaughter volume covered (%)", color="#B2451F")
    ax.set_title(
        "Figure 6. Extending monitoring to non-signatory direct suppliers would roughly\n"
        "triple the covered slaughter volume, at the cost of a much larger footprint",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    for bar in bars_area:
        ax.annotate(f"{bar.get_height():.1f}", (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom", fontsize=8, color="#2166AC")
    for bar in bars_volume:
        ax2.annotate(f"{bar.get_height():.0f}%", (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom", fontsize=8, color="#B2451F")
    _footer(ax)
    _finish(fig, paths["figures"] / "figure_6_expansion_pathways.png")


def chart_supplier_flows(cfg: dict, flows: pd.DataFrame) -> None:
    """Horizontal bar chart of where cattle leaving CA-linked direct properties go."""
    paths = ensure_directories(cfg)
    labels = {
        "slaughter_CA": "Slaughtered at a\nsignatory plant",
        "slaughter_non_CA": "Slaughtered at a\nnon-signatory plant",
        "non_slaughter_property_movement": "Moved to another\nproperty (not slaughtered)",
    }
    colors = {
        "slaughter_CA": "#1B7837",
        "slaughter_non_CA": "#B2182B",
        "non_slaughter_property_movement": "#999999",
    }
    data = flows.set_index("flow_category").loc[list(labels)].sort_values("percent")

    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    bars = ax.barh(
        [labels[item] for item in data.index],
        data["percent"],
        color=[colors[item] for item in data.index],
        height=0.55,
    )
    for bar, value in zip(bars, data["percent"]):
        ax.text(value + 1, bar.get_y() + bar.get_height() / 2, f"{value:.0f}%", va="center", fontsize=10)
    ax.set_xlim(0, max(data["percent"]) * 1.2)
    ax.set_xlabel("Share of cattle heads leaving signatory direct properties (%)")
    ax.set_title(
        "Figure 7. Under half of the cattle leaving signatory direct properties are\n"
        "slaughtered at a signatory plant; the rest exit through other channels",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    _footer(ax)
    _finish(fig, paths["figures"] / "figure_7_supplier_flows.png")


def chart_distance_distribution(cfg: dict, distances: pd.DataFrame) -> None:
    """Distribution of the two distance analyses, side by side."""
    paths = ensure_directories(cfg)
    labels = {
        "tier1_to_nearest_direct": "Tier-1 indirect supplier\nto nearest direct supplier",
        "CA_to_nearest_non_CA_slaughterhouse": "Signatory plant to\nnearest non-signatory plant",
    }
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    groups = [distances.loc[distances["distance_type"] == key, "distance_km"] for key in labels]
    violins = ax.violinplot(groups, showmedians=True, widths=0.7)
    for body, color in zip(violins["bodies"], ["#6096BA", "#B2451F"]):
        body.set_facecolor(color)
        body.set_alpha(0.55)
        body.set_edgecolor("none")
    for part in ("cbars", "cmins", "cmaxes", "cmedians"):
        violins[part].set_color("#333333")
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(list(labels.values()), fontsize=9.5)
    ax.set_ylabel("Distance (km)")
    ax.set_title(
        "Figure 8. Indirect suppliers typically sit within about 35-55 km of a direct\n"
        "supplier, while signatory and non-signatory plants are more widely separated",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    _footer(ax)
    _finish(fig, paths["figures"] / "figure_8_distance_distribution.png")


def chart_alternative_methods(cfg: dict, alternatives: pd.DataFrame) -> None:
    """Scatter comparing the paper-analogue method against simpler proxies."""
    paths = ensure_directories(cfg)
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    max_area = alternatives[["paper_analogue_area_ha", "radial_buffer_area_ha", "supplier_hull_proxy_area_ha"]].to_numpy().max() / 1_000_000
    ax.plot([0, max_area], [0, max_area], color="#999999", linestyle="--", linewidth=1, label="1:1 line")
    ax.scatter(
        alternatives["paper_analogue_area_ha"] / 1_000_000,
        alternatives["radial_buffer_area_ha"] / 1_000_000,
        color="#B2182B",
        alpha=0.6,
        s=28,
        label="Simple radial buffer",
    )
    ax.scatter(
        alternatives["paper_analogue_area_ha"] / 1_000_000,
        alternatives["supplier_hull_proxy_area_ha"] / 1_000_000,
        color="#2166AC",
        alpha=0.6,
        s=28,
        label="Supplier convex-hull proxy",
    )
    ax.set_xlabel("Zone area, incremental-autocorrelation method (million ha)")
    ax.set_ylabel("Zone area, alternative method (million ha)")
    ax.set_title(
        "Figure 9. Simpler distance-based proxies systematically overestimate zone\n"
        "area relative to the incremental spatial-autocorrelation method",
        loc="left",
        fontsize=12,
        weight="bold",
    )
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    _footer(ax, "Illustrative synthetic data. The supplier-hull proxy is a transparent stand-in, not a reconstruction of unpublished ArcGIS parameters.")
    _finish(fig, paths["figures"] / "figure_9_alternative_methods.png")


def chart_zone_overlap_heatmap(cfg: dict, overlap: pd.DataFrame) -> None:
    """Symmetric heatmap of pairwise zone-overlap (Jaccard) percentages."""
    paths = ensure_directories(cfg)
    matrix = pd.DataFrame(100.0, index=ZONE_ORDER, columns=ZONE_ORDER)
    for row in overlap.itertuples(index=False):
        matrix.loc[row.zone_type_a, row.zone_type_b] = row.jaccard_percent
        matrix.loc[row.zone_type_b, row.zone_type_a] = row.jaccard_percent

    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    image = ax.imshow(matrix.loc[ZONE_ORDER, ZONE_ORDER], cmap="YlGnBu", vmin=0, vmax=100)
    ax.set_xticks(range(len(ZONE_ORDER)))
    ax.set_yticks(range(len(ZONE_ORDER)))
    ax.set_xticklabels([ZONE_LABELS[z] for z in ZONE_ORDER], rotation=30, ha="right", fontsize=9)
    ax.set_yticklabels([ZONE_LABELS[z] for z in ZONE_ORDER], fontsize=9)
    for i in range(len(ZONE_ORDER)):
        for j in range(len(ZONE_ORDER)):
            value = matrix.loc[ZONE_ORDER[i], ZONE_ORDER[j]]
            ax.text(
                j, i, f"{value:.0f}%", ha="center", va="center",
                color="white" if value > 55 else "#222222", fontsize=9,
            )
    fig.colorbar(image, ax=ax, shrink=0.8, label="Spatial overlap (Jaccard, %)")
    ax.set_title("Figure 10. Pairwise spatial overlap between supply-zone types", loc="left", fontsize=12, weight="bold")
    _footer(ax)
    _finish(fig, paths["figures"] / "figure_10_zone_overlap_heatmap.png")


def map_state_coverage(cfg: dict, cumulative: gpd.GeoDataFrame) -> None:
    """Small-multiples choropleth-style map of CA-direct zone coverage by state."""
    paths = ensure_directories(cfg)
    states = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
    zone = cumulative[
        (cumulative["zone_type"] == "CA_direct")
        & (cumulative["temporal_scope"] == cumulative_scope_label(cfg))
    ]
    zone_geometry = zone.geometry.iloc[0]

    rows = []
    for row in states.itertuples(index=False):
        state_area = row.geometry.area / 10_000
        covered_area = row.geometry.intersection(zone_geometry).area / 10_000
        rows.append({"state": row.state, "coverage_percent": 100 * covered_area / state_area})
    coverage = pd.DataFrame(rows).set_index("state")["coverage_percent"]
    states = states.assign(coverage_percent=states["state"].map(coverage))

    fig, ax = plt.subplots(figsize=(7.5, 7))
    states.plot(
        ax=ax, column="coverage_percent", cmap="YlGn", edgecolor="#333333", linewidth=1,
        legend=True, legend_kwds={"label": "Share of regional area inside the signatory direct zone (%)", "shrink": 0.7},
        vmin=0, vmax=max(60, coverage.max() * 1.1),
    )
    for row in states.itertuples(index=False):
        point = row.geometry.representative_point()
        label = _short_label(getattr(row, "state_name", None) or row.state)
        ax.text(
            point.x, point.y, f"{label}\n{row.coverage_percent:.0f}%",
            ha="center", va="center", fontsize=10, weight="bold", color="#1A1A1A",
        )
    ax.set_axis_off()
    ax.set_title(
        f"Figure 11. Share of each region's territory falling inside the cumulative\n"
        f"signatory direct supply zone, {year_range_label(cfg)}",
        loc="left", fontsize=12, weight="bold",
    )
    _footer(ax)
    _finish(fig, paths["figures"] / "figure_11_state_coverage_map.png")


def create_report_charts(cfg: dict, results: dict) -> None:
    paths = ensure_directories(cfg)
    chart_landuse_composition(cfg, results["land_use"])
    incremental_moran = pd.read_csv(paths["tables"] / "incremental_moran.csv")
    chart_moran_correlogram(cfg, incremental_moran)
    chart_expansion_pathways(cfg, results["expansion"])
    chart_supplier_flows(cfg, results["flows"])
    chart_distance_distribution(cfg, results["distances"])
    chart_alternative_methods(cfg, results["alternatives"])
    zone_overlap = pd.read_csv(paths["tables"] / "zone_overlap.csv")
    chart_zone_overlap_heatmap(cfg, zone_overlap)
    map_state_coverage(cfg, results["cumulative"])
