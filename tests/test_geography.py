import builtins
import sys
import types

import geopandas as gpd
from shapely.geometry import Polygon

from supply_zones import osm as osm_module
from supply_zones.config import load_config


def _fake_osmnx_module(polygons: dict[str, Polygon]) -> types.ModuleType:
    fake = types.ModuleType("osmnx")

    def geocode_to_gdf(query: str) -> gpd.GeoDataFrame:
        geometry = polygons[query]
        return gpd.GeoDataFrame(
            [{"display_name": query, "geometry": geometry}], crs="EPSG:4326"
        )

    fake.geocode_to_gdf = geocode_to_gdf
    return fake


def test_resolve_admin_units_uses_osm_when_available(tmp_path, monkeypatch):
    """When osmnx is importable, real geometry should be fetched, cached, and
    reprojected to an appropriate local metric CRS, for any place name."""
    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["geography"] = {
        "mode": "osm",
        "place_queries": ["Testland A", "Testland B"],
        "unit_codes": ["TA", "TB"],
        "cache_dir": "data/raw/osm_cache",
    }
    polygons = {
        "Testland A": Polygon([(-60, -10), (-59, -10), (-59, -9), (-60, -9)]),
        "Testland B": Polygon([(-59, -10), (-58, -10), (-58, -9), (-59, -9)]),
    }
    monkeypatch.setitem(sys.modules, "osmnx", _fake_osmnx_module(polygons))

    gdf, crs, source = osm_module.resolve_admin_units(cfg)

    assert set(gdf["state"]) == {"TA", "TB"}
    assert source == "openstreetmap"
    assert gdf.crs is not None and not gdf.crs.is_geographic
    cache_dir = tmp_path / "data" / "raw" / "osm_cache"
    assert (cache_dir / "testland_a.geojson").exists()
    assert (cache_dir / "testland_b.geojson").exists()


def test_resolve_admin_units_uses_real_natural_earth_data(tmp_path, monkeypatch):
    """With osmnx unavailable, real place names should resolve through the
    public-domain Natural Earth dataset (a genuine network fetch to GitHub,
    not mocked), producing real, non-rectangular coordinates."""
    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["geography"] = {
        "mode": "osm",
        "place_queries": ["Rondônia, Brazil", "Mato Grosso, Brazil", "Pará, Brazil"],
        "unit_codes": ["RO", "MT", "PA"],
        "cache_dir": "data/raw/osm_cache",
    }
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "osmnx":
            raise ImportError("osmnx not installed in this environment")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    gdf, crs, source = osm_module.resolve_admin_units(cfg)

    assert source == "natural_earth"
    assert set(gdf["state"]) == {"RO", "MT", "PA"}
    assert gdf.crs is not None and not gdf.crs.is_geographic
    # Real admin-1 polygons are irregular, unlike the offline rectangle
    # fallback: none of the fetched shapes should be an exact 4-corner box.
    for geometry in gdf.geometry:
        exterior_coords = (
            geometry.exterior.coords
            if geometry.geom_type == "Polygon"
            else max(geometry.geoms, key=lambda part: part.area).exterior.coords
        )
        assert len(exterior_coords) > 5


def test_resolve_admin_units_falls_back_when_no_source_matches(tmp_path, monkeypatch):
    """If osmnx cannot be imported and the place names match nothing in
    Natural Earth either, the workflow must still produce a usable,
    deterministic set of admin units offline, for any number of places."""
    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["geography"] = {
        "mode": "osm",
        "place_queries": ["Nowhere A", "Nowhere B", "Nowhere C"],
        "unit_codes": ["NA", "NB", "NC"],
        "cache_dir": "data/raw/osm_cache",
    }
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "osmnx":
            raise ImportError("no osmnx in this environment")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    gdf, crs, source = osm_module.resolve_admin_units(cfg)

    assert set(gdf["state"]) == {"NA", "NB", "NC"}
    assert source == "synthetic_fallback"
    assert len(gdf) == 3
    assert gdf.crs is not None


def test_resolve_admin_units_synthetic_mode_skips_osm_entirely(tmp_path):
    """Explicit 'synthetic' mode should never attempt network access."""
    cfg = load_config()
    cfg["_root"] = str(tmp_path)
    cfg["geography"] = {
        "mode": "synthetic",
        "place_queries": ["Anywhere, Anycountry"],
        "unit_codes": ["A1"],
    }
    gdf, crs, source = osm_module.resolve_admin_units(cfg)
    assert list(gdf["state"]) == ["A1"]
    assert source == "synthetic_fallback"


def test_fallback_layout_handles_arbitrary_unit_counts():
    """The offline layout generator must not be hardcoded to three units."""
    for codes in (["A"], ["A", "B"], ["A", "B", "C", "D", "E"]):
        layout = osm_module._fallback_rectangle_layout(codes, 500_000, 500_000)
        assert set(layout) == set(codes)
        for bounds in layout.values():
            minx, miny, maxx, maxy = bounds
            assert maxx > minx and maxy > miny
