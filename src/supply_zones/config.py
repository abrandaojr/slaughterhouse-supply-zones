from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config_path = Path(path) if path else repository_root() / "config" / "config.yml"
    with config_path.open("r", encoding="utf-8") as stream:
        cfg = yaml.safe_load(stream)
    cfg["_root"] = str(repository_root())
    return cfg


def project_paths(cfg: dict[str, Any]) -> dict[str, Path]:
    root = Path(cfg["_root"])
    return {
        "root": root,
        "raw": root / "data" / "raw",
        "interim": root / "data" / "interim",
        "tables": root / "outputs" / "tables",
        "spatial": root / "outputs" / "spatial",
        "figures": root / "outputs" / "figures",
        "qa": root / "outputs" / "qa",
    }


def ensure_directories(cfg: dict[str, Any]) -> dict[str, Path]:
    paths = project_paths(cfg)
    for key, path in paths.items():
        if key != "root":
            path.mkdir(parents=True, exist_ok=True)
    return paths


def cumulative_scope_label(cfg: dict[str, Any]) -> str:
    """The sentinel `temporal_scope` value for the all-years cumulative union.

    Computed from the configured project years so the workflow generalizes to
    any year range, rather than a range hardcoded to one historical example.
    """
    years = cfg["project"]["years"]
    return f"{min(years)}_{max(years)}_union"


def year_range_label(cfg: dict[str, Any]) -> str:
    """A human-readable year range, e.g. '2013-2018', for titles and captions."""
    years = cfg["project"]["years"]
    return f"{min(years)}-{max(years)}"

