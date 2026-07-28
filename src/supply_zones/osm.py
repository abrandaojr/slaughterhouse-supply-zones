"""Resolve the study area's administrative units from global, open data.

This module is what makes the workflow geographically generic: instead of a
hardcoded set of Brazilian state rectangles, the study area is defined by a
list of place names in the project configuration (``geography.place_queries``
in ``config.yml``), which can name *any* place in the world. When network
access to OpenStreetMap is available, real administrative boundaries are
fetched through ``osmnx`` (Nominatim geocoding + the OSM database, both free
and globally accessible) and cached to disk as GeoJSON. When OSM cannot be
reached, either because the optional ``osmnx`` dependency is not installed or
because the network call fails, the workflow falls back to a deterministic,
offline rectangular layout so the pipeline remains fully reproducible without
an internet connection.

Either way, downstream code only ever sees a GeoDataFrame with ``state`` (a
short unit code, e.g. an abbreviation) and ``geometry`` columns in an
appropriate local projected CRS, so no other module needs to know which mode
was used.
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


def _slug(text: str) -> str:
    ascii_text = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def _default_codes(place_queries: list[str]) -> list[str]:
    codes = []
    for query in place_queries:
        primary = query.split(",")[0].strip()
        letters = re.sub(r"[^A-Za-z]", "", primary).upper()
        codes.append((letters[:2] or "XX"))
    # Disambiguate any duplicate two-letter codes deterministically.
    seen: dict[str, int] = {}
    unique_codes = []
    for code in codes:
        seen[code] = seen.get(code, 0) + 1
        unique_codes.append(code if seen[code] == 1 else f"{code}{seen[code]}")
    return unique_codes


def _fallback_rectangle_layout(
    codes: list[str], unit_width_m: float, unit_height_m: float
) -> dict[str, tuple[float, float, float, float]]:
    """A deterministic, offline, N-unit rectangular grid.

    Used whenever OpenStreetMap boundaries are not fetched. Works for any
    number of units, unlike a hardcoded three-state layout.
    """
    n_columns = max(1, math.ceil(math.sqrt(len(codes))))
    layout = {}
    for index, code in enumerate(codes):
        row, column = divmod(index, n_columns)
        x0 = column * unit_width_m
        y0 = row * unit_height_m
        layout[code] = (x0, y0, x0 + unit_width_m, y0 + unit_height_m)
    return layout


def _fetch_from_osm(
    place_queries: list[str], codes: list[str], cache_dir: Path
) -> gpd.GeoDataFrame:
    """Fetch real administrative boundaries from OpenStreetMap via osmnx.

    Requires the optional ``osmnx`` dependency and network access to
    Nominatim/Overpass. Results are cached to ``cache_dir`` as GeoJSON so
    repeated runs, and offline re-runs, do not need to hit the network again.
    Raises on any failure so the caller can fall back cleanly.
    """
    import osmnx as ox  # optional dependency; ImportError handled by caller

    cache_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for query, code in zip(place_queries, codes):
        cache_path = cache_dir / f"{_slug(query)}.geojson"
        if cache_path.exists():
            unit = gpd.read_file(cache_path)
        else:
            unit = ox.geocode_to_gdf(query)
            unit.to_file(cache_path, driver="GeoJSON")
        geometry = unit.geometry.iloc[0]
        display_name = str(unit.iloc[0].get("display_name", query))
        rows.append({"state": code, "state_name": query, "osm_display_name": display_name, "geometry": geometry})
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    metric_crs = gdf.estimate_utm_crs()
    return gdf.to_crs(metric_crs)


def resolve_admin_units(cfg: dict) -> tuple[gpd.GeoDataFrame, str, bool]:
    """Resolve the study area's administrative units and an appropriate CRS.

    Returns a GeoDataFrame with ``state``, ``state_name``, and ``geometry``
    columns in a locally appropriate projected CRS, that CRS as a string, and
    a boolean indicating whether real OpenStreetMap geometry was used (as
    opposed to the deterministic offline fallback). Any place in the world
    can be requested through ``geography.place_queries``; nothing else in the
    pipeline is Brazil-specific or otherwise geography-locked.
    """
    geography_cfg = cfg.get("geography", {})
    mode = geography_cfg.get("mode", "synthetic")
    place_queries = geography_cfg.get("place_queries", [])
    codes = geography_cfg.get("unit_codes") or _default_codes(place_queries)
    root = Path(cfg["_root"])
    cache_dir = root / geography_cfg.get("cache_dir", "data/raw/osm_cache")

    if mode == "osm" and place_queries:
        try:
            gdf = _fetch_from_osm(place_queries, codes, cache_dir)
            print(
                "[geography] Using real administrative boundaries from "
                f"OpenStreetMap for: {', '.join(place_queries)}"
            )
            return gdf, str(gdf.crs), True
        except Exception as exc:  # noqa: BLE001 - any failure should fall back cleanly
            print(
                "[geography] Could not fetch OpenStreetMap boundaries "
                f"({exc.__class__.__name__}: {exc}); falling back to a deterministic "
                "offline synthetic layout. Install `osmnx` and ensure network "
                "access to use real OpenStreetMap geometry."
            )

    codes = codes or ["A", "B", "C"]
    unit_width_m = float(geography_cfg.get("fallback_unit_width_m", 700_000))
    unit_height_m = float(geography_cfg.get("fallback_unit_height_m", 700_000))
    fallback_crs = geography_cfg.get("fallback_crs", "EPSG:5880")
    layout = _fallback_rectangle_layout(codes, unit_width_m, unit_height_m)
    rows = [
        {"state": code, "state_name": place_queries[i] if i < len(place_queries) else code, "geometry": box(*bounds)}
        for i, (code, bounds) in enumerate(layout.items())
    ]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=fallback_crs)
    return gdf, fallback_crs, False
