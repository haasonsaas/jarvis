.PHONY: check test-fast test-sim test-sim-acceptance test-faults test-fault-profiles test-fault-campaign test-fault-chaos test-soak test-soak-reliability test-soak-extended test-soak-campaign test-personality security-gate \
		bootstrap quality-report eval-dataset router-eval interruption-eval trace-eval trace-synth-eval autonomy-eval memory-eval runtime-outcome-gate quality-trend-gate release-channel-check release-acceptance readiness

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

test-fault-chaos:
	./scripts/test_fault_chaos.sh quick,network,storage,contract 2

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

router-eval:
	./scripts/run_router_policy_eval.py docs/evals/router-policy-contract.json --output .artifacts/quality/router-eval.json --strict --min-cases 20 --require-unique-ids

interruption-eval:
	./scripts/run_interruption_route_eval.py docs/evals/interruption-route-contract.json --output .artifacts/quality/interruption-eval.json --strict --min-cases 20 --require-unique-ids

trace-eval:
	./scripts/run_trace_trajectory_eval.py docs/evals/trajectory-trace-contract.json --output .artifacts/quality/trace-eval.json --strict --min-cases 10 --require-unique-ids

trace-synth-eval:
	./scripts/synthesize_trace_eval_dataset.py .artifacts/quality/conversation-trace.json --output .artifacts/quality/trajectory-trace-generated.json --max-cases 200 --max-turns-per-case 12

autonomy-eval:
	./scripts/run_autonomy_cycle_eval.py docs/evals/autonomy-cycle-contract.json --output .artifacts/quality/autonomy-eval.json --strict --min-cases 10 --require-unique-ids

memory-eval:
	uv run python scripts/run_memory_quality_eval.py docs/evals/memory-quality-contract.json --output .artifacts/quality/memory-eval.json --strict --min-pass-rate 0.8 --max-failed 1 --min-cases 5 --require-unique-ids --llm-judge on --conflict-resolution on --min-avg-judge-score 0.7

runtime-outcome-gate:
	uv run python scripts/run_runtime_outcome_gate.py --output .artifacts/quality/runtime-outcome-gate.json --strict --min-pass-rate 1.0 --max-failed 0

quality-trend-gate:
	./scripts/check_quality_trends.py

release-channel-check:
	./scripts/check_release_channel.py --channel stable

release-acceptance:
	./scripts/release_acceptance.sh fast

readiness:
	./scripts/jarvis_readiness.sh fast
