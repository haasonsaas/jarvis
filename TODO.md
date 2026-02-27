# Jarvis Next TODO (Broad Product Roadmap)

Last updated: 2026-02-27

This is a fresh roadmap focused on what is still missing for a "feels-like-Jarvis" assistant: proactive behavior, stronger presence, richer multi-user trust, deeper home intelligence, and production-grade operations.

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

## Priority model
- `P0`: must-have for daily "Jarvis" experience
- `P1`: major capability expansion
- `P2`: polish, scale, and ecosystem hardening

## Previous backlog status
- Prior hardening/integration backlog was completed before this roadmap.
- This file now tracks only next-stage product expansion work.

---

## 1) Core Jarvis Experience (6 items)

- [x] `JX01` Define a concrete "Jarvis interaction contract" (tone, brevity, initiative, boundaries) and enforce it in system prompts. `P0`
- [x] `JX02` Add dynamic response mode switching (`brief`, `normal`, `deep`) based on user context and urgency. `P0`
- [x] `JX03` Add context-aware first-response behavior (acknowledge, answer, act, or ask clarifying question). `P0`
- [x] `JX04` Add confidence-aware language policy to avoid overconfident answers when uncertain. `P0`
- [ ] `JX05` Add "operator personality controls" with live preview and rollback. `P1`
- [x] `JX06` Add "Jarvis quality bar" regression checks for tone/style consistency across common prompts. `P1`

## 2) Voice and Dialogue Quality (6 items)

- [x] `VX01` Add robust wake-word false-trigger suppression with environment-specific calibration profiles. `P0`
- [x] `VX02` Add adaptive end-of-turn timing based on speaking rate and interruption likelihood. `P0`
- [x] `VX03` Add explicit "follow-up intent carryover" so multi-turn requests preserve unresolved slots. `P0`
- [ ] `VX04` Add per-user voice preferences (pace, verbosity, confirmations). `P1`
- [ ] `VX05` Add runtime STT confidence diagnostics in operator UI and status endpoints. `P1`
- [ ] `VX06` Add conversation repair loops ("I misheard X, did you mean Y?") with minimal friction. `P1`

## 3) Proactive Assistant Behavior (6 items)

- [ ] `PX01` Add proactive briefing engine (morning/evening) built from calendar, reminders, weather, and home state. `P0`
- [ ] `PX02` Add proactive anomaly notifications (device offline, unusual temp, missed reminder). `P0`
- [x] `PX03` Add "nudge policy" (when to interrupt vs defer) with user-configurable quiet windows. `P0`
- [ ] `PX04` Add routine suggestions based on repeated behavior patterns (opt-in only). `P1`
- [ ] `PX05` Add proactive follow-through ("I can do that now" for pending tasks after confirmations). `P1`
- [ ] `PX06` Add proactive event summarization with digest and snooze controls. `P1`

## 4) Memory and Personalization (6 items)

- [x] `MX01` Add scoped long-term memory classes (`preferences`, `people`, `projects`, `household_rules`) with explicit retrieval policy. `P0`
- [x] `MX02` Add "memory confidence" and "source trail" to prevent stale or hallucinated recall. `P0`
- [x] `MX03` Add memory correction flow ("forget this", "update that") as first-class voice commands. `P0`
- [ ] `MX04` Add episodic timeline snapshots for recent important conversations/actions. `P1`
- [ ] `MX05` Add per-user memory partitions with shared/common memory overlays. `P1`
- [ ] `MX06` Add memory quality audits (duplication, contradiction, stale data) with cleanup tools. `P1`

## 5) Multi-User Identity and Trust (6 items)

- [ ] `IX01` Add session-level identity confidence score from voice context + operator hints. `P0`
- [ ] `IX02` Add per-user trust policies for high-risk domains (locks, alarms, purchases, external messages). `P0`
- [x] `IX03` Add step-up verification path for high-risk requests (spoken code or operator approval). `P0`
- [ ] `IX04` Add "guest mode" with constrained capabilities and automatic expiry. `P1`
- [ ] `IX05` Add household profile management in operator UI (users, roles, trust, exceptions). `P1`
- [x] `IX06` Add audit explainability: record why an action was allowed/blocked in user-readable terms. `P1`

## 6) Home Intelligence and Automation (6 items)

- [ ] `HX01` Add intent-to-plan decomposition for complex home requests ("movie mode", "bedtime routine"). `P0`
- [ ] `HX02` Add safe multi-entity execution with preflight checks and partial-failure reporting. `P0`
- [ ] `HX03` Add area-level policy constraints (e.g., no loud actions in bedroom after quiet hours). `P0`
- [ ] `HX04` Add Home Assistant automation suggestion mode with review before creation. `P1`
- [ ] `HX05` Add long-running home task tracking (start, in-progress, completed) in status and operator UI. `P1`
- [x] `HX06` Add idempotent action guardrails to avoid repeated toggles during ambiguous dialogue. `P1`

## 7) Operator Surfaces and Control (6 items)

- [ ] `OX01` Add operator auth mode options (`off`, `token`, `session`) with explicit startup warnings by risk level. `P0`
- [ ] `OX02` Add signed operator action records for tamper-evident operations trail. `P1`
- [x] `OX03` Add live "conversation trace" panel (turn flow, tool calls, policy decisions, latencies). `P1`
- [x] `OX04` Add operator "safe mode" toggle that forces dry-run behavior globally. `P0`
- [ ] `OX05` Add control presets (`quiet hours`, `demo mode`, `maintenance mode`) with one-click activation. `P1`
- [ ] `OX06` Add export/import for operator settings and runtime profiles. `P2`

## 8) Skills Ecosystem and Extensibility (6 items)

- [ ] `SX01` Add skill capability negotiation so planner can reason about tool quality and reliability. `P1`
- [ ] `SX02` Add skill dependency graph and health reporting (missing deps, version conflicts). `P1`
- [ ] `SX03` Add per-skill runtime quotas (rate, CPU time, outbound calls). `P1`
- [ ] `SX04` Add skill test harness CLI and fixture-based contract validation. `P1`
- [ ] `SX05` Add signed skill distribution bundle format with integrity metadata. `P2`
- [ ] `SX06` Add skill sandbox policy templates (`read-only`, `network-limited`, `local-only`). `P1`

## 9) Planning and Autonomy (6 items)

- [ ] `AX01` Add explicit planner/executor split with retry policy and rollback hints. `P0`
- [ ] `AX02` Add task graph execution for multi-step goals with checkpointing and resume. `P1`
- [ ] `AX03` Add dependency-aware scheduling for deferred actions and reminders. `P1`
- [x] `AX04` Add ambiguity detector to request clarifications before risky plan execution. `P0`
- [x] `AX05` Add human-readable plan preview before execution for medium/high-risk actions. `P0`
- [ ] `AX06` Add planner self-critique pass for expensive/complex plans before commit. `P2`

## 10) Reliability and Runtime Safety (6 items)

- [x] `RX01` Add per-integration circuit breakers with cooldown/backoff state in status. `P0`
- [x] `RX02` Add persistent recovery journal for interrupted actions and post-restart reconciliation. `P0`
- [ ] `RX03` Add dead-letter queue for failed outbound notifications/webhooks with replay controls. `P1`
- [x] `RX04` Add stricter timeout budgets per turn phase (listen/think/speak/act). `P0`
- [ ] `RX05` Add chaos/fault profile runner in CI for scheduled resilience regression tests. `P1`
- [ ] `RX06` Add runtime invariant checks to detect impossible state combinations and auto-heal. `P1`

## 11) Observability and Evaluation (6 items)

- [x] `EX01` Add intent-level success metrics (answer quality, completion success, correction frequency). `P0`
- [ ] `EX02` Add percentile dashboards for end-to-end turn latency by mode and tool mix. `P1`
- [ ] `EX03` Add policy-decision analytics (allow/deny reason distribution by user and tool). `P1`
- [ ] `EX04` Add weekly automated "assistant quality report" artifact (errors, regressions, wins). `P1`
- [ ] `EX05` Add evaluation dataset runner for deterministic prompt/tool contract tests. `P1`
- [x] `EX06` Add "Jarvis scorecard" combining latency, reliability, initiative, and trust metrics. `P1`

## 12) Embodiment and Presence (6 items)

- [ ] `BX01` Add richer stateful micro-expression library mapped to dialogue intent and certainty. `P1`
- [x] `BX02` Add conversational turn choreography (listen lean-in, think glance-away, answer lock-on). `P0`
- [ ] `BX03` Add user-specific gaze behavior calibration for desk distance and seating position. `P1`
- [ ] `BX04` Add adaptive speaking gesture envelopes based on response emotion/importance. `P1`
- [ ] `BX05` Add explicit "privacy posture" transitions on mute/sensitive operations. `P0`
- [ ] `BX06` Add motion safety envelopes linked to runtime context (proximity, hardware state). `P0`

## 13) Integrations and Productivity Surface (6 items)

- [ ] `GX01` Add richer calendar actions (create/update/delete with confirmation policy). `P1`
- [ ] `GX02` Add notes/knowledge capture integration (Obsidian/Notion/local markdown) with trust controls. `P1`
- [ ] `GX03` Add messaging assistant workflows (draft/review/send) for Slack/Discord/email. `P1`
- [ ] `GX04` Add commute/travel briefing integration (traffic/transit APIs). `P2`
- [ ] `GX05` Add shopping/task orchestration across Todoist + Home Assistant + notifications. `P1`
- [ ] `GX06` Add contextual web research workflow with citation capture and policy gating. `P2`

## 14) Packaging, Deployment, and Ecosystem Fit (6 items)

- [ ] `DX01` Add one-command local install/bootstrap script for clean hosts. `P1`
- [ ] `DX02` Add containerized deployment profile for always-on home-server runtime. `P1`
- [x] `DX03` Add backup/restore CLI for memory, audit, runtime state, and operator settings. `P1`
- [ ] `DX04` Add staged release channels (`dev`, `beta`, `stable`) with migration checks. `P2`
- [ ] `DX05` Add Home Assistant add-on packaging path and setup guide. `P2`
- [ ] `DX06` Add release acceptance suite focused on "Jarvis feel" scenarios before ship. `P1`

---

## Immediate Execution Queue (First 20)

- [x] `Q01` Implement `JX01` interaction contract + prompt enforcement.
- [x] `Q02` Implement `AX04` ambiguity detector for risky actions.
- [x] `Q03` Implement `AX05` plan preview before medium/high-risk execution.
- [x] `Q04` Implement `RX04` turn-phase timeout budgets and status exposure.
- [x] `Q05` Implement `PX03` nudge/interrupt policy + quiet windows.
- [x] `Q06` Implement `MX03` memory correction voice commands.
- [x] `Q07` Implement `IX03` step-up verification flow.
- [x] `Q08` Implement `HX06` idempotent home-action guardrail.
- [x] `Q09` Implement `OX04` global safe-mode toggle.
- [x] `Q10` Implement `EX01` intent-level success metrics.
- [x] `Q11` Implement `BX02` turn choreography pass.
- [x] `Q12` Implement `VX02` adaptive end-of-turn timing.
- [x] `Q13` Implement `JX06` style consistency regression tests.
- [x] `Q14` Implement `RX01` integration circuit breakers.
- [x] `Q15` Implement `RX02` recovery journal and resume.
- [x] `Q16` Implement `OX03` conversation trace panel.
- [x] `Q17` Implement `MX02` memory confidence/source trail.
- [x] `Q18` Implement `IX06` readable audit explainability.
- [x] `Q19` Implement `DX03` backup/restore CLI.
- [x] `Q20` Implement `EX06` unified Jarvis scorecard.
