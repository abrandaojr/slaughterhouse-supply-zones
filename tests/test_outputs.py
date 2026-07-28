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
        "outputs/report/REPORT.md",
        "outputs/figures/figure_4_land_use_composition.png",
        "outputs/figures/figure_5_moran_correlogram.png",
        "outputs/figures/figure_6_expansion_pathways.png",
        "outputs/figures/figure_7_supplier_flows.png",
        "outputs/figures/figure_8_distance_distribution.png",
        "outputs/figures/figure_9_alternative_methods.png",
        "outputs/figures/figure_10_zone_overlap_heatmap.png",
        "outputs/figures/figure_11_state_coverage_map.png",
    ]
    missing = [item for item in expected if not (root / item).exists()]
    assert not missing, f"Run `python -m supply_zones all --clean`; missing: {missing}"


def test_report_contains_all_expected_sections():
    root = Path(__file__).resolve().parents[1]
    report_path = root / "outputs" / "report" / "REPORT.md"
    assert report_path.exists(), "Run `python -m supply_zones all --clean` or `python -m supply_zones report`"
    text = report_path.read_text(encoding="utf-8")
    expected_headings = [
        "Executive summary",
        "Why supply zones matter",
        "Study design in brief",
        "How large are supply zones",
        "Does the same area stay in the supply zone every year",
        "What land cover is inside each supply zone",
        "Deforestation and carbon inside the signatory direct zone",
        "How the supply-zone radius is chosen",
        "Where does the cattle that leaves a signatory property end up",
        "How far apart are direct suppliers",
        "What would happen if monitoring were extended",
        "Does the choice of method matter",
        "Where the supply zone sits geographically",
        "Limitations",
        "How to reproduce every number in this report",
    ]
    missing_sections = [heading for heading in expected_headings if heading not in text]
    assert not missing_sections, f"Missing report sections: {missing_sections}"
    assert "fictitious" in text.lower()

