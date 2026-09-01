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
	@test -n "$(CONNECTION)" || { \
		echo "Set HARLEQUIN_SNOWFLAKE_TEST_CONNECTION to the name of a"; \
		echo "connections.toml entry, or pass CONNECTION=<name>."; \
		exit 1; \
	}
	HARLEQUIN_SNOWFLAKE_TEST_CONNECTION=$(CONNECTION) uv run pytest -m integration

.PHONY: lint
lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy

.PHONY: clean
clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache profile.html
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +

.PHONY: serve
serve:
	uv run harlequin -P None -a snowflake $(CONNECTION)

.PHONY: sql
sql:
	uv run python -m snowflake.connector.cli --connection-name $(CONNECTION) 2>/dev/null \
		|| echo "Install the Snowflake CLI (snow sql -c $(CONNECTION)) for a REPL."

.PHONY: build
build:
	uv build

profile.html: $(wildcard src/**/*.py)
	uv run pyinstrument -r html -o profile.html --from-path harlequin -a snowflake $(CONNECTION)
