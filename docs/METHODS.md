# Methods implemented in this repository

## Scope and analytical unit

The workflow reproduces the logic of Brandão et al. (2023). By default it is configured for three synthetic state-shaped regions labeled PA, MT, and RO (Pará, Mato Grosso, and Rondônia, Brazil), covering 2013–2018, matching the original study's setting. Neither the geography nor the observation period is hardcoded, however: any region in the world and any year range can be substituted through `config/config.yml` (see "Geographic genericity" below). The main analytical unit is the slaughterhouse–year–supplier-type combination. Property-level flows are the unit used to identify direct and tier-1 indirect suppliers.

All spatial calculations use a projected, equal-area-appropriate CRS: an automatically estimated local UTM zone when real OpenStreetMap boundaries are fetched, or the configured `fallback_crs` (EPSG:5880 by default) otherwise. The synthetic rasters use 10 km cells to keep the repository compact. This resolution is appropriate only for the demonstration data and must not be carried into empirical applications without reassessment.

## Geographic genericity

`src/supply_zones/osm.py` resolves the study area's administrative units (the workflow's generic term for what the source study calls "states") from `geography.place_queries` in the configuration, which can name any place recognized by OpenStreetMap or Natural Earth, worldwide. Three tiers are tried in order: (1) OpenStreetMap via the optional `osmnx` dependency plus Nominatim/Overpass access; (2) the public-domain Natural Earth admin-1 dataset, mirrored on GitHub, needing only a plain HTTPS fetch; (3) a deterministic offline rectangular layout with no network dependency. Whichever real tier succeeds, the fetched geometry is cached to `data/raw/osm_cache/` and an appropriate local metric CRS is estimated automatically. Property and slaughterhouse placement uses rejection sampling to guarantee valid, non-empty geometry inside the resolved administrative polygon regardless of its shape (rectangular, or real and irregular, including multi-part polygons). A marker file (`data/raw/geography_source.json`) records which tier was used; figures draw a real OpenStreetMap tile basemap (via the optional `contextily` dependency) only when a real tier succeeded.

Throughout the code, "CA" (Brazil's Cattle Agreement, the zero-deforestation sourcing commitment the source study examined) is retained as the internal data label for backward compatibility with the source study, but is presented to readers as "signatory" / "non-signatory" in figures, tables, and the plain-language report, since a public sourcing commitment of this kind is not unique to Brazil.

## Transformation graph

1. `osm.py` resolves the study area's administrative units from OpenStreetMap or a deterministic offline fallback (see "Geographic genericity" above). `synthetic.py` then creates GTA-like movements, GTA establishment attributes, CAR-like property polygons, slaughterhouses, agreement status, biomes, protected areas, military areas, land use, deforestation, and biomass carbon density within those units.
2. `matching.py` standardizes text and identifiers, then applies strict, ordered GTA–CAR matching rules. A record is linked only when a rule identifies one unique CAR candidate.
3. `network.py` filters movements below 16 heads, selects inspected slaughterhouses with mean annual slaughter above 1,000 heads, identifies direct suppliers, and traces tier-1 non-slaughter movements into direct suppliers in the same year.
4. A property that has both roles in the same year is classified at its highest supply-chain role, direct supplier.
5. `spatial.py` calculates cattle-volume-weighted Global Moran’s I over 50–220 km distance bands. Fixed-seed permutations provide z-scores. The distance with the highest z-score among bands connecting at least half the suppliers is selected.
6. Supplier polygons are buffered by half the selected distance, dissolved, and contracted by the same amount. Components are ranked by their included cattle volume and retained until they contain 95% of the group’s cattle. The result is clipped to the synthetic study area and topology-preserving simplification is applied.
7. Annual zones are classified as CA direct, CA tier-1 indirect, non-CA direct, or non-CA tier-1 indirect.
8. `characterize.py` calculates annual and cumulative areas, pairwise overlap, six-year persistence, land use, filtered deforestation, committed carbon emissions, nearest-neighbor distances, supplier flows, agreement-expansion pathways, and alternative-zone comparisons.
9. `figures.py` and `report_charts.py` create three main-figure analogues, three supplementary-figure analogues, and eight additional report-oriented figures and maps. `report.py` assembles all of these, plus every table, into a single plain-language Markdown report.
10. `qa.py` checks keys, linkage truth, CRS, geometry validity, thresholds, areas, raster classes, temporal coverage, and output completeness.

## Explicit operational decisions

The article does not publish every ArcGIS environment setting or every record-linkage field combination used by the authors’ internal database. This reconstruction therefore makes the following decisions explicit and configurable:

- The slaughterhouse threshold is interpreted as mean annual slaughter greater than 1,000 heads over 2013–2018.
- The incremental Moran search uses binary distance-band weights, row standardization, 99 fixed-seed permutations, and the largest eligible z-score.
- Sparse groups with fewer than four suppliers use twice the median nearest-neighbor distance, bounded by configured minimum and maximum distances.
- The phrase “most cattle” is operationalized as components containing 95% of cattle volume.
- Persistence and raster overlays use the synthetic raster cell size in `config/config.yml`.
- The supplier-hull comparison is only a transparent proxy. It does not claim to reproduce the unpublished cost-distance settings used in earlier studies.

These decisions allow full computational reproduction without pretending that missing parameters are known.

## Land-use and deforestation rules

The synthetic land-use raster contains four reclassified categories: pasture, natural vegetation, soybean, and other. Natural-vegetation coverage is calculated outside synthetic Indigenous Lands, Conservation Units, and Military Areas.

Synthetic PRODES-like polygons are filtered at 6.25 ha in the Amazon label and 1 ha in the Cerrado label. Pantanal-labeled polygons are excluded. Deforestation is grouped into through-2007 and annual 2008–2018 periods. Committed emissions are:

`clipped deforestation area (ha) × biomass carbon density (Mg C/ha) × 44/12 ÷ 1,000,000`.

The result is expressed in MtCO₂e.

## Interpretation

Outputs demonstrate reproducibility of the method, not empirical evidence about Brazil or any other configured region. Regional codes and article terminology are retained only to make the analytical correspondence to the source study easy to inspect; the underlying method works identically for any place named in `geography.place_queries`.
