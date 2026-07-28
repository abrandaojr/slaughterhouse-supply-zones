# Synthetic data dictionary

## `data/raw/gta_transactions.csv`

| Field | Meaning |
|---|---|
| `transaction_id` | Unique fictitious movement identifier |
| `year` | Movement year, 2013–2018 |
| `origin_gta_property_id` | Fictitious GTA establishment of origin |
| `destination_type` | `property` or `slaughterhouse` |
| `destination_id` | Fictitious receiving establishment |
| `purpose` | `slaughter`, `fattening`, `breeding`, or `other` |
| `heads` | Number of cattle in the movement |

## `data/raw/gta_properties.csv`

Contains the GTA-side owner, establishment, municipality, state, and identifier fields used for deterministic linkage.

## `data/raw/synthetic_inputs.gpkg`

| Layer | Contents |
|---|---|
| `study_area` | Union of the configured administrative units (three fictitious Brazilian states by default) |
| `states` | Administrative unit polygons (`state` code, `state_name`, geometry); real OpenStreetMap boundaries when available, otherwise a deterministic offline fallback |
| `biomes` | Simplified fictitious Amazon, Cerrado, and Pantanal partitions (labels and extents configurable in `config.yml`) |
| `protected_areas` | Fictitious Conservation Unit and Indigenous Land polygons |
| `military_areas` | Fictitious military polygon |
| `slaughterhouses` | Plant location, inspection, and signatory (CA) status |
| `car_properties` | CAR-like property polygons and linkage attributes |
| `deforestation` | PRODES-like polygons, year, biome, area, and carbon density |

## Rasters

- `land_use_2018.tif`: 0 nodata, 1 natural vegetation, 2 pasture, 3 soybean, 4 other.
- `biomass_carbon_2018.tif`: fictitious Mg C/ha sampled within each clipped deforestation polygon to estimate committed emissions.

## Derived spatial files

- `data/interim/linked_properties.gpkg`: unambiguous GTA–CAR links.
- `data/interim/analytical_suppliers.gpkg`: supplier and eligible-slaughterhouse layers.
- `outputs/spatial/supply_zones.gpkg`: annual slaughterhouse zones.
- `outputs/spatial/analysis_layers.gpkg`: annual and 2013–2018 cumulative unions.
- `outputs/spatial/ca_direct_persistence.tif`: number of years each cell falls inside cumulative annual CA direct zones.
