from __future__ import annotations

from itertools import combinations

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask, rasterize
from shapely.ops import unary_union

from supply_zones.config import ensure_directories


def _union(frame: gpd.GeoDataFrame):
    return unary_union(frame.geometry) if not frame.empty else None


def _area_ha(geometry) -> float:
    return 0.0 if geometry is None or geometry.is_empty else geometry.area / 10_000


def _write_or_append(gdf: gpd.GeoDataFrame, path, layer: str) -> None:
    mode = "a" if path.exists() else "w"
    gdf.to_file(path, layer=layer, driver="GPKG", mode=mode)


def build_cumulative_zones(cfg: dict, zones: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    paths = ensure_directories(cfg)
    rows = []
    for zone_type, group in zones.groupby("zone_type"):
        rows.append(
            {
                "zone_type": zone_type,
                "year": 0,
                "temporal_scope": "2013_2018_union",
                "geometry": _union(group),
            }
        )
        for year, annual in group.groupby("year"):
            rows.append(
                {
                    "zone_type": zone_type,
                    "year": int(year),
                    "temporal_scope": "annual_union",
                    "geometry": _union(annual),
                }
            )
    cumulative = gpd.GeoDataFrame(rows, geometry="geometry", crs=zones.crs)
    cumulative["area_ha"] = cumulative.area / 10_000
    _write_or_append(cumulative, paths["spatial"] / "analysis_layers.gpkg", "cumulative_zones")
    return cumulative


def summarize_zone_areas(cfg: dict, zones: gpd.GeoDataFrame, cumulative: gpd.GeoDataFrame) -> None:
    paths = ensure_directories(cfg)
    summary = (
        zones.groupby(["zone_type", "state", "inspection_type", "supplier_type"])["area_ha"]
        .agg(["count", "mean", "median", "min", "max"])
        .reset_index()
    )
    summary.to_csv(paths["tables"] / "zone_area_summary.csv", index=False)
    cumulative.drop(columns="geometry").to_csv(
        paths["tables"] / "cumulative_zone_area.csv", index=False
    )

    all_period = cumulative[cumulative["temporal_scope"] == "2013_2018_union"].set_index(
        "zone_type"
    )
    overlap_rows = []
    for left, right in combinations(sorted(all_period.index), 2):
        a = all_period.loc[left].geometry
        b = all_period.loc[right].geometry
        intersection = _area_ha(a.intersection(b))
        union_area = _area_ha(a.union(b))
        overlap_rows.append(
            {
                "zone_type_a": left,
                "zone_type_b": right,
                "intersection_ha": intersection,
                "percent_of_a": 100 * intersection / _area_ha(a),
                "percent_of_b": 100 * intersection / _area_ha(b),
                "jaccard_percent": 100 * intersection / union_area,
            }
        )
    pd.DataFrame(overlap_rows).to_csv(paths["tables"] / "zone_overlap.csv", index=False)


def analyze_persistence(
    cfg: dict, cumulative: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, np.ndarray]:
    paths = ensure_directories(cfg)
    study = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="study_area")
    states = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
    annual = cumulative[
        (cumulative["zone_type"] == "CA_direct")
        & (cumulative["temporal_scope"] == "annual_union")
    ]
    minx, miny, maxx, maxy = study.total_bounds
    cell = cfg["synthetic"]["cell_size_m"]
    width = int(np.ceil((maxx - minx) / cell))
    height = int(np.ceil((maxy - miny) / cell))
    transform = rasterio.transform.from_origin(minx, maxy, cell, cell)
    count = np.zeros((height, width), dtype=np.uint8)
    for geometry in annual.geometry:
        count += rasterize(
            [(geometry, 1)],
            out_shape=count.shape,
            transform=transform,
            fill=0,
            all_touched=False,
            dtype="uint8",
        )
    study_mask = ~geometry_mask(
        study.geometry, out_shape=count.shape, transform=transform, invert=True
    )
    count[study_mask] = 255
    with rasterio.open(
        paths["spatial"] / "ca_direct_persistence.tif",
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype="uint8",
        crs=study.crs,
        transform=transform,
        nodata=255,
        compress="deflate",
    ) as dst:
        dst.write(count, 1)

    pixel_ha = cell * cell / 10_000
    rows = []
    for state_row in [None, *list(states.itertuples(index=False))]:
        if state_row is None:
            label = "ALL"
            valid = count != 255
        else:
            label = state_row.state
            valid = rasterize(
                [(state_row.geometry, 1)],
                out_shape=count.shape,
                transform=transform,
                fill=0,
                dtype="uint8",
            ).astype(bool)
        covered = valid & (count > 0) & (count != 255)
        denominator = covered.sum()
        for years_present in range(1, len(cfg["project"]["years"]) + 1):
            cells = valid & (count == years_present)
            rows.append(
                {
                    "state": label,
                    "years_present": years_present,
                    "area_ha": int(cells.sum()) * pixel_ha,
                    "percent_of_ever_covered": (
                        100 * cells.sum() / denominator if denominator else 0
                    ),
                }
            )
    persistence = pd.DataFrame(rows)
    persistence.to_csv(paths["tables"] / "ca_direct_persistence.csv", index=False)
    return persistence, count


def analyze_land_use(cfg: dict, cumulative: gpd.GeoDataFrame) -> pd.DataFrame:
    paths = ensure_directories(cfg)
    states = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="states")
    protected = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="protected_areas")
    military = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="military_areas")
    exclusions = unary_union(pd.concat([protected, military]).geometry)
    all_period = cumulative[cumulative["temporal_scope"] == "2013_2018_union"]
    class_names = {int(key): value for key, value in cfg["land_use"]["classes"].items()}
    rows = []
    with rasterio.open(paths["raw"] / "land_use_2018.tif") as src:
        land_use = src.read(1)
        pixel_ha = abs(src.transform.a * src.transform.e) / 10_000
        for state_row in [None, *list(states.itertuples(index=False))]:
            geography = unary_union(states.geometry) if state_row is None else state_row.geometry
            state_name = "ALL" if state_row is None else state_row.state
            geography_mask = rasterize(
                [(geography, 1)],
                out_shape=land_use.shape,
                transform=src.transform,
                fill=0,
                all_touched=False,
            ).astype(bool)
            unprotected = geography.difference(exclusions)
            unprotected_mask = rasterize(
                [(unprotected, 1)],
                out_shape=land_use.shape,
                transform=src.transform,
                fill=0,
                all_touched=False,
            ).astype(bool)
            for row in all_period.itertuples(index=False):
                zone = row.geometry.intersection(geography)
                if zone.is_empty:
                    zone_mask = np.zeros(land_use.shape, dtype=bool)
                else:
                    zone_mask = rasterize(
                        [(zone, 1)],
                        out_shape=land_use.shape,
                        transform=src.transform,
                        fill=0,
                        all_touched=False,
                    ).astype(bool)
                for class_code, class_name in class_names.items():
                    denominator_mask = geography_mask & (land_use == class_code)
                    if class_name == "natural_vegetation":
                        denominator_mask &= unprotected_mask
                        zone_class_mask = zone_mask & unprotected_mask & (land_use == class_code)
                    else:
                        zone_class_mask = zone_mask & (land_use == class_code)
                    total_cells = int(denominator_mask.sum())
                    zone_cells = int(zone_class_mask.sum())
                    rows.append(
                        {
                            "state": state_name,
                            "zone_type": row.zone_type,
                            "land_use": class_name,
                            "zone_area_ha": zone_cells * pixel_ha,
                            "study_area_ha": total_cells * pixel_ha,
                            "coverage_percent": (
                                100 * zone_cells / total_cells if total_cells else 0
                            ),
                            "natural_vegetation_excludes_protected_and_military": (
                                class_name == "natural_vegetation"
                            ),
                        }
                    )
    result = pd.DataFrame(rows)
    result.to_csv(paths["tables"] / "land_use_by_zone.csv", index=False)
    return result


def analyze_deforestation_carbon(cfg: dict, cumulative: gpd.GeoDataFrame) -> pd.DataFrame:
    paths = ensure_directories(cfg)
    deforestation = gpd.read_file(
        paths["raw"] / "synthetic_inputs.gpkg", layer="deforestation"
    )
    minimum = {
        "Amazon": cfg["deforestation"]["amazon_minimum_mapping_unit_ha"],
        "Cerrado": cfg["deforestation"]["cerrado_minimum_mapping_unit_ha"],
    }
    deforestation = deforestation[
        ~deforestation["biome"].isin(cfg["deforestation"]["exclude_biomes"])
    ].copy()
    deforestation = deforestation[
        deforestation.apply(
            lambda row: row["mapped_area_ha"] >= minimum.get(row["biome"], np.inf), axis=1
        )
    ]
    rows = []
    all_period = cumulative[cumulative["temporal_scope"] == "2013_2018_union"]
    with rasterio.open(paths["raw"] / "biomass_carbon_2018.tif") as biomass_src:
        biomass = biomass_src.read(1)
        valid_biomass = biomass != biomass_src.nodata
        for zone_row in all_period.itertuples(index=False):
            for def_row in deforestation.itertuples(index=False):
                clipped = def_row.geometry.intersection(zone_row.geometry)
                if clipped.is_empty:
                    continue
                clipped_ha = clipped.area / 10_000
                carbon_mask = rasterize(
                    [(clipped, 1)],
                    out_shape=biomass.shape,
                    transform=biomass_src.transform,
                    fill=0,
                    all_touched=True,
                    dtype="uint8",
                ).astype(bool)
                sampled = biomass[carbon_mask & valid_biomass]
                mean_carbon = (
                    float(sampled.mean()) if sampled.size else float(def_row.carbon_mg_c_ha)
                )
                emissions = (
                    clipped_ha
                    * mean_carbon
                    * cfg["deforestation"]["carbon_to_co2"]
                    / 1_000_000
                )
                rows.append(
                    {
                        "zone_type": zone_row.zone_type,
                        "year": int(def_row.year),
                        "period": def_row.period,
                        "biome": def_row.biome,
                        "deforestation_ha": clipped_ha,
                        "mean_biomass_carbon_mg_c_ha": mean_carbon,
                        "emissions_mtco2e": emissions,
                    }
                )
    detailed = pd.DataFrame(rows)
    summary = (
        detailed.groupby(["zone_type", "period", "year"], as_index=False)[
            ["deforestation_ha", "emissions_mtco2e"]
        ]
        .sum()
        .sort_values(["zone_type", "year"])
    )
    summary.to_csv(paths["tables"] / "deforestation_carbon_by_zone.csv", index=False)
    return summary


def analyze_distances(cfg: dict) -> pd.DataFrame:
    paths = ensure_directories(cfg)
    suppliers = gpd.read_file(paths["interim"] / "analytical_suppliers.gpkg", layer="suppliers")
    plants = gpd.read_file(
        paths["interim"] / "analytical_suppliers.gpkg", layer="eligible_slaughterhouses"
    )
    rows = []
    for (plant, year), group in suppliers.groupby(["slaughterhouse_id", "year"]):
        direct = group[group["supplier_type"] == "direct"]
        indirect = group[group["supplier_type"] == "tier1_indirect"]
        if direct.empty or indirect.empty:
            continue
        direct_points = direct.geometry.centroid
        for row in indirect.itertuples(index=False):
            distance = direct_points.distance(row.geometry.centroid).min() / 1000
            rows.append(
                {
                    "distance_type": "tier1_to_nearest_direct",
                    "slaughterhouse_id": plant,
                    "year": year,
                    "entity_id": row.gta_property_id,
                    "distance_km": distance,
                }
            )
    for state, state_plants in plants.groupby("state"):
        ca = state_plants[state_plants["ca_signatory"]]
        non_ca = state_plants[~state_plants["ca_signatory"]]
        for row in ca.itertuples(index=False):
            if non_ca.empty:
                continue
            distance = non_ca.geometry.distance(row.geometry).min() / 1000
            rows.append(
                {
                    "distance_type": "CA_to_nearest_non_CA_slaughterhouse",
                    "slaughterhouse_id": row.slaughterhouse_id,
                    "year": 0,
                    "entity_id": state,
                    "distance_km": distance,
                }
            )
    result = pd.DataFrame(rows)
    result.to_csv(paths["tables"] / "distance_analysis.csv", index=False)
    result.groupby("distance_type")["distance_km"].describe().to_csv(
        paths["tables"] / "distance_summary.csv"
    )
    return result


def analyze_supplier_flows_and_expansion(
    cfg: dict, suppliers: gpd.GeoDataFrame, cumulative: gpd.GeoDataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    paths = ensure_directories(cfg)
    tx = pd.read_csv(paths["raw"] / "gta_transactions.csv")
    plants = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="slaughterhouses")
    plant_ca = plants.set_index("slaughterhouse_id")["ca_signatory"].to_dict()
    all_period = cumulative[cumulative["temporal_scope"] == "2013_2018_union"].set_index(
        "zone_type"
    )
    baseline_zone = all_period.loc["CA_direct"].geometry
    scenarios = {
        "current_CA_direct": ["CA_direct"],
        "pathway_1_add_CA_tier1": ["CA_direct", "CA_tier1_indirect"],
        "pathway_2_add_non_CA_direct": ["CA_direct", "non_CA_direct"],
        "pathway_3_all_direct_and_tier1": list(all_period.index),
    }
    supplier_sets = {
        zone_type: set(suppliers.loc[suppliers["zone_type"] == zone_type, "gta_property_id"])
        for zone_type in all_period.index
    }
    linked = gpd.read_file(paths["interim"] / "linked_properties.gpkg")
    total_slaughter = tx.loc[tx["purpose"] == "slaughter", "heads"].sum()
    farm_moves = tx[tx["destination_type"] == "property"]
    total_received = farm_moves["heads"].sum()
    expansion_rows = []
    for scenario, zone_types in scenarios.items():
        scenario_zone = unary_union([all_period.loc[item].geometry for item in zone_types])
        ids = set().union(*(supplier_sets[item] for item in zone_types))
        properties = linked[linked["gta_property_id"].isin(ids)]
        property_area = _area_ha(unary_union(properties.geometry))
        slaughter_covered = tx[
            (tx["purpose"] == "slaughter")
            & tx["origin_gta_property_id"].isin(ids)
        ]["heads"].sum()
        received_covered = farm_moves[farm_moves["destination_id"].isin(ids)]["heads"].sum()
        expansion_rows.append(
            {
                "scenario": scenario,
                "zone_area_ha": _area_ha(scenario_zone),
                "zone_area_increase_percent": 100
                * (_area_ha(scenario_zone) - _area_ha(baseline_zone))
                / _area_ha(baseline_zone),
                "monitored_property_count": len(ids),
                "monitored_property_area_ha": property_area,
                "slaughter_volume_coverage_percent": 100
                * slaughter_covered
                / total_slaughter,
                "farm_movement_received_coverage_percent": 100
                * received_covered
                / total_received,
            }
        )
    expansion = pd.DataFrame(expansion_rows)
    expansion.to_csv(paths["tables"] / "expansion_pathways.csv", index=False)

    ca_direct_ids = supplier_sets["CA_direct"]
    outgoing = tx[tx["origin_gta_property_id"].isin(ca_direct_ids)].copy()
    outgoing["flow_category"] = outgoing.apply(
        lambda row: (
            "slaughter_CA"
            if row["purpose"] == "slaughter" and plant_ca.get(row["destination_id"], False)
            else (
                "slaughter_non_CA"
                if row["purpose"] == "slaughter"
                else "non_slaughter_property_movement"
            )
        ),
        axis=1,
    )
    flows = outgoing.groupby("flow_category", as_index=False)["heads"].sum()
    flows["percent"] = 100 * flows["heads"] / flows["heads"].sum()
    flows.to_csv(paths["tables"] / "ca_direct_supplier_flows.csv", index=False)
    return flows, expansion


def compare_alternative_zone_methods(cfg: dict, zones: gpd.GeoDataFrame) -> pd.DataFrame:
    paths = ensure_directories(cfg)
    suppliers = gpd.read_file(paths["interim"] / "analytical_suppliers.gpkg", layer="suppliers")
    plants = gpd.read_file(
        paths["interim"] / "analytical_suppliers.gpkg", layer="eligible_slaughterhouses"
    ).set_index("slaughterhouse_id")
    study = unary_union(
        gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="study_area").geometry
    )
    rows = []
    for zone in zones[zones["supplier_type"] == "direct"].itertuples(index=False):
        group = suppliers[
            (suppliers["slaughterhouse_id"] == zone.slaughterhouse_id)
            & (suppliers["year"] == zone.year)
            & (suppliers["supplier_type"] == "direct")
        ]
        plant_geometry = plants.loc[zone.slaughterhouse_id].geometry
        maximum_distance = group.geometry.centroid.distance(plant_geometry).max()
        radial = plant_geometry.buffer(maximum_distance).intersection(study)
        supplier_hull = unary_union(group.geometry).convex_hull.buffer(20_000).intersection(study)
        rows.append(
            {
                "slaughterhouse_id": zone.slaughterhouse_id,
                "year": zone.year,
                "paper_analogue_area_ha": zone.area_ha,
                "radial_buffer_area_ha": _area_ha(radial),
                "supplier_hull_proxy_area_ha": _area_ha(supplier_hull),
                "radial_overestimate_percent": 100
                * (_area_ha(radial) - zone.area_ha)
                / zone.area_ha,
                "note": "Supplier hull is a transparent proxy, not a reconstruction of the unpublished cost-distance parameters.",
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(paths["tables"] / "alternative_zone_methods.csv", index=False)
    return result


def characterize_all(cfg: dict, zones: gpd.GeoDataFrame) -> dict[str, object]:
    cumulative = build_cumulative_zones(cfg, zones)
    summarize_zone_areas(cfg, zones, cumulative)
    persistence, persistence_array = analyze_persistence(cfg, cumulative)
    land_use = analyze_land_use(cfg, cumulative)
    deforestation = analyze_deforestation_carbon(cfg, cumulative)
    distances = analyze_distances(cfg)
    suppliers = gpd.read_file(
        ensure_directories(cfg)["interim"] / "analytical_suppliers.gpkg", layer="suppliers"
    )
    flows, expansion = analyze_supplier_flows_and_expansion(cfg, suppliers, cumulative)
    alternatives = compare_alternative_zone_methods(cfg, zones)
    return {
        "cumulative": cumulative,
        "persistence": persistence,
        "persistence_array": persistence_array,
        "land_use": land_use,
        "deforestation": deforestation,
        "distances": distances,
        "flows": flows,
        "expansion": expansion,
        "alternatives": alternatives,
    }
