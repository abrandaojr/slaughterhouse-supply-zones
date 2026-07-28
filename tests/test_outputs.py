from pathlib import Path


def test_complete_run_outputs_exist():
    root = Path(__file__).resolve().parents[1]
    expected = [
        "data/raw/synthetic_inputs.gpkg",
        "data/raw/gta_transactions.csv",
        "outputs/spatial/supply_zones.gpkg",
        "outputs/tables/zone_overlap.csv",
        "outputs/tables/expansion_pathways.csv",
        "outputs/figures/figure_1_study_area.png",
        "outputs/qa/qa_report.json",
    ]
    missing = [item for item in expected if not (root / item).exists()]
    assert not missing, f"Run `python -m supply_zones all --clean`; missing: {missing}"

