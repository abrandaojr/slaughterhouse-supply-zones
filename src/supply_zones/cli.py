from __future__ import annotations

import argparse

from supply_zones.characterize import characterize_all
from supply_zones.config import load_config
from supply_zones.figures import create_all_figures
from supply_zones.matching import link_gta_to_car
from supply_zones.network import identify_supplier_roles
from supply_zones.pipeline import clean_generated, load_existing_zones, run_all
from supply_zones.qa import run_qa, write_output_inventory
from supply_zones.report import build_report
from supply_zones.spatial import map_supply_zones
from supply_zones.synthetic import generate_synthetic_data


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="Synthetic reproduction of Brandão et al. (2023)."
    )
    command_parser.add_argument(
        "command",
        choices=["generate", "link", "network", "zones", "analyze", "report", "qa", "all", "clean"],
    )
    command_parser.add_argument("--config", default=None, help="Path to YAML configuration.")
    command_parser.add_argument(
        "--clean", action="store_true", help="Remove generated outputs before a full run."
    )
    return command_parser


def main() -> None:
    args = parser().parse_args()
    cfg = load_config(args.config)
    if args.command == "generate":
        generate_synthetic_data(cfg)
    elif args.command == "link":
        link_gta_to_car(cfg)
    elif args.command == "network":
        identify_supplier_roles(cfg)
    elif args.command == "zones":
        map_supply_zones(cfg)
    elif args.command == "analyze":
        zones = load_existing_zones(cfg)
        results = characterize_all(cfg, zones)
        create_all_figures(cfg, zones, results)
    elif args.command == "report":
        zones = load_existing_zones(cfg)
        results = characterize_all(cfg, zones)
        build_report(cfg, zones, results)
    elif args.command == "qa":
        report = run_qa(cfg)
        write_output_inventory(cfg)
        if (report["status"] != "PASS").any():
            raise SystemExit(1)
    elif args.command == "clean":
        clean_generated(cfg)
    elif args.command == "all":
        run_all(cfg, clean=args.clean)

