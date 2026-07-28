from supply_zones.matching import normalize_identifier, normalize_text


def test_text_normalization_is_deterministic():
    assert normalize_text("Fazenda São João, Ltda.") == "FAZENDA SAO JOAO LTDA"


def test_identifier_normalization_removes_punctuation():
    assert normalize_identifier("12.345.678/0001-90") == "12345678000190"

