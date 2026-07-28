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

