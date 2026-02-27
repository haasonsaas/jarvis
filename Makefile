.PHONY: check test-fast test-faults test-fault-profiles test-soak security-gate \
	bootstrap quality-report eval-dataset release-channel-check release-acceptance readiness

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
