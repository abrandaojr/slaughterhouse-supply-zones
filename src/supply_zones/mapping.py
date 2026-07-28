"""Shared helper for placing synthetic geographic data on a real OpenStreetMap basemap."""

from __future__ import annotations

import json
from pathlib import Path


def _geography_is_real(paths: dict) -> bool:
    marker = paths["raw"] / "geography_source.json"
    if not marker.exists():
        return False
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("source") == "openstreetmap"
    except Exception:  # noqa: BLE001
        return False


def add_basemap_if_available(ax, crs, paths: dict) -> None:
    """Draw a real OpenStreetMap tile basemap behind the current axes.

    Only attempted when the plotted geometry is anchored to real coordinates
    (i.e. ``geography.mode: osm`` succeeded for this run) — overlaying map
    tiles behind the arbitrary offline fallback rectangles would place them
    at a meaningless location. Requires the optional ``contextily``
    dependency and network access to a tile server; any failure is silent so
    figure generation never breaks when a basemap isn't available.
    """
    if not _geography_is_real(paths):
        return
    try:
        import contextily as cx

        cx.add_basemap(
            ax, crs=str(crs), source=cx.providers.OpenStreetMap.Mapnik, attribution=False, zorder=-10
        )
    except Exception as exc:  # noqa: BLE001 - basemap is a visual enhancement, never fatal
        print(
            "[mapping] Could not draw an OpenStreetMap basemap "
            f"({exc.__class__.__name__}: {exc}); showing data without a basemap. "
            "Install `contextily` and ensure network access to a tile server to enable it."
        )
