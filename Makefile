.PHONY: check test-fast test-faults test-fault-profiles test-soak security-gate

check:
	uv run ruff check src tests
	uv run pytest -q

test-fast:
	uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools_robot.py tests/test_tools_services.py

test-faults:
	./scripts/test_faults.sh

test-fault-profiles:
	./scripts/run_fault_profiles.sh all

test-soak:
	uv run pytest -q tests/test_main_audio.py -k soak

security-gate:
	./scripts/security_gate.sh
