.PHONY: install test lint format clean build publish

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check heliox_cli/

format:
	ruff format heliox_cli/ tests/

clean:
	rm -rf dist/ build/ *.egg-info .pytest_cache __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

build:
	pip install build --quiet
	python -m build

publish: build
	pip install twine --quiet
	twine upload dist/*
