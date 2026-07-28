from __future__ import annotations

import os

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-supply-zones")

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Patch

from supply_zones.config import cumulative_scope_label, ensure_directories
from supply_zones.mapping import add_basemap_if_available
from supply_zones.report_charts import ZONE_LABELS


COLORS = {
    "CA_direct": "#1B7837",
    "CA_tier1_indirect": "#7FBF7B",
    "non_CA_direct": "#B2182B",
    "non_CA_tier1_indirect": "#EF8A62",
}


def _finish(fig, path) -> None:
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def figure_study_area(cfg: dict) -> None:
    paths = ensure_directories(cfg)
    gpkg = paths["raw"] / "synthetic_inputs.gpkg"
    states = gpd.read_file(gpkg, layer="states")
    plants = gpd.read_file(gpkg, layer="slaughterhouses")
    linked = gpd.read_file(paths["interim"] / "linked_properties.gpkg")
    fig, ax = plt.subplots(figsize=(8, 7))
    states.plot(ax=ax, color="#F3EFE5", edgecolor="#4D4D4D", linewidth=1, alpha=0.75)
    linked.plot(ax=ax, color="#6096BA", alpha=0.55, linewidth=0)
    plants[~plants["ca_signatory"]].plot(
        ax=ax, color="#B2182B", marker="^", markersize=45, label="Non-signatory slaughterhouse"
    )
    plants[plants["ca_signatory"]].plot(
        ax=ax, color="#1B7837", marker="^", markersize=45, label="Signatory slaughterhouse"
    )
    for row in states.itertuples(index=False):
        point = row.geometry.representative_point()
        full_label = getattr(row, "state_name", None) or row.state
        label = full_label.split(",")[0].strip()
        ax.text(point.x, point.y, label, weight="bold", ha="center", fontsize=10)
    add_basemap_if_available(ax, states.crs, paths)
    ax.set_axis_off()
    ax.legend(frameon=False, loc="center left", bbox_to_anchor=(1.02, 0.5))
    _finish(fig, paths["figures"] / "figure_1_study_area.png")


def figure_zone_overlap(cfg: dict, cumulative: gpd.GeoDataFrame) -> None:
    paths = ensure_directories(cfg)
    study = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
    all_period = cumulative[cumulative["temporal_scope"] == cumulative_scope_label(cfg)]
    fig, ax = plt.subplots(figsize=(8, 7))
    study.plot(ax=ax, color="#F7F7F7", edgecolor="#666666", linewidth=0.8, alpha=0.35)
    for zone_type in [
        "non_CA_tier1_indirect",
        "CA_tier1_indirect",
        "non_CA_direct",
        "CA_direct",
    ]:
        frame = all_period[all_period["zone_type"] == zone_type]
        frame.plot(ax=ax, color=COLORS[zone_type], alpha=0.5, edgecolor="none")
    ax.legend(
        handles=[Patch(facecolor=color, alpha=0.6, label=ZONE_LABELS[key]) for key, color in COLORS.items()],
        frameon=False,
        loc="center left",
        bbox_to_anchor=(1.02, 0.5),
    )
    add_basemap_if_available(ax, study.crs, paths)
    ax.set_axis_off()
    _finish(fig, paths["figures"] / "figure_2_zone_overlap.png")


def figure_persistence(cfg: dict) -> None:
    paths = ensure_directories(cfg)
    states = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
    raster_path = paths["spatial"] / "ca_direct_persistence.tif"
    fig, ax = plt.subplots(figsize=(8, 7))
    with rasterio.open(raster_path) as src:
        data = src.read(1, masked=True)
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
    cmap = ListedColormap(["#FEE8C8", "#FDBB84", "#FC8D59", "#EF6548", "#D7301F", "#7F0000"])
    norm = BoundaryNorm(np.arange(0.5, 7.5, 1), cmap.N)
    image = ax.imshow(data, extent=extent, origin="upper", cmap=cmap, norm=norm, alpha=0.85)
    states.boundary.plot(ax=ax, color="#333333", linewidth=0.8)
    add_basemap_if_available(ax, states.crs, paths)
    colorbar = fig.colorbar(image, ax=ax, shrink=0.72, ticks=range(1, 7))
    colorbar.set_label("Number of years covered")
    ax.set_axis_off()
    _finish(fig, paths["figures"] / "figure_3_persistence.png")


def figure_zone_boxplots(cfg: dict, zones: gpd.GeoDataFrame) -> None:
    paths = ensure_directories(cfg)
    order = list(COLORS)
    data = [zones.loc[zones["zone_type"] == item, "area_ha"] / 1_000_000 for item in order]
    fig, ax = plt.subplots(figsize=(9, 5))
    boxes = ax.boxplot(data, tick_labels=[item.replace("_", " ") for item in order], patch_artist=True)
    for box_artist, zone_type in zip(boxes["boxes"], order):
        box_artist.set_facecolor(COLORS[zone_type])
        box_artist.set_alpha(0.7)
    ax.set_ylabel("Zone area (million ha)")
    ax.tick_params(axis="x", rotation=20)
    ax.grid(axis="y", alpha=0.25)
    _finish(fig, paths["figures"] / "figure_s1_zone_area_boxplots.png")


def figure_deforestation_carbon(cfg: dict, deforestation: pd.DataFrame) -> None:
    paths = ensure_directories(cfg)
    annual = deforestation[
        (deforestation["period"] == "annual_2008_2018")
        & (deforestation["zone_type"] == "CA_direct")
    ].copy()
    annual = (
        annual.set_index("year")[["deforestation_ha", "emissions_mtco2e"]]
        .reindex(range(2008, 2019), fill_value=0)
        .reset_index()
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(annual["year"], annual["deforestation_ha"] / 1_000, marker="o", color="#B2182B")
    axes[0].set_ylabel("Deforestation (thousand ha)")
    axes[1].plot(annual["year"], annual["emissions_mtco2e"], marker="o", color="#2166AC")
    axes[1].set_ylabel("Committed emissions (MtCO₂e)")
    for ax in axes:
        ax.set_xlabel("Year")
        ax.grid(alpha=0.25)
    _finish(fig, paths["figures"] / "figure_s2_deforestation_carbon.png")


def figure_single_zone(cfg: dict, zones: gpd.GeoDataFrame) -> None:
    paths = ensure_directories(cfg)
    direct = zones[zones["supplier_type"] == "direct"].sort_values(
        ["supplier_count", "year"], ascending=False
    )
    example = direct.iloc[0]
    suppliers = gpd.read_file(paths["interim"] / "analytical_suppliers.gpkg", layer="suppliers")
    group = suppliers[
        (suppliers["slaughterhouse_id"] == example["slaughterhouse_id"])
        & (suppliers["year"] == example["year"])
        & (suppliers["supplier_type"] == "direct")
    ]
    fig, ax = plt.subplots(figsize=(7, 6))
    gpd.GeoSeries([example.geometry], crs=zones.crs).plot(
        ax=ax, color="#D9F0D3", edgecolor="#1B7837", linewidth=1.5, alpha=0.65
    )
    group.plot(
        ax=ax,
        column="cattle_heads",
        cmap="Blues",
        edgecolor="white",
        linewidth=0.3,
        legend=True,
        legend_kwds={"label": "Cattle heads"},
    )
    add_basemap_if_available(ax, zones.crs, paths)
    ax.set_axis_off()
    _finish(fig, paths["figures"] / "figure_s3_example_zone.png")


def create_all_figures(cfg: dict, zones: gpd.GeoDataFrame, results: dict) -> None:
    figure_study_area(cfg)
    figure_zone_overlap(cfg, results["cumulative"])
    figure_persistence(cfg)
    figure_zone_boxplots(cfg, zones)
    figure_deforestation_carbon(cfg, results["deforestation"])
    figure_single_zone(cfg, zones)
