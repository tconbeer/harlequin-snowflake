CONNECTION ?= $(HARLEQUIN_SNOWFLAKE_TEST_CONNECTION)

.PHONY: check
check:
	uv run ruff format .
	uv run ruff check . --fix
	uv run mypy
	uv run pytest

.PHONY: init
init:
	uv sync

.PHONY: test
test:
	uv run pytest -m "not integration"

.PHONY: integration
integration:
	uv run pytest -m integration

.PHONY: lint
lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy

.PHONY: clean
clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache profile.html
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

# With no CONNECTION, Harlequin uses the default profile in .harlequin.toml.
.PHONY: serve
serve:
	uv run harlequin $(CONNECTION)

.PHONY: build
build:
	uv build

profile.html: $(wildcard src/**/*.py)
	uv run pyinstrument -r html -o profile.html --from-path harlequin $(CONNECTION)
