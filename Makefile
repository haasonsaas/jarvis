.PHONY: check test-fast test-faults test-soak

check:
	uv run ruff check src tests
	uv run pytest -q

test-fast:
	uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools.py

test-faults:
	./scripts/test_faults.sh

test-soak:
	uv run pytest -q tests/test_main_audio.py -k soak
