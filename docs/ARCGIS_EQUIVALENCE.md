# ArcGIS-to-Python equivalence

| Published operation | Python reconstruction | Important difference |
|---|---|---|
| Incremental Spatial Autocorrelation, ArcGIS Pro 3.1.3 | Distance-band Global Moran’s I with cattle-volume attributes and fixed-seed permutation z-scores | ArcGIS analytic z-score details and environment settings are not fully reported in the article. Small numerical differences are expected. |
| Peak spatial-autocorrelation distance | Maximum eligible permutation z-score | The search grid and tie handling are declared in `config/config.yml`. |
| Aggregate Polygons | Half-distance buffer, dissolve, equal negative buffer, component ranking, clip, simplify | ArcGIS cartographic aggregation uses proprietary implementation details. Topology and areas may differ slightly. |
| Raster land-use overlay | Rasterio rasterization and class counting | Synthetic 10 km pixels are deliberately coarse; empirical work should preserve source resolution. |
| PRODES and biomass overlay | Shapely polygon intersection plus Rasterio sampling of a synthetic biomass raster | The compact synthetic raster is much coarser than an empirical carbon-density product. |

This repository provides methodological equivalence, not software identity. The open implementation is auditable and removes the ArcGIS license requirement, but empirical replication should include a sensitivity comparison against the original ArcGIS outputs.
