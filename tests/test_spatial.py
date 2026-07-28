import geopandas as gpd
import numpy as np
from shapely.geometry import box

from supply_zones.spatial import (
    aggregate_supplier_polygons,
    global_moran,
    incremental_spatial_autocorrelation,
)


def test_global_moran_detects_positive_pattern():
    values = np.array([1.0, 1.1, 8.9, 9.0])
    weights = np.array(
        [
            [0, 1, 0, 0],
            [1, 0, 0, 0],
            [0, 0, 0, 1],
            [0, 0, 1, 0],
        ]
    )
    assert global_moran(values, weights) > 0


def test_incremental_autocorrelation_returns_candidate_distance():
    coordinates = np.array([[0, 0], [10_000, 0], [100_000, 0], [110_000, 0]])
    values = np.array([10, 11, 90, 91])
    candidates = [20, 50, 120]
    results, selected = incremental_spatial_autocorrelation(
        coordinates, values, candidates, permutations=19, seed=42
    )
    assert len(results) == 3
    assert selected in candidates


def test_polygon_aggregation_connects_nearby_properties():
    frame = gpd.GeoDataFrame(
        {
            "cattle_heads": [80, 20],
            "geometry": [box(0, 0, 1000, 1000), box(2000, 0, 3000, 1000)],
        },
        crs="EPSG:5880",
    )
    result = aggregate_supplier_polygons(
        frame,
        aggregation_distance_m=1200,
        volume_coverage=1.0,
        study_geometry=box(-10_000, -10_000, 20_000, 20_000),
        simplify_tolerance_m=0,
    )
    assert not result.is_empty
    assert result.geom_type in {"Polygon", "MultiPolygon"}

