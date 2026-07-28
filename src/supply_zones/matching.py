from __future__ import annotations

import re
import unicodedata

import geopandas as gpd
import pandas as pd

from supply_zones.config import ensure_directories


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", text.upper()).strip()


def normalize_identifier(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize_text(value))


def _unique_index(frame: pd.DataFrame, columns: list[str]) -> dict[tuple, str]:
    grouped = frame.groupby(columns, dropna=False)["car_id"].agg(list)
    return {key if isinstance(key, tuple) else (key,): values[0] for key, values in grouped.items() if len(values) == 1}


def link_gta_to_car(cfg: dict) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Apply conservative, deterministic GTA–CAR linkage rules."""
    paths = ensure_directories(cfg)
    gpkg = paths["raw"] / "synthetic_inputs.gpkg"
    car = gpd.read_file(gpkg, layer="car_properties")
    gta = pd.read_csv(paths["raw"] / "gta_properties.csv", dtype=str)

    for frame in (car, gta):
        frame["n_owner_tax_id"] = frame["owner_tax_id"].map(normalize_identifier)
        frame["n_owner_name"] = frame["owner_name"].map(normalize_text)
        frame["n_property_name"] = frame["property_name"].map(normalize_text)
        frame["n_municipality"] = frame["municipality"].map(normalize_text)
        frame["n_state"] = frame["state"].map(normalize_text)

    rules = [
        (
            "R1_tax_property_municipality",
            ["n_state", "n_owner_tax_id", "n_property_name", "n_municipality"],
        ),
        ("R2_tax_municipality", ["n_state", "n_owner_tax_id", "n_municipality"]),
        (
            "R3_owner_property_municipality",
            ["n_state", "n_owner_name", "n_property_name", "n_municipality"],
        ),
    ]
    indices = [(name, columns, _unique_index(car, columns)) for name, columns in rules]
    match_rows = []
    for row in gta.itertuples(index=False):
        matched_car = None
        matched_rule = None
        for rule_name, columns, index in indices:
            key = tuple(getattr(row, column) for column in columns)
            candidate = index.get(key)
            if candidate is not None:
                matched_car = candidate
                matched_rule = rule_name
                break
        match_rows.append(
            {
                "gta_property_id": row.gta_property_id,
                "car_id": matched_car,
                "match_status": "matched" if matched_car else "unmatched_or_ambiguous",
                "match_rule": matched_rule or "",
            }
        )
    matches = pd.DataFrame(match_rows)
    linked = car.merge(matches[matches["car_id"].notna()], on="car_id", how="inner")
    linked = gpd.GeoDataFrame(linked, geometry="geometry", crs=car.crs)
    keep = [
        "gta_property_id",
        "car_id",
        "state",
        "owner_tax_id",
        "owner_name",
        "property_name",
        "municipality",
        "match_rule",
        "geometry",
    ]
    linked = linked[keep]
    linked.to_file(
        paths["interim"] / "linked_properties.gpkg",
        layer="linked_properties",
        driver="GPKG",
    )
    matches.to_csv(paths["interim"] / "record_linkage.csv", index=False)

    truth = pd.read_csv(paths["raw"] / "synthetic_linkage_truth.csv", dtype={"true_car_id": str})
    evaluated = matches.merge(truth, on="gta_property_id", how="left")
    evaluated["true_positive"] = (
        evaluated["car_id"].fillna("") == evaluated["true_car_id"].fillna("")
    ) & evaluated["expected_match"]
    evaluated["false_positive"] = evaluated["car_id"].notna() & ~evaluated["expected_match"]
    evaluated["false_negative"] = evaluated["car_id"].isna() & evaluated["expected_match"]
    evaluated.to_csv(paths["qa"] / "record_linkage_evaluation.csv", index=False)
    return linked, matches

