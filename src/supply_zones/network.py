from __future__ import annotations

import geopandas as gpd
import pandas as pd

from supply_zones.config import ensure_directories


def identify_supplier_roles(cfg: dict) -> gpd.GeoDataFrame:
    """Identify direct and tier-1 indirect suppliers for each plant and year."""
    paths = ensure_directories(cfg)
    tx = pd.read_csv(paths["raw"] / "gta_transactions.csv")
    linked = gpd.read_file(paths["interim"] / "linked_properties.gpkg")
    plants = gpd.read_file(paths["raw"] / "synthetic_inputs.gpkg", layer="slaughterhouses")
    threshold = cfg["selection"]["minimum_transaction_heads"]

    matched_ids = set(linked["gta_property_id"])
    slaughter = tx[
        (tx["purpose"] == "slaughter")
        & (tx["destination_type"] == "slaughterhouse")
        & (tx["heads"] >= threshold)
        & tx["origin_gta_property_id"].isin(matched_ids)
    ].copy()
    annual = (
        slaughter.groupby(["destination_id", "year"], as_index=False)["heads"]
        .sum()
        .rename(columns={"destination_id": "slaughterhouse_id", "heads": "annual_heads"})
    )
    average = annual.groupby("slaughterhouse_id", as_index=False)["annual_heads"].mean()
    average = average.rename(columns={"annual_heads": "mean_annual_heads"})
    plants = plants.merge(average, on="slaughterhouse_id", how="left")
    plants["mean_annual_heads"] = plants["mean_annual_heads"].fillna(0)
    eligible = plants[
        (plants["mean_annual_heads"] > cfg["selection"]["minimum_annual_slaughter_heads"])
        & plants["inspection_code"].notna()
    ].copy()
    eligible_ids = set(eligible["slaughterhouse_id"])
    slaughter = slaughter[slaughter["destination_id"].isin(eligible_ids)]

    direct = (
        slaughter.groupby(
            ["destination_id", "year", "origin_gta_property_id"], as_index=False
        )["heads"]
        .sum()
        .rename(
            columns={
                "destination_id": "slaughterhouse_id",
                "origin_gta_property_id": "gta_property_id",
                "heads": "cattle_heads",
            }
        )
    )
    direct["supplier_type"] = "direct"

    direct_destinations = direct[
        ["slaughterhouse_id", "year", "gta_property_id"]
    ].rename(columns={"gta_property_id": "destination_id"})
    farm_moves = tx[
        (tx["destination_type"] == "property")
        & (tx["purpose"] != "slaughter")
        & (tx["heads"] >= threshold)
        & tx["origin_gta_property_id"].isin(matched_ids)
        & tx["destination_id"].isin(matched_ids)
    ].copy()
    indirect = farm_moves.merge(direct_destinations, on=["year", "destination_id"], how="inner")
    indirect = (
        indirect.groupby(
            ["slaughterhouse_id", "year", "origin_gta_property_id"], as_index=False
        )["heads"]
        .sum()
        .rename(
            columns={
                "origin_gta_property_id": "gta_property_id",
                "heads": "cattle_heads",
            }
        )
    )

    # Property-level hierarchy: a property that is a direct supplier anywhere in
    # the same year is not also classified as tier-1 indirect that year.
    direct_year_keys = set(zip(direct["year"], direct["gta_property_id"]))
    indirect = indirect[
        ~indirect.apply(
            lambda row: (row["year"], row["gta_property_id"]) in direct_year_keys, axis=1
        )
    ].copy()
    indirect["supplier_type"] = "tier1_indirect"

    suppliers = pd.concat([direct, indirect], ignore_index=True)
    suppliers = suppliers.merge(
        eligible[
            [
                "slaughterhouse_id",
                "state",
                "inspection_type",
                "inspection_code",
                "ca_signatory",
            ]
        ],
        on="slaughterhouse_id",
        how="left",
    )
    supplier_geometries = linked[
        ["gta_property_id", "car_id", "geometry"]
    ].copy()
    suppliers = suppliers.merge(supplier_geometries, on="gta_property_id", how="left")
    suppliers = gpd.GeoDataFrame(suppliers, geometry="geometry", crs=linked.crs)
    suppliers["zone_type"] = suppliers.apply(
        lambda row: (
            ("CA" if row["ca_signatory"] else "non_CA")
            + "_"
            + ("direct" if row["supplier_type"] == "direct" else "tier1_indirect")
        ),
        axis=1,
    )

    output = paths["interim"] / "analytical_suppliers.gpkg"
    suppliers.to_file(output, layer="suppliers", driver="GPKG")
    eligible.to_file(output, layer="eligible_slaughterhouses", driver="GPKG", mode="a")
    annual.to_csv(paths["tables"] / "annual_slaughterhouse_volume.csv", index=False)
    return suppliers

