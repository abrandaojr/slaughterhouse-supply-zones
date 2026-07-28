.PHONY: install reproduce test clean

install:
	python -m pip install -e ".[dev]"

reproduce:
	python -m supply_zones all --clean

test:
	pytest

clean:
	python -m supply_zones clean

