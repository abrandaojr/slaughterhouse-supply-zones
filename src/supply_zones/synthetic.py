from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box
from shapely.ops import unary_union

from supply_zones.config import ensure_directories
from supply_zones.osm import resolve_admin_units


def _ascii(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def _square(x: float, y: float, half_size: float):
    return box(x - half_size, y - half_size, x + half_size, y + half_size)


def _sample_point_in_polygon(rng, cx, cy, jitter, polygon, bounds, margin, max_tries=30):
    """Sample a point near (cx, cy) that is guaranteed to fall inside ``polygon``.

    Real administrative boundaries fetched from OpenStreetMap are frequently
    concave or irregular, unlike the old fixed rectangles, so a plain
    clip-to-bounding-box draw can land outside the actual shape. This retries
    with jitter and falls back to the polygon's own representative point,
    which is always inside it, so placement never fails regardless of the
    geometry's shape or origin (OpenStreetMap or the offline fallback).
    """
    minx, miny, maxx, maxy = bounds
    for _ in range(max_tries):
        x = float(np.clip(cx + rng.normal(0, jitter), minx + margin, maxx - margin))
        y = float(np.clip(cy + rng.normal(0, jitter), miny + margin, maxy - margin))
        if polygon.contains(Point(x, y)):
            return x, y
    anchor = polygon.representative_point()
    return anchor.x + rng.normal(0, jitter / 10), anchor.y + rng.normal(0, jitter / 10)


def _write_layer(gdf: gpd.GeoDataFrame, path: Path, layer: str, first: bool = False) -> None:
    mode = "w" if first else "a"
    gdf.to_file(path, layer=layer, driver="GPKG", mode=mode)


def _write_raster(
    path: Path,
    array: np.ndarray,
    bounds: tuple[float, float, float, float],
    cell_size: int,
    crs: str,
    dtype: str,
    nodata: float | int,
) -> None:
    minx, miny, maxx, maxy = bounds
    transform = from_origin(minx, maxy, cell_size, cell_size)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=array.shape[0],
        width=array.shape[1],
        count=1,
        crs=crs,
        transform=transform,
        dtype=dtype,
        nodata=nodata,
        compress="deflate",
    ) as dst:
        dst.write(array.astype(dtype), 1)


def generate_synthetic_data(cfg: dict) -> dict[str, Path]:
    """Create a complete fictitious input database with known linkage truth."""
    paths = ensure_directories(cfg)
    raw = paths["raw"]
    rng = np.random.default_rng(cfg["project"]["seed"])

    admin_units, crs = resolve_admin_units(cfg)
    cfg["project"]["crs"] = crs
    STATE_LAYOUT = {
        row.state: row.geometry.bounds for row in admin_units.itertuples(index=False)
    }
    ADMIN_POLYGON = {
        row.state: row.geometry for row in admin_units.itertuples(index=False)
    }
    years = cfg["project"]["years"]
    n_properties = cfg["synthetic"]["properties_per_state"]
    n_plants = cfg["synthetic"]["slaughterhouses_per_state"]

    states = admin_units[[col for col in ["state", "state_name", "geometry"] if col in admin_units.columns]].copy()
    if "state_name" not in states.columns:
        states["state_name"] = states["state"]
    study_geom = unary_union(states.geometry)
    study_area = gpd.GeoDataFrame(
        [{"study_id": "SYNTHETIC_STUDY_AREA", "geometry": study_geom}], crs=crs
    )

    # Biomes are intentionally simplified fictitious partitions, defined as
    # fractions of the overall study-area extent so the layout works for any
    # geography, not just the specific coordinates of one country's states.
    biome_labels = cfg["deforestation"].get("biome_labels", ["Amazon", "Cerrado", "Pantanal"])
    biome_fractions = cfg["deforestation"].get(
        "biome_extent_fractions",
        {
            "Amazon": (0.0, 0.33, 1.0, 1.0),
            "Cerrado": (0.18, 0.0, 1.0, 0.42),
            "Pantanal": (0.0, 0.0, 0.30, 0.21),
        },
    )
    study_minx, study_miny, study_maxx, study_maxy = study_geom.bounds
    study_width, study_height = study_maxx - study_minx, study_maxy - study_miny
    biomes = gpd.GeoDataFrame(
        [
            {
                "biome": label,
                "geometry": study_geom.intersection(
                    box(
                        study_minx + biome_fractions[label][0] * study_width,
                        study_miny + biome_fractions[label][1] * study_height,
                        study_minx + biome_fractions[label][2] * study_width,
                        study_miny + biome_fractions[label][3] * study_height,
                    )
                ),
            }
            for label in biome_labels
            if label in biome_fractions
        ],
        crs=crs,
    )
    biomes = biomes[~biomes.geometry.is_empty].reset_index(drop=True)

    plant_rows: list[dict] = []
    plant_centers: dict[str, list[tuple[float, float]]] = {}
    inspection_pattern = ["SIF", "SIF", "SIE", "OTH"]
    x_fractions = [0.28, 0.35, 0.65, 0.72]
    y_fractions = [0.40, 0.47, 0.40, 0.47]
    for state, bounds in STATE_LAYOUT.items():
        minx, miny, maxx, maxy = bounds
        centers = []
        for index in range(n_plants):
            # CA and non-CA plants occur in nearby pairs, creating the
            # competition and overlapping procurement geography examined in
            # the paper.
            raw_x = minx + x_fractions[index] * (maxx - minx)
            raw_y = miny + y_fractions[index] * (maxy - miny)
            x, y = _sample_point_in_polygon(
                rng, raw_x, raw_y, 12_000, ADMIN_POLYGON[state], bounds, margin=1_000
            )
            centers.append((x, y))
            plant_id = f"SH_{state}_{index + 1:02d}"
            inspection = inspection_pattern[index % len(inspection_pattern)]
            ca = (index + list(STATE_LAYOUT).index(state)) % 2 == 0
            plant_rows.append(
                {
                    "slaughterhouse_id": plant_id,
                    "synthetic_name": f"Fictitious Plant {state}-{index + 1}",
                    "state": state,
                    "inspection_type": inspection,
                    "inspection_code": f"{inspection}-{state}-{100 + index}",
                    "ca_signatory": ca,
                    "geometry": Point(x, y),
                }
            )
        plant_centers[state] = centers
    slaughterhouses = gpd.GeoDataFrame(plant_rows, crs=crs)

    car_rows: list[dict] = []
    gta_property_rows: list[dict] = []
    truth_rows: list[dict] = []
    unmatched_fraction = cfg["synthetic"]["unmatched_gta_fraction"]
    ambiguous_fraction = cfg["synthetic"]["deliberately_ambiguous_fraction"]

    for state, bounds in STATE_LAYOUT.items():
        minx, miny, maxx, maxy = bounds
        for index in range(n_properties):
            cluster = index % n_plants
            cx, cy = plant_centers[state][cluster]
            x, y = _sample_point_in_polygon(
                rng, cx, cy, 70_000, ADMIN_POLYGON[state], bounds, margin=8_000
            )
            half_size = float(rng.uniform(1_800, 5_500))
            car_id = f"CAR_{state}_{index + 1:04d}"
            gta_id = f"GTA_{state}_{index + 1:04d}"
            owner_number = 10_000_000 + list(STATE_LAYOUT).index(state) * 100_000 + index
            owner_name = f"Owner {state} {index + 1:04d}"
            property_name = f"Farm {state} {index + 1:04d}"
            municipality = f"{state}_M{1 + index % 6:02d}"
            car_rows.append(
                {
                    "car_id": car_id,
                    "state": state,
                    "owner_tax_id": str(owner_number),
                    "owner_name": owner_name,
                    "property_name": property_name,
                    "municipality": municipality,
                    "geometry": _square(x, y, half_size).intersection(ADMIN_POLYGON[state]),
                }
            )

            draw = rng.random()
            match_expected = draw >= unmatched_fraction
            ambiguous = match_expected and draw < unmatched_fraction + ambiguous_fraction
            gta_owner_id = str(owner_number)
            gta_owner_name = _ascii(owner_name).upper()
            gta_property_name = _ascii(property_name).upper()
            gta_municipality = municipality.upper()
            if not match_expected:
                gta_owner_id = f"UNRESOLVED-{state}-{index:04d}"
                gta_owner_name = f"UNKNOWN HOLDER {state} {index:04d}"
                gta_property_name = f"UNLISTED HOLDING {state} {index:04d}"
            gta_property_rows.append(
                {
                    "gta_property_id": gta_id,
                    "state": state,
                    "owner_tax_id": gta_owner_id,
                    "owner_name": gta_owner_name,
                    "property_name": gta_property_name,
                    "municipality": gta_municipality,
                }
            )
            truth_rows.append(
                {
                    "gta_property_id": gta_id,
                    "true_car_id": car_id if match_expected else "",
                    "expected_match": match_expected,
                    "deliberately_ambiguous": ambiguous,
                }
            )

    car = gpd.GeoDataFrame(car_rows, crs=crs)
    gta_properties = pd.DataFrame(gta_property_rows)
    truth = pd.DataFrame(truth_rows)

    # Add a small set of duplicated CAR identities to test ambiguity handling.
    ambiguous_ids = truth.loc[truth["deliberately_ambiguous"], "true_car_id"].tolist()
    if ambiguous_ids:
        duplicates = car[car["car_id"].isin(ambiguous_ids)].copy()
        duplicates["car_id"] = duplicates["car_id"] + "_DUP"
        duplicates["geometry"] = duplicates.geometry.translate(xoff=750, yoff=750)
        car = pd.concat([car, duplicates], ignore_index=True)
        car = gpd.GeoDataFrame(car, geometry="geometry", crs=crs)
        truth.loc[truth["deliberately_ambiguous"], "expected_match"] = False
        truth.loc[truth["deliberately_ambiguous"], "true_car_id"] = ""

    # GTA movements: slaughter movements identify direct suppliers; farm-to-farm
    # movements identify tier-1 suppliers in the same calendar year.
    transactions: list[dict] = []
    tx_counter = 1
    property_lookup = car[~car["car_id"].str.endswith("_DUP")].set_index("car_id")
    for year in years:
        for state in STATE_LAYOUT:
            state_properties = truth[
                truth["gta_property_id"].str.startswith(f"GTA_{state}_")
            ]["gta_property_id"].tolist()
            for gta_id in state_properties:
                idx = int(gta_id.rsplit("_", 1)[1]) - 1
                car_id = f"CAR_{state}_{idx + 1:04d}"
                centroid = property_lookup.loc[car_id].geometry.centroid
                plant_subset = slaughterhouses[slaughterhouses["state"] == state].copy()
                distances = plant_subset.geometry.distance(centroid).to_numpy()
                primary = plant_subset.iloc[int(np.argmin(distances))]

                # Most properties sell for slaughter; the rotating rule creates
                # stable yet non-identical annual supply zones.
                is_direct = (idx + year) % 5 != 0
                if is_direct:
                    distance_km = float(np.min(distances) / 1000)
                    heads = int(max(45, 245 - 0.65 * distance_km + rng.normal(0, 24)))
                    transactions.append(
                        {
                            "transaction_id": f"TX{tx_counter:08d}",
                            "year": year,
                            "origin_gta_property_id": gta_id,
                            "destination_type": "slaughterhouse",
                            "destination_id": primary["slaughterhouse_id"],
                            "purpose": "slaughter",
                            "heads": heads,
                        }
                    )
                    tx_counter += 1
                    if idx % 2 == 0:
                        second = plant_subset.iloc[int(np.argsort(distances)[1])]
                        transactions.append(
                            {
                                "transaction_id": f"TX{tx_counter:08d}",
                                "year": year,
                                "origin_gta_property_id": gta_id,
                                "destination_type": "slaughterhouse",
                                "destination_id": second["slaughterhouse_id"],
                                "purpose": "slaughter",
                                "heads": int(rng.integers(16, 60)),
                            }
                        )
                        tx_counter += 1

                # Send cattle to a nearby property that is likely a direct supplier.
                # Properties with the same modulo cluster are spatially close.
                candidate_offsets = [n_plants, 2 * n_plants, -n_plants, 3 * n_plants]
                dest_idx = next(
                    (
                        (idx + offset) % n_properties
                        for offset in candidate_offsets
                        if ((idx + offset) % n_properties + year) % 5 != 0
                    ),
                    (idx + 1) % n_properties,
                )
                destination_gta = f"GTA_{state}_{dest_idx + 1:04d}"
                transactions.append(
                    {
                        "transaction_id": f"TX{tx_counter:08d}",
                        "year": year,
                        "origin_gta_property_id": gta_id,
                        "destination_type": "property",
                        "destination_id": destination_gta,
                        "purpose": ["fattening", "breeding", "other"][idx % 3],
                        "heads": int(rng.integers(18, 125)),
                    }
                )
                tx_counter += 1
                if idx % 11 == 0:
                    transactions.append(
                        {
                            "transaction_id": f"TX{tx_counter:08d}",
                            "year": year,
                            "origin_gta_property_id": gta_id,
                            "destination_type": "property",
                            "destination_id": destination_gta,
                            "purpose": "other",
                            "heads": int(rng.integers(1, 15)),
                        }
                    )
                    tx_counter += 1
    gta = pd.DataFrame(transactions)

    codes = list(STATE_LAYOUT)
    protected = gpd.GeoDataFrame(
        [
            {
                "protected_id": f"PA_{state}",
                "type": "Conservation Unit" if state != codes[0] else "Indigenous Land",
                "geometry": box(
                    bounds[0] + 0.04 * (bounds[2] - bounds[0]),
                    bounds[1] + 0.68 * (bounds[3] - bounds[1]),
                    bounds[0] + 0.25 * (bounds[2] - bounds[0]),
                    bounds[1] + 0.94 * (bounds[3] - bounds[1]),
                ).intersection(ADMIN_POLYGON[state]),
            }
            for state, bounds in STATE_LAYOUT.items()
        ],
        crs=crs,
    )
    military = gpd.GeoDataFrame(
        [
            {
                "military_id": "MIL_SYNTH_01",
                "geometry": box(
                    study_minx + 0.79 * study_width,
                    study_miny + 0.77 * study_height,
                    study_minx + 0.88 * study_width,
                    study_miny + 0.87 * study_height,
                ).intersection(study_geom),
            }
        ],
        crs=crs,
    )

    deforestation_rows: list[dict] = []
    for index in range(130):
        state = codes[index % len(codes)]
        bounds = STATE_LAYOUT[state]
        x = rng.uniform(bounds[0] + 5_000, bounds[2] - 5_000)
        y = rng.uniform(bounds[1] + 5_000, bounds[3] - 5_000)
        year = 2007 if index % 4 == 0 else int(rng.integers(2008, 2019))
        radius = float(rng.uniform(300, 2_000))
        geom = Point(x, y).buffer(radius)
        biome_hit = biomes[biomes.geometry.intersects(Point(x, y))]
        biome = biome_hit.iloc[0]["biome"] if not biome_hit.empty else biome_labels[0]
        deforestation_rows.append(
            {
                "deforestation_id": f"DEF_{index + 1:04d}",
                "year": year,
                "period": "through_2007" if year <= 2007 else "annual_2008_2018",
                "biome": biome,
                "carbon_mg_c_ha": float(rng.uniform(45, 180)),
                "geometry": geom.intersection(study_geom),
            }
        )
    deforestation = gpd.GeoDataFrame(deforestation_rows, crs=crs)
    deforestation["mapped_area_ha"] = deforestation.area / 10_000

    gpkg = raw / "synthetic_inputs.gpkg"
    if gpkg.exists():
        gpkg.unlink()
    _write_layer(study_area, gpkg, "study_area", first=True)
    _write_layer(states, gpkg, "states")
    _write_layer(biomes, gpkg, "biomes")
    _write_layer(protected, gpkg, "protected_areas")
    _write_layer(military, gpkg, "military_areas")
    _write_layer(slaughterhouses, gpkg, "slaughterhouses")
    _write_layer(car, gpkg, "car_properties")
    _write_layer(deforestation, gpkg, "deforestation")

    gta.to_csv(raw / "gta_transactions.csv", index=False)
    gta_properties.to_csv(raw / "gta_properties.csv", index=False)
    truth.to_csv(raw / "synthetic_linkage_truth.csv", index=False)

    minx, miny, maxx, maxy = study_area.total_bounds
    cell = cfg["synthetic"]["cell_size_m"]
    width = int(np.ceil((maxx - minx) / cell))
    height = int(np.ceil((maxy - miny) / cell))
    yy, xx = np.indices((height, width))
    smooth = np.sin(xx / 8) + np.cos(yy / 11) + rng.normal(0, 0.35, (height, width))
    land_use = np.full((height, width), 4, dtype=np.uint8)
    land_use[smooth > 0.45] = 1
    land_use[(smooth <= 0.45) & (smooth > -0.55)] = 2
    land_use[(smooth <= -0.55) & (xx > width * 0.35)] = 3
    biomass = np.where(land_use == 1, 130 + 20 * smooth, 25 + 8 * smooth).clip(5, 220)

    from rasterio.features import geometry_mask

    outside = geometry_mask(
        [study_geom],
        out_shape=(height, width),
        transform=from_origin(minx, maxy, cell, cell),
        invert=False,
    )
    land_use[outside] = 0
    biomass[outside] = -9999
    _write_raster(raw / "land_use_2018.tif", land_use, (minx, miny, maxx, maxy), cell, crs, "uint8", 0)
    _write_raster(
        raw / "biomass_carbon_2018.tif",
        biomass,
        (minx, miny, maxx, maxy),
        cell,
        crs,
        "float32",
        -9999,
    )

    manifest_rows = []
    for file_path in sorted(raw.glob("*")):
        if file_path.is_file():
            digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
            manifest_rows.append(
                {
                    "file": file_path.name,
                    "source_type": "synthetic_authoritative_input",
                    "fictitious": True,
                    "sha256": digest,
                    "description": {
                        "synthetic_inputs.gpkg": "Vector study layers and synthetic entities.",
                        "gta_transactions.csv": "Fictitious cattle movements.",
                        "gta_properties.csv": "Fictitious GTA establishment attributes.",
                        "synthetic_linkage_truth.csv": "Known record-linkage truth for QA only.",
                        "land_use_2018.tif": "Fictitious categorical land-use raster.",
                        "biomass_carbon_2018.tif": "Fictitious biomass-carbon-density raster.",
                    }.get(file_path.name, "Synthetic input."),
                }
            )
    pd.DataFrame(manifest_rows).to_csv(raw / "source_manifest.csv", index=False)
    metadata = {
        "seed": cfg["project"]["seed"],
        "crs": crs,
        "years": years,
        "warning": "Every record, name, identifier, geometry, and value is fictitious.",
    }
    (raw / "SYNTHETIC_DATA_NOTICE.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    return {
        "gpkg": gpkg,
        "transactions": raw / "gta_transactions.csv",
        "gta_properties": raw / "gta_properties.csv",
        "land_use": raw / "land_use_2018.tif",
        "biomass": raw / "biomass_carbon_2018.tif",
    }
