# Methods implemented in this repository

## Scope and analytical unit

The workflow reproduces the logic of Brandão et al. (2023) with fictitious records for three synthetic state-shaped regions labeled PA, MT, and RO. The observation period is 2013–2018. The main analytical unit is the slaughterhouse–year–supplier-type combination. Property-level flows are the unit used to identify direct and tier-1 indirect suppliers.

All spatial calculations use the projected equal-area CRS EPSG:5880. The synthetic rasters use 10 km cells to keep the repository compact. This resolution is appropriate only for the demonstration data and must not be carried into empirical applications without reassessment.

## Transformation graph

1. `synthetic.py` creates GTA-like movements, GTA establishment attributes, CAR-like property polygons, slaughterhouses, agreement status, biomes, protected areas, military areas, land use, deforestation, and biomass carbon density.
2. `matching.py` standardizes text and identifiers, then applies strict, ordered GTA–CAR matching rules. A record is linked only when a rule identifies one unique CAR candidate.
3. `network.py` filters movements below 16 heads, selects inspected slaughterhouses with mean annual slaughter above 1,000 heads, identifies direct suppliers, and traces tier-1 non-slaughter movements into direct suppliers in the same year.
4. A property that has both roles in the same year is classified at its highest supply-chain role, direct supplier.
5. `spatial.py` calculates cattle-volume-weighted Global Moran’s I over 50–220 km distance bands. Fixed-seed permutations provide z-scores. The distance with the highest z-score among bands connecting at least half the suppliers is selected.
6. Supplier polygons are buffered by half the selected distance, dissolved, and contracted by the same amount. Components are ranked by their included cattle volume and retained until they contain 95% of the group’s cattle. The result is clipped to the synthetic study area and topology-preserving simplification is applied.
7. Annual zones are classified as CA direct, CA tier-1 indirect, non-CA direct, or non-CA tier-1 indirect.
8. `characterize.py` calculates annual and cumulative areas, pairwise overlap, six-year persistence, land use, filtered deforestation, committed carbon emissions, nearest-neighbor distances, supplier flows, agreement-expansion pathways, and alternative-zone comparisons.
9. `figures.py` creates three main-figure analogues and three supplementary-figure analogues.
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

Outputs demonstrate reproducibility of the method, not empirical evidence about Brazil. State abbreviations and article terminology are retained only to make the analytical correspondence easy to inspect.
