# Autonomy Checkpoint and Rollback Runbook

## Scope

Use this runbook for autonomy scheduling/cycle incidents:
- checkpoint token mismatches
- stalled or repeated autonomy cycles
- unsafe or partial automation apply/rollback states

## Stabilize

1. Freeze autonomy progression:
   - pause new cycle execution until checkpoint integrity is verified
2. Capture current planner state:
   - `planner_engine` with `action=autonomy_status`
   - `planner_engine` with `action=task_graph_list`
3. Snapshot related orchestration state:
   - `home_orchestrator` with `action=automation_status`
   - `system_status` for expansion/recovery indicators

## Checkpoint Recovery

1. Validate next required checkpoint:
   - `planner_engine` with `action=autonomy_checkpoint`
2. Resume one cycle only after token validation:
   - `planner_engine` with `action=autonomy_cycle`
3. If cycle fails mid-flight:
   - inspect recovery journal and dead-letter signals
   - run `dead_letter_list` for replay candidates

## Rollback Path

1. Generate rollback preview:
   - `home_orchestrator` with `action=automation_rollback`, `execute=false`
2. Execute rollback with explicit approval:
   - `home_orchestrator` with `action=automation_rollback`, `execute=true`
3. Verify post-rollback invariants:
   - `home_orchestrator` with `action=automation_status`
   - `planner_engine` with `action=autonomy_status`

## Exit Criteria

- checkpoint and cycle counters advancing normally
- no interrupted recovery entries remain
- rollback/apply state is internally consistent and auditable
