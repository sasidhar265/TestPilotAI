.PHONY: install quality lint format format-check type audit test run

install:
	python3 -m pip install -e '.[dev]'

lint:
	ruff check app tests

format-check:
	ruff format --check app tests

format:
	ruff format app tests
	ruff check --fix app tests

type:
	mypy app

audit:
	pip-audit .

test:
	pytest --cov=app --cov-report=term-missing

quality: format-check lint type audit test
	python3 -m compileall -q app tests

run:
	uvicorn app.main:app --reload
