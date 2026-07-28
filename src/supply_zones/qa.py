from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from supply_zones.config import ensure_directories


def _check(name: str, passed: bool, observed: object, expected: str) -> dict:
    return {
        "check": name,
        "status": "PASS" if bool(passed) else "FAIL",
        "observed": observed,
        "expected": expected,
    }


def run_qa(cfg: dict) -> pd.DataFrame:
    paths = ensure_directories(cfg)
    checks: list[dict] = []
    linked = gpd.read_file(paths["interim"] / "linked_properties.gpkg")
    suppliers = gpd.read_file(paths["interim"] / "analytical_suppliers.gpkg", layer="suppliers")
    zones = gpd.read_file(paths["spatial"] / "supply_zones.gpkg", layer="annual_zones")
    matches = pd.read_csv(paths["interim"] / "record_linkage.csv")
    truth = pd.read_csv(paths["raw"] / "synthetic_linkage_truth.csv")
    transactions = pd.read_csv(paths["raw"] / "gta_transactions.csv")
    linkage_eval = pd.read_csv(paths["qa"] / "record_linkage_evaluation.csv")

    checks.append(
        _check(
            "linked_property_key_unique",
            linked["gta_property_id"].is_unique,
            linked["gta_property_id"].nunique(),
            f"{len(linked)} unique GTA property identifiers",
        )
    )
    checks.append(
        _check(
            "linked_geometries_valid",
            linked.geometry.is_valid.all() and (~linked.geometry.is_empty).all(),
            int(linked.geometry.is_valid.sum()),
            f"{len(linked)} valid, non-empty geometries",
        )
    )
    checks.append(
        _check(
            "projected_equal_area_crs",
            linked.crs is not None and not linked.crs.is_geographic,
            str(linked.crs),
            f"projected CRS {cfg['project']['crs']}",
        )
    )
    match_rate = (matches["match_status"] == "matched").mean()
    checks.append(
        _check(
            "matching_rate_plausible",
            cfg["qa"]["minimum_expected_matching_rate"]
            <= match_rate
            <= cfg["qa"]["maximum_expected_matching_rate"],
            round(float(match_rate), 4),
            (
                f"{cfg['qa']['minimum_expected_matching_rate']:.2f}–"
                f"{cfg['qa']['maximum_expected_matching_rate']:.2f}"
            ),
        )
    )
    false_positives = int(linkage_eval["false_positive"].sum())
    checks.append(_check("record_linkage_false_positives", false_positives == 0, false_positives, "0"))
    expected_matches = int(truth["expected_match"].sum())
    true_positives = int(linkage_eval["true_positive"].sum())
    checks.append(
        _check(
            "expected_links_recovered",
            true_positives == expected_matches,
            true_positives,
            str(expected_matches),
        )
    )
    checks.append(
        _check(
            "supplier_years_complete",
            set(suppliers["year"]) == set(cfg["project"]["years"]),
            sorted(suppliers["year"].unique().tolist()),
            str(cfg["project"]["years"]),
        )
    )
    checks.append(
        _check(
            "supplier_transaction_threshold",
            (suppliers["cattle_heads"] >= cfg["selection"]["minimum_transaction_heads"]).all(),
            int(suppliers["cattle_heads"].min()),
            f">= {cfg['selection']['minimum_transaction_heads']} heads after aggregation",
        )
    )
    role_duplicates = suppliers.duplicated(
        ["slaughterhouse_id", "year", "gta_property_id", "supplier_type"]
    ).sum()
    checks.append(_check("supplier_role_keys_unique", role_duplicates == 0, int(role_duplicates), "0"))
    checks.append(
        _check(
            "zone_geometries_valid",
            zones.geometry.is_valid.all() and (~zones.geometry.is_empty).all(),
            int(zones.geometry.is_valid.sum()),
            f"{len(zones)} valid, non-empty zones",
        )
    )
    area_error = np.max(
        np.abs(zones["area_ha"] - zones.geometry.area / 10_000)
        / np.maximum(zones["area_ha"], 1)
    )
    checks.append(
        _check(
            "zone_area_recalculation",
            area_error <= cfg["qa"]["area_relative_tolerance"],
            float(area_error),
            f"<= {cfg['qa']['area_relative_tolerance']}",
        )
    )
    required_zone_types = {
        "CA_direct",
        "CA_tier1_indirect",
        "non_CA_direct",
        "non_CA_tier1_indirect",
    }
    checks.append(
        _check(
            "four_zone_types_present",
            required_zone_types.issubset(set(zones["zone_type"])),
            sorted(zones["zone_type"].unique().tolist()),
            sorted(required_zone_types),
        )
    )
    with rasterio.open(paths["raw"] / "land_use_2018.tif") as src:
        classes = set(np.unique(src.read(1)).tolist())
    allowed_classes = {0, *[int(key) for key in cfg["land_use"]["classes"]]}
    checks.append(
        _check(
            "land_use_class_values",
            classes.issubset(allowed_classes),
            sorted(classes),
            sorted(allowed_classes),
        )
    )
    tx_ids_unique = transactions["transaction_id"].is_unique
    checks.append(
        _check(
            "transaction_ids_unique",
            tx_ids_unique,
            transactions["transaction_id"].nunique(),
            str(len(transactions)),
        )
    )

    expected_outputs = [
        paths["tables"] / "zone_overlap.csv",
        paths["tables"] / "ca_direct_persistence.csv",
        paths["tables"] / "land_use_by_zone.csv",
        paths["tables"] / "deforestation_carbon_by_zone.csv",
        paths["tables"] / "expansion_pathways.csv",
        paths["figures"] / "figure_1_study_area.png",
        paths["figures"] / "figure_2_zone_overlap.png",
        paths["figures"] / "figure_3_persistence.png",
        paths["figures"] / "figure_s1_zone_area_boxplots.png",
        paths["figures"] / "figure_s2_deforestation_carbon.png",
        paths["figures"] / "figure_s3_example_zone.png",
    ]
    missing = [str(path.relative_to(paths["root"])) for path in expected_outputs if not path.exists()]
    checks.append(_check("required_outputs_exist", not missing, missing, "no missing files"))

    report = pd.DataFrame(checks)
    report.to_csv(paths["qa"] / "qa_checks.csv", index=False)
    payload = {
        "overall_status": "PASS" if (report["status"] == "PASS").all() else "FAIL",
        "checks": checks,
    }
    (paths["qa"] / "qa_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown = [
        "# QA report",
        "",
        f"Overall status: **{payload['overall_status']}**",
        "",
        "| Check | Status | Observed | Expected |",
        "|---|---:|---|---|",
    ]
    for row in checks:
        observed = str(row["observed"]).replace("|", "/")
        expected = str(row["expected"]).replace("|", "/")
        markdown.append(
            f"| {row['check']} | {row['status']} | {observed} | {expected} |"
        )
    (paths["qa"] / "QA_REPORT.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return report


def write_output_inventory(cfg: dict) -> Path:
    paths = ensure_directories(cfg)
    rows = []
    for directory_key in ["raw", "interim", "tables", "spatial", "figures", "qa"]:
        for path in sorted(paths[directory_key].glob("*")):
            if path.is_file():
                rows.append(
                    {
                        "category": directory_key,
                        "relative_path": str(path.relative_to(paths["root"])),
                        "bytes": path.stat().st_size,
                    }
                )
    inventory = pd.DataFrame(rows)
    output = paths["qa"] / "output_inventory.csv"
    inventory.to_csv(output, index=False)
    return output

