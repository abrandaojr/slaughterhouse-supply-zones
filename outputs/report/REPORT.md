# Mapping Slaughterhouse Supply Zones: A Reproducible, Synthetic Walkthrough

**A plain-language companion to Brandão Jr., Rausch, Munger & Gibbs (2023), *Land*, 12(9), 1782**

> **A note on the data.** Every figure, table, and number in this report is computed from a fictitious dataset built specifically for this repository. No confidential cattle-transit (GTA), rural property registry (CAR), or slaughterhouse record is used or reproduced anywhere in this document. The workflow reconstructs the *analytical logic* of Brandão Jr. et al. (2023, *Land*, 12(9), 1782) in open-source tools, not its empirical findings.

## Executive summary

Cattle raised in the Brazilian Amazon can travel through several properties
before reaching a slaughterhouse, which makes it hard to know exactly where
the animals a company buys actually came from. This report walks through a
complete, open-source workflow that estimates the geographic area, or
**supply zone**, that feeds each slaughterhouse, and separates that area into
farms that sell cattle directly to the plant from farms that sell only
through an intermediary. Using an illustrative synthetic dataset built for
this repository, across 3 states, 12 slaughterhouses, and the
years 2013-2018, the workflow finds that the average direct supply zone of a
Cattle Agreement (CA) signatory covers about 1.2 million
hectares, that roughly a quarter of that area is natural vegetation, and that
extending monitoring to indirect suppliers or non-signatory plants would
substantially widen coverage of the cattle trade at the cost of a much larger
area to monitor. Every number below comes from fictitious data; the value of
the exercise is the method, not the estimate.

## 1. Why supply zones matter

Companies, regulators, and civil-society groups that want to know whether
cattle products are linked to deforestation face a basic geographic problem:
purchase records name a slaughterhouse, not a location on a map. A supply
zone translates the plant's likely catchment area for cattle into an
explicit polygon, so it can be overlaid with land use, deforestation, and
protected-area data to ask questions such as: how much of a plant's likely
sourcing area still has forest cover, and how does that compare between
plants that have signed a public zero-deforestation commitment (the Cattle
Agreement, or **CA**) and plants that have not.

The original study built these zones from confidential cattle-transit permits
(GTA) and rural property registrations (CAR) using proprietary ArcGIS
routines. This repository asks a narrower question with synthetic stand-in
data: can the same analytical logic be reproduced end to end with transparent,
open-source tools, and does doing so change how the results should be read.
Full methodological detail is in `docs/METHODS.md`; this report focuses on
what each result means for a non-specialist reader.

## 2. Study design in brief

The workflow simulates six years of fictitious cattle-transit records, rural
property boundaries, slaughterhouse locations, land use, and deforestation
across three states. It then:

1. Links each transit record to a property using deterministic matching rules.
2. Classifies slaughterhouses as eligible when they process more than 1,000
   head per year and hold a sanitary inspection code, matching the
   thresholds used in the source study.
3. Identifies **direct suppliers** (properties that sell straight to an
   eligible plant) and **tier-1 indirect suppliers** (properties that sell to
   a direct supplier, using the same 16-head minimum transaction threshold).
4. Chooses, separately for every plant and year, the distance at which
   cattle-volume-weighted spatial clustering (Global Moran's I) peaks, and
   uses that distance to aggregate supplier properties into a single supply
   zone (an open-source analogue of the original ArcGIS Aggregate Polygons
   step).
5. Cross-tabulates the resulting zones against land use, deforestation,
   carbon density, and protected or military areas.

![Figure 1. Synthetic study area, slaughterhouse locations, and linked properties.](../figures/figure_1_study_area.png)

*Figure 1. Synthetic study area, slaughterhouse locations, and linked properties.*

## 3. How large are supply zones, and how much do they overlap

| Zone type | Zone-years observed | Mean annual area (million ha) | Median annual area (million ha) | Mean number of properties |
| --- | --- | --- | --- | --- |
| CA direct | 36 | 1.2 | 0.8 | 16.3 |
| CA tier-1 indirect | 36 | 0.1 | 0.0 | 3.2 |
| Non-CA direct | 36 | 1.0 | 1.0 | 17.6 |
| Non-CA tier-1 indirect | 36 | 0.1 | 0.0 | 3.5 |

CA-signatory plants have direct supply zones that are, on average, larger
than their non-CA counterparts in this synthetic dataset, largely because
CA-signatory plants tend to source from more properties. The zones are not
mutually exclusive: a property can appear inside more than one plant's
catchment, and different zone types partly cover the same territory.

| Zone type A | Zone type B | Share of A inside B (%) | Share of B inside A (%) | Overlap index, Jaccard (%) |
| --- | --- | --- | --- | --- |
| CA direct | CA tier-1 indirect | 12.0% | 57.8% | 11.0% |
| CA direct | Non-CA direct | 42.3% | 43.3% | 27.2% |
| CA direct | Non-CA tier-1 indirect | 13.2% | 80.7% | 12.8% |
| CA tier-1 indirect | Non-CA direct | 72.4% | 15.4% | 14.5% |
| CA tier-1 indirect | Non-CA tier-1 indirect | 36.5% | 46.4% | 25.7% |
| Non-CA direct | Non-CA tier-1 indirect | 12.4% | 74.3% | 11.9% |

![Figure 2. Cumulative overlap of all four supply-zone types, 2013-2018.](../figures/figure_2_zone_overlap.png)

*Figure 2. Cumulative overlap of all four supply-zone types, 2013-2018.*

![Figure 10. Pairwise spatial overlap between zone types, summarized as a Jaccard index.](../figures/figure_10_zone_overlap_heatmap.png)

*Figure 10. Pairwise spatial overlap between zone types, summarized as a Jaccard index.*

## 4. Does the same area stay in the supply zone every year

A property that supplies a plant only once is a weaker basis for monitoring
than one that supplies it consistently. The workflow tracks, pixel by pixel,
how many of the six years a location falls inside the CA-direct supply zone.

| Years covered out of 6 | Cumulative area (thousand ha) | Share of the ever-covered footprint (%) |
| --- | --- | --- |
| 1 | 1,090.0 | 9.1% |
| 2 | 900.0 | 7.5% |
| 3 | 3,090.0 | 25.8% |
| 4 | 3,640.0 | 30.4% |
| 5 | 2,460.0 | 20.6% |
| 6 | 780.0 | 6.5% |

![Figure 3. Number of years each location falls inside the CA-direct supply zone.](../figures/figure_3_persistence.png)

*Figure 3. Number of years each location falls inside the CA-direct supply zone.*

## 5. What land cover is inside each supply zone

![Figure 4. Land-cover composition inside each supply-zone type.](../figures/figure_4_land_use_composition.png)

*Figure 4. Land-cover composition inside each supply-zone type.*

Natural vegetation, pasture, soybean cropland, and a residual "other" class
are cross-tabulated against each zone type, after excluding officially
protected and military areas from the denominator for the natural-vegetation
figure so that it reflects land that is legally available for conversion.

## 6. Deforestation and carbon inside the CA-direct zone

| Zone type | Deforestation, 2008-2018 (thousand ha) | Committed emissions, 2008-2018 (MtCO2e) |
| --- | --- | --- |
| CA direct | 6.4 | 2.9 |
| CA tier-1 indirect | 0.7 | 0.2 |
| Non-CA direct | 9.5 | 3.6 |
| Non-CA tier-1 indirect | 1.5 | 0.4 |

![Figure S2. Annual synthetic deforestation and committed carbon emissions inside the CA-direct zone, 2008-2018.](../figures/figure_s2_deforestation_carbon.png)

*Figure S2. Annual synthetic deforestation and committed carbon emissions inside the CA-direct zone, 2008-2018.*

## 7. How the supply-zone radius is chosen for each plant and year

Rather than applying one fixed radius to every plant, the workflow tests a
range of distances for each plant-year and keeps the one at which
cattle-volume-weighted spatial clustering is strongest. This makes zones
larger around plants with a spatially concentrated supplier base and smaller
around plants whose suppliers are scattered.

![Figure 5. Correlogram of Moran's I against distance for four example slaughterhouses; the marked point is the distance actually used to build that plant-year's zone.](../figures/figure_5_moran_correlogram.png)

*Figure 5. Correlogram of Moran's I against distance for four example slaughterhouses; the marked point is the distance actually used to build that plant-year's zone.*

## 8. Where does the cattle that leaves a CA-linked property end up

![Figure 7. Destination of cattle heads that leave CA-linked direct properties.](../figures/figure_7_supplier_flows.png)

*Figure 7. Destination of cattle heads that leave CA-linked direct properties.*

Only part of the cattle that leaves a CA-linked direct property is
slaughtered at a CA-signatory plant; the remainder is either slaughtered
elsewhere or moved to another property first, which is exactly the kind of
leakage that indirect-supplier monitoring is designed to catch.

## 9. How far apart are direct suppliers, indirect suppliers, and rival plants

![Figure 8. Distribution of two distance measures: tier-1 indirect supplier to nearest direct supplier, and CA-signatory plant to nearest non-CA plant.](../figures/figure_8_distance_distribution.png)

*Figure 8. Distribution of two distance measures: tier-1 indirect supplier to nearest direct supplier, and CA-signatory plant to nearest non-CA plant.*

## 10. What would happen if monitoring were extended

| Monitoring scenario | Zone area (million ha) | Properties covered | Slaughter volume covered (%) |
| --- | --- | --- | --- |
| Current (CA direct only) | 12.1 | 120 | 56.5% |
| Add CA tier-1 indirect | 13.1 | 136 | 63.4% |
| Add non-CA direct | 18.7 | 170 | 78.3% |
| All direct and tier-1 suppliers | 19.3 | 170 | 78.3% |

![Figure 6. Monitored area and slaughter-volume coverage under four expansion scenarios.](../figures/figure_6_expansion_pathways.png)

*Figure 6. Monitored area and slaughter-volume coverage under four expansion scenarios.*

Adding non-CA direct suppliers to the monitored footprint captures far more
of the slaughter volume in this synthetic scenario than adding tier-1
indirect suppliers of CA-linked plants does, but it also requires monitoring
a substantially larger area, illustrating the coverage-versus-scope trade-off
that any traceability system has to navigate.

## 11. Does the choice of method matter

| Method | Mean zone area (million ha) | Median overestimate vs. this workflow (%) |
| --- | --- | --- |
| Incremental spatial-autocorrelation (this workflow) | 1.1 | - |
| Simple radial buffer around the plant | 11.7 | 1,064.9% |
| Supplier convex-hull proxy | 6.1 | - |

![Figure 9. Zone area under the incremental spatial-autocorrelation method compared with two simpler distance-based proxies.](../figures/figure_9_alternative_methods.png)

*Figure 9. Zone area under the incremental spatial-autocorrelation method compared with two simpler distance-based proxies.*

Simple proxies, such as a fixed-radius buffer around the plant, tend to
overestimate the true supply zone because they ignore the actual geographic
spread of a plant's supplier base; the overestimate is largest, sometimes by
more than an order of magnitude, in plant-years where the true supply zone is
small and tightly clustered. The median is reported above rather than the
mean because a handful of these small-zone plant-years produce extreme
percentage overestimates that would otherwise dominate the average. This is a
methodological caution for anyone tempted to shortcut the distance-selection
step to save computation time.

## 12. Where the supply zone sits geographically, state by state

![Figure 11. Share of each state's territory that falls inside the cumulative CA-direct supply zone.](../figures/figure_11_state_coverage_map.png)

*Figure 11. Share of each state's territory that falls inside the cumulative CA-direct supply zone.*

## 13. Limitations

- **All data are synthetic.** Every property boundary, transaction, and
  slaughterhouse in this repository was generated for testing purposes and
  carries no relationship to actual locations, companies, or individuals.
- **The open-source distance-selection and aggregation methods are declared
  analogues, not certified reproductions,** of the original study's ArcGIS
  Pro routines; see `docs/ARCGIS_EQUIVALENCE.md` for a line-by-line
  comparison of assumptions.
- **Land-use and deforestation layers are simplified** into four classes and
  a single annual raster; the original study's underlying data sources are
  richer.
- **Supplier-hull and radial-buffer comparisons are illustrative proxies**
  built for this repository; they should not be read as a critique of any
  specific commercial GIS workflow.

## 14. How to reproduce every number in this report

```
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m supply_zones all --clean
pytest
```

This regenerates the synthetic input data, reruns every analytical step
described above, rebuilds every figure and table referenced in this report
(including this document itself), and runs the automated QA gates in
`outputs/qa/QA_REPORT.md`.

## Citation

Please cite the original article for the underlying method, and
`CITATION.cff` in this repository for the synthetic reproduction code.
