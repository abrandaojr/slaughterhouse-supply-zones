from __future__ import annotations

import shutil

import geopandas as gpd

from supply_zones.characterize import characterize_all
from supply_zones.config import ensure_directories, project_paths
from supply_zones.figures import create_all_figures
from supply_zones.matching import link_gta_to_car
from supply_zones.network import identify_supplier_roles
from supply_zones.qa import run_qa, write_output_inventory
from supply_zones.spatial import map_supply_zones
from supply_zones.synthetic import generate_synthetic_data


def clean_generated(cfg: dict) -> None:
    """Remove only bounded, workflow-generated data and output directories."""
    paths = project_paths(cfg)
    targets = [paths["raw"], paths["interim"], paths["tables"], paths["spatial"], paths["figures"], paths["qa"]]
    for target in targets:
        if target.exists() and target.is_dir() and paths["root"] in target.parents:
            shutil.rmtree(target)
    ensure_directories(cfg)


def run_all(cfg: dict, clean: bool = False) -> None:
    if clean:
        clean_generated(cfg)
    print("[1/7] Generating fictitious input data")
    generate_synthetic_data(cfg)
    print("[2/7] Linking GTA establishments to CAR-like properties")
    link_gta_to_car(cfg)
    print("[3/7] Identifying direct and tier-1 indirect suppliers")
    identify_supplier_roles(cfg)
    print("[4/7] Selecting spatial-autocorrelation distances and mapping zones")
    zones = map_supply_zones(cfg)
    print("[5/7] Characterizing zones and expansion pathways")
    results = characterize_all(cfg, zones)
    print("[6/7] Creating main and supplementary-style figures")
    create_all_figures(cfg, zones, results)
    print("[7/7] Running QA gates and writing inventory")
    qa = run_qa(cfg)
    write_output_inventory(cfg)
    if (qa["status"] != "PASS").any():
        failed = qa.loc[qa["status"] != "PASS", "check"].tolist()
        raise RuntimeError(f"QA failed: {', '.join(failed)}")
    paths = project_paths(cfg)
    print(f"Reproduction complete: {paths['root'] / 'outputs'}")


def load_existing_zones(cfg: dict) -> gpd.GeoDataFrame:
    paths = ensure_directories(cfg)
    return gpd.read_file(paths["spatial"] / "supply_zones.gpkg", layer="annual_zones")

