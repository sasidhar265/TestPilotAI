.PHONY: install quality lint format format-check type audit test run

PRETTIER = npx --yes prettier@3.6.2
PRETTIER_SCOPE = . --ignore-unknown --ignore-path .gitignore --ignore-path .prettierignore
CSHARP_FILES = $(shell git ls-files --cached --others --exclude-standard -- '*.cs')
CSHARP_FORMAT = dotnet format whitespace . --folder --include $(CSHARP_FILES)

install:
	python3 -m pip install -e '.[dev]'

lint:
	ruff check app tests

format-check:
	ruff format --check app tests tools
	$(PRETTIER) --check $(PRETTIER_SCOPE)
	$(CSHARP_FORMAT) --verify-no-changes

format:
	ruff format app tests tools
	$(PRETTIER) --write $(PRETTIER_SCOPE)
	$(CSHARP_FORMAT)

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
