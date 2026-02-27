.PHONY: check test-fast test-sim test-faults test-fault-profiles test-soak test-soak-reliability test-soak-extended test-personality security-gate \
	bootstrap quality-report eval-dataset release-channel-check release-acceptance readiness

check:
	uv run ruff check src tests
	uv run pytest -q

test-fast:
	uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools_robot.py tests/test_tools_services.py

test-sim:
	./scripts/test_sim.sh

test-faults:
	./scripts/test_faults.sh

test-fault-profiles:
	./scripts/run_fault_profiles.sh all

test-soak:
	./scripts/test_soak.sh

test-soak-reliability:
	./scripts/test_soak_reliability.sh

test-soak-extended:
	./scripts/test_soak_extended.sh full

test-personality:
	./scripts/test_personality.sh

security-gate:
	./scripts/security_gate.sh

bootstrap:
	./scripts/bootstrap.sh

quality-report:
	./scripts/generate_quality_report.py --output-dir .artifacts/quality --markdown

eval-dataset:
	./scripts/run_eval_dataset.py docs/evals/assistant-contract.json --output .artifacts/quality/eval.json --strict

release-channel-check:
	./scripts/check_release_channel.py --channel stable

release-acceptance:
	./scripts/release_acceptance.sh fast

readiness:
	./scripts/jarvis_readiness.sh fast
