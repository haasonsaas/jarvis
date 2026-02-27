.PHONY: check test-fast test-sim test-sim-acceptance test-faults test-fault-profiles test-fault-campaign test-soak test-soak-reliability test-soak-extended test-soak-campaign test-personality security-gate \
	bootstrap quality-report eval-dataset quality-trend-gate release-channel-check release-acceptance readiness

check:
	uv run ruff check src tests
	uv run pytest -q

test-fast:
	uv run pytest -q tests/test_config.py tests/test_memory.py tests/test_tools_robot.py tests/test_tools_services.py

test-sim:
	./scripts/test_sim.sh

test-sim-acceptance:
	./scripts/test_sim_acceptance.sh fast 1

test-faults:
	./scripts/test_faults.sh

test-fault-profiles:
	./scripts/run_fault_profiles.sh all

test-fault-campaign:
	./scripts/test_fault_campaign.sh quick,network,storage,contract 2

test-soak:
	./scripts/test_soak.sh

test-soak-reliability:
	./scripts/test_soak_reliability.sh

test-soak-extended:
	./scripts/test_soak_extended.sh full

test-soak-campaign:
	./scripts/test_soak_campaign.sh full 2

test-personality:
	./scripts/test_personality.sh

security-gate:
	./scripts/security_gate.sh

bootstrap:
	./scripts/bootstrap.sh

quality-report:
	./scripts/generate_quality_report.py --output-dir .artifacts/quality --markdown

eval-dataset:
	./scripts/run_eval_dataset.py docs/evals/assistant-contract.json --output .artifacts/quality/eval.json --strict --min-cases 250 --require-unique-ids --require-expected-tools

quality-trend-gate:
	./scripts/check_quality_trends.py

release-channel-check:
	./scripts/check_release_channel.py --channel stable

release-acceptance:
	./scripts/release_acceptance.sh fast

readiness:
	./scripts/jarvis_readiness.sh fast
