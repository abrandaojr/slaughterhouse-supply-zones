from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist
from shapely.geometry import MultiPolygon
from shapely.ops import unary_union

from supply_zones.config import ensure_directories


@dataclass(frozen=True)
class MoranResult:
    distance_km: float
    moran_i: float
    z_score: float
    p_value: float
    connected_share: float


def global_moran(values: np.ndarray, weights: np.ndarray) -> float:
    """Calculate Global Moran's I for a supplied spatial-weights matrix."""
    x = np.asarray(values, dtype=float)
    w = np.asarray(weights, dtype=float).copy()
    np.fill_diagonal(w, 0)
    row_sums = w.sum(axis=1)
    nonzero = row_sums > 0
    w[nonzero] = w[nonzero] / row_sums[nonzero, None]
    centered = x - x.mean()
    denominator = np.square(centered).sum()
    weight_sum = w.sum()
    if denominator == 0 or weight_sum == 0:
        return float("nan")
    return float((len(x) / weight_sum) * (w * np.outer(centered, centered)).sum() / denominator)


def incremental_spatial_autocorrelation(
    coordinates_m: np.ndarray,
    values: np.ndarray,
    distances_km: list[float],
    permutations: int,
    seed: int,
) -> tuple[list[MoranResult], float]:
    """Find the distance with the largest deterministic permutation z-score."""
    coordinates_m = np.asarray(coordinates_m, dtype=float)
    values = np.asarray(values, dtype=float)
    distances = cdist(coordinates_m, coordinates_m)
    rng = np.random.default_rng(seed)
    results: list[MoranResult] = []
    for distance_km in distances_km:
        weights = ((distances > 0) & (distances <= distance_km * 1000)).astype(float)
        connected_share = float((weights.sum(axis=1) > 0).mean())
        observed = global_moran(values, weights)
        if np.isnan(observed):
            results.append(MoranResult(distance_km, np.nan, np.nan, np.nan, connected_share))
            continue
        permuted = np.array(
            [global_moran(rng.permutation(values), weights) for _ in range(permutations)]
        )
        permuted = permuted[np.isfinite(permuted)]
        std = permuted.std(ddof=1) if len(permuted) > 1 else 0
        z = (observed - permuted.mean()) / std if std > 0 else 0.0
        p = (1 + np.count_nonzero(np.abs(permuted) >= abs(observed))) / (
            len(permuted) + 1
        )
        results.append(MoranResult(distance_km, observed, float(z), float(p), connected_share))

    usable = [result for result in results if np.isfinite(result.z_score) and result.connected_share >= 0.5]
    if not usable:
        usable = [result for result in results if np.isfinite(result.z_score)]
    selected = max(usable, key=lambda result: result.z_score).distance_km if usable else distances_km[0]
    return results, selected


def _parts(geometry):
    if geometry.geom_type == "Polygon":
        return [geometry]
    if geometry.geom_type == "MultiPolygon":
        return list(geometry.geoms)
    return [part for part in getattr(geometry, "geoms", []) if part.geom_type == "Polygon"]


def aggregate_supplier_polygons(
    suppliers: gpd.GeoDataFrame,
    aggregation_distance_m: float,
    volume_coverage: float,
    study_geometry,
    simplify_tolerance_m: float,
):
    """Open-source analogue of Aggregate Polygons.

    Buffering by half the aggregation distance joins polygons whose boundaries
    are separated by no more than that distance. A matching negative buffer
    restores an approximation of the original exterior boundary.
    """
    half = max(aggregation_distance_m / 2, 1)
    expanded = unary_union([geometry.buffer(half) for geometry in suppliers.geometry])
    contracted = expanded.buffer(-half)
    if contracted.is_empty:
        contracted = unary_union(suppliers.geometry)
    components = _parts(contracted)
    scored = []
    total = float(suppliers["cattle_heads"].sum())
    for component in components:
        contained = suppliers[
            suppliers.geometry.representative_point().apply(component.buffer(1).covers)
        ]
        scored.append((component, float(contained["cattle_heads"].sum())))
    scored.sort(key=lambda item: item[1], reverse=True)
    kept = []
    cumulative = 0.0
    for component, heads in scored:
        kept.append(component)
        cumulative += heads
        if total == 0 or cumulative / total >= volume_coverage:
            break
    zone = unary_union(kept).intersection(study_geometry)
    zone = zone.simplify(simplify_tolerance_m, preserve_topology=True)
    if zone.geom_type == "Polygon":
        return zone
    return MultiPolygon(_parts(zone))


def map_supply_zones(cfg: dict) -> gpd.GeoDataFrame:
    paths = ensure_directories(cfg)
    suppliers = gpd.read_file(paths["interim"] / "analytical_suppliers.gpkg", layer="suppliers")
    study = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="study_area")
    study_geometry = unary_union(study.geometry)
    ac = cfg["autocorrelation"]
    distances = list(
        np.arange(
            ac["minimum_distance_km"],
            ac["maximum_distance_km"] + ac["interval_km"],
            ac["interval_km"],
        )
    )
    isa_rows: list[dict] = []
    zone_rows: list[dict] = []
    grouped = suppliers.groupby(["slaughterhouse_id", "year", "supplier_type"], sort=True)
    for group_index, ((plant_id, year, supplier_type), group) in enumerate(grouped):
        group = group.copy()
        centroids = group.geometry.centroid
        coordinates = np.column_stack([centroids.x, centroids.y])
        if len(group) >= ac["minimum_suppliers"]:
            results, selected_km = incremental_spatial_autocorrelation(
                coordinates,
                group["cattle_heads"].to_numpy(),
                distances,
                ac["permutations"],
                cfg["project"]["seed"] + group_index,
            )
            method = "incremental_moran_peak"
            for result in results:
                isa_rows.append(
                    {
                        "slaughterhouse_id": plant_id,
                        "year": year,
                        "supplier_type": supplier_type,
                        **result.__dict__,
                        "selected": result.distance_km == selected_km,
                    }
                )
        else:
            if len(group) > 1:
                matrix = cdist(coordinates, coordinates)
                matrix[matrix == 0] = np.nan
                selected_km = float(np.nanmedian(np.nanmin(matrix, axis=1)) * 2 / 1000)
            else:
                selected_km = float(ac["minimum_distance_km"])
            selected_km = float(
                np.clip(
                    selected_km,
                    ac["minimum_distance_km"],
                    cfg["zones"]["maximum_aggregation_distance_km"],
                )
            )
            method = "sparse_group_nearest_neighbor_fallback"
            isa_rows.append(
                {
                    "slaughterhouse_id": plant_id,
                    "year": year,
                    "supplier_type": supplier_type,
                    "distance_km": selected_km,
                    "moran_i": np.nan,
                    "z_score": np.nan,
                    "p_value": np.nan,
                    "connected_share": np.nan,
                    "selected": True,
                }
            )
        selected_km = min(selected_km, cfg["zones"]["maximum_aggregation_distance_km"])
        zone = aggregate_supplier_polygons(
            group,
            selected_km * 1000,
            cfg["zones"]["cattle_volume_coverage"],
            study_geometry,
            cfg["zones"]["simplify_tolerance_m"],
        )
        first = group.iloc[0]
        zone_rows.append(
            {
                "slaughterhouse_id": plant_id,
                "year": int(year),
                "supplier_type": supplier_type,
                "zone_type": first["zone_type"],
                "ca_signatory": bool(first["ca_signatory"]),
                "inspection_type": first["inspection_type"],
                "state": first["state"],
                "supplier_count": int(len(group)),
                "cattle_heads": int(group["cattle_heads"].sum()),
                "aggregation_distance_km": selected_km,
                "distance_selection_method": method,
                "geometry": zone,
            }
        )

    zones = gpd.GeoDataFrame(zone_rows, geometry="geometry", crs=suppliers.crs)
    zones["area_ha"] = zones.area / 10_000
    zones.to_file(paths["spatial"] / "supply_zones.gpkg", layer="annual_zones", driver="GPKG")
    pd.DataFrame(isa_rows).to_csv(paths["tables"] / "incremental_moran.csv", index=False)
    return zones

