"""Resolve the study area's administrative units from global, open data.

This module is what makes the workflow geographically generic: instead of a
hardcoded set of Brazilian state rectangles, the study area is defined by a
list of place names in the project configuration (``geography.place_queries``
in ``config.yml``), which can name *any* place in the world. Three tiers of
resolution are tried, in order, so the workflow always has the best
available real-world anchoring:

1. **OpenStreetMap** (``osmnx``, Nominatim + Overpass): the most precise and
   current source, when the optional dependency and full network access are
   available.
2. **Natural Earth** (public-domain admin-1 boundaries, mirrored on GitHub):
   a real, globally-available fallback that needs only a plain HTTPS fetch
   to a GitHub raw-content URL, so it works in far more restricted network
   environments than OSM's own services.
3. **Deterministic offline rectangles**: a last-resort layout with no
   network dependency at all, used only if neither real source is reachable.

Either way, downstream code only ever sees a GeoDataFrame with ``state`` (a
short unit code, e.g. an abbreviation) and ``geometry`` columns in an
appropriate local projected CRS, so no other module needs to know which tier
was used. A written marker (``geography_source.json``) records which tier
produced the data, so plotting code knows whether the coordinates are real
(tiers 1-2, in which case a real OpenStreetMap basemap is also attempted) or
an arbitrary offline layout (tier 3, where a basemap would be meaningless).
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_1_states_provinces.geojson"
)


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

    Used only when neither real geographic source is reachable. Works for
    any number of units, unlike a hardcoded three-state layout.
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


def _load_natural_earth_admin1(cache_dir: Path):
    """Download (once) and cache the Natural Earth admin-1 dataset."""
    import urllib.request

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "natural_earth_admin1.geojson"
    if not cache_path.exists():
        with urllib.request.urlopen(NATURAL_EARTH_URL, timeout=30) as response:
            cache_path.write_bytes(response.read())
    return gpd.read_file(cache_path)


def _fetch_from_natural_earth(
    place_queries: list[str], codes: list[str], cache_dir: Path
) -> gpd.GeoDataFrame:
    """Fetch real admin-1 boundaries from the public-domain Natural Earth
    dataset, mirrored on GitHub. Needs only a plain HTTPS GET to a GitHub
    raw-content URL, so it works in network environments that block
    Nominatim/Overpass but allow ordinary GitHub access. A place query may be
    ``"Region name"`` or ``"Region name, Country"``; matching is
    case-insensitive and accent-insensitive. Raises if any query cannot be
    matched, so the caller can fall back cleanly.
    """
    admin1 = _load_natural_earth_admin1(cache_dir)
    name_key = admin1["name"].map(lambda value: _slug(str(value)))
    admin_key = admin1["admin"].map(lambda value: _slug(str(value)))

    rows = []
    for query, code in zip(place_queries, codes):
        parts = [part.strip() for part in query.split(",")]
        region_key = _slug(parts[0])
        candidates = admin1[name_key == region_key]
        if len(parts) > 1:
            country_key = _slug(parts[-1])
            with_country = candidates[admin_key[candidates.index] == country_key]
            if not with_country.empty:
                candidates = with_country
        if candidates.empty:
            raise ValueError(f"No Natural Earth admin-1 region matched '{query}'")
        feature = candidates.iloc[0]
        rows.append(
            {
                "state": code,
                "state_name": query,
                "osm_display_name": f"{feature['name']}, {feature['admin']} (Natural Earth)",
                "geometry": feature.geometry,
            }
        )
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=admin1.crs or "EPSG:4326")
    metric_crs = gdf.estimate_utm_crs()
    return gdf.to_crs(metric_crs)


def resolve_admin_units(cfg: dict) -> tuple[gpd.GeoDataFrame, str, str]:
    """Resolve the study area's administrative units and an appropriate CRS.

    Returns a GeoDataFrame with ``state``, ``state_name``, and ``geometry``
    columns in a locally appropriate projected CRS, that CRS as a string, and
    the data source actually used: ``"openstreetmap"``, ``"natural_earth"``,
    or ``"synthetic_fallback"``. The first two are real-world geometry (from
    OpenStreetMap or the public-domain Natural Earth dataset); the third is
    the deterministic offline rectangle layout. Any place in the world can be
    requested through ``geography.place_queries``; nothing else in the
    pipeline is Brazil-specific or otherwise geography-locked.
    """
    geography_cfg = cfg.get("geography", {})
    mode = geography_cfg.get("mode", "synthetic")
    place_queries = geography_cfg.get("place_queries", [])
    codes = geography_cfg.get("unit_codes") or _default_codes(place_queries)
    root = Path(cfg["_root"])
    cache_dir = root / geography_cfg.get("cache_dir", "data/raw/osm_cache")

    if mode in ("osm", "natural_earth") and place_queries:
        if mode == "osm":
            try:
                gdf = _fetch_from_osm(place_queries, codes, cache_dir)
                print(
                    "[geography] Using real administrative boundaries from "
                    f"OpenStreetMap for: {', '.join(place_queries)}"
                )
                return gdf, str(gdf.crs), "openstreetmap"
            except Exception as exc:  # noqa: BLE001 - any failure should fall back cleanly
                print(
                    "[geography] Could not fetch OpenStreetMap boundaries "
                    f"({exc.__class__.__name__}: {exc}); trying the Natural Earth "
                    "fallback next."
                )
        try:
            gdf = _fetch_from_natural_earth(place_queries, codes, cache_dir)
            print(
                "[geography] Using real administrative boundaries from "
                f"Natural Earth (public domain, via GitHub) for: {', '.join(place_queries)}"
            )
            return gdf, str(gdf.crs), "natural_earth"
        except Exception as exc:  # noqa: BLE001 - any failure should fall back cleanly
            print(
                "[geography] Could not fetch Natural Earth boundaries "
                f"({exc.__class__.__name__}: {exc}); falling back to a deterministic "
                "offline synthetic layout. Ensure network access to GitHub (or "
                "install `osmnx` with full network access) to use real geometry."
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
    return gdf, fallback_crs, "synthetic_fallback"
