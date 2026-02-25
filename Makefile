.PHONY: check test-fast test-faults test-soak

check:
	uv run ruff check src tests
	uv run pytest -q

test-fast:
	uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools.py

test-faults:
	uv run pytest -q tests/test_tools.py -k "timeout or cancelled or invalid_json or storage_error or unavailable"

test-soak:
	uv run pytest -q tests/test_main_audio.py -k soak
