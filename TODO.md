# Jarvis Feature Expansion TODO (Research-Backed)

Last updated: 2026-02-26

This backlog replaces the completed hardening backlog and focuses on feature gaps found by comparing Jarvis against modern local assistant ecosystems (Home Assistant Assist/Conversation APIs, OVOS/Rhasspy-style voice stacks, and multi-surface assistants).

## Status legend
- `[ ]` Not started
- `[-]` In progress
- `[x]` Implemented

## Priority model
- `P0`: core product gaps that materially block daily use
- `P1`: major capabilities that unlock scale and ecosystem fit
- `P2`: quality/operational improvements after core gaps are closed

---

## 1) Voice Attention and Conversation Control (10 items)

- [ ] `VA01` Add local wake-word support with configurable hotwords.
- [ ] `VA02` Add wake-word sensitivity tuning and false-positive suppression.
- [ ] `VA03` Add explicit sleep/wake modes (`always_listening`, `wake_word`, `push_to_talk`).
- [ ] `VA04` Add interruption policy controls (barge-in thresholds per mode).
- [ ] `VA05` Add per-room attention routing signals (when satellites are introduced).
- [ ] `VA06` Add configurable end-of-turn timeout profiles (short/normal/long).
- [ ] `VA07` Add “continue listening” follow-up window for multi-turn voice sessions.
- [ ] `VA08` Add spoken confirmation grammar for dangerous actions (`confirm/deny/repeat`).
- [ ] `VA09` Add wake-word and attention state visibility to `system_status`.
- [ ] `VA10` Add voice state regression tests for wake/sleep/listen transitions.

---

## 2) Home Assistant Native Intent Layer (10 items)

- [x] `HA01` Add Home Assistant conversation API tool (`/api/conversation/process`) for intent-level commands.
- [x] `HA02` Add optional language/agent parameters for HA conversation calls.
- [x] `HA03` Add structured response extraction from HA conversation payloads.
- [ ] `HA04` Add Home Assistant to-do list integration tool path.
- [ ] `HA05` Add Home Assistant timer integration tool path.
- [ ] `HA06` Add entity capability discovery helper for safer action planning.
- [ ] `HA07` Add optional area-aware commands (room/area targeting helper).
- [x] `HA08` Add HA conversation error taxonomy mapping and tests.
- [x] `HA09` Add policy profile controls for HA intent tool (`readonly|control`).
- [ ] `HA10` Add HA intent runbook section with safe rollout checklist.

---

## 3) Productivity Primitives (Timers, Reminders, Calendar) (10 items)

- [x] `PR01` Add timer creation tool with natural duration parsing (`5m`, `90s`, `1h`).
- [x] `PR02` Add timer listing tool with remaining-time reporting.
- [x] `PR03` Add timer cancel tool (by id and optionally by label).
- [ ] `PR04` Add lightweight reminder creation tool with due timestamp parsing.
- [ ] `PR05` Add reminder listing and completion flow.
- [ ] `PR06` Add optional reminder notifications via Pushover.
- [ ] `PR07` Add calendar read integration (Google/ICS or HA calendar bridge).
- [ ] `PR08` Add “next event” conversational helper tool.
- [x] `PR09` Add persistence layer for timers/reminders across restarts.
- [ ] `PR10` Add productivity tool regression tests and edge-case parsing tests.

---

## 4) Identity, Permissions, and Trust Controls (8 items)

- [ ] `ID01` Add user identity abstraction for voice/text request contexts.
- [ ] `ID02` Add per-user permission profiles layered over global policy.
- [ ] `ID03` Add approval handshake flow for high-risk commands.
- [ ] `ID04` Add trusted-speaker shortcut path (optional biometric/speaker-id hook point).
- [ ] `ID05` Add denied-action escalation guidance in user-facing responses.
- [ ] `ID06` Add audit fields for requester identity and decision reason chain.
- [ ] `ID07` Add tests for per-user allow/deny precedence.
- [ ] `ID08` Add trust policy runbook for household/shared deployments.

---

## 5) Integrations and Channel Surface Expansion (8 items)

- [ ] `IN01` Add weather integration tool (provider-backed, configurable units).
- [ ] `IN02` Add email summary/send integration with strict safety policy.
- [ ] `IN03` Add Slack/Discord notification hooks (opt-in).
- [ ] `IN04` Add webhook trigger tool with domain allowlist and auth controls.
- [ ] `IN05` Add webhook inbound receiver for automation callbacks.
- [ ] `IN06` Add media-control abstraction helper over HA media player actions.
- [ ] `IN07` Add integration health probes surfaced in `system_status`.
- [ ] `IN08` Add integration contract tests for each external service.

---

## 6) Skills and Extensibility Architecture (8 items)

- [ ] `SK01` Add local skill/plugin discovery mechanism for service tools.
- [ ] `SK02` Add signed/allowlisted skill loading policy.
- [ ] `SK03` Add skill lifecycle commands (`enable`, `disable`, `list`, `version`).
- [ ] `SK04` Add stable tool namespace conventions for third-party skills.
- [ ] `SK05` Add skill capability metadata surfacing in `system_status`.
- [ ] `SK06` Add skill sandboxing constraints for network/file access.
- [ ] `SK07` Add integration tests for plugin load failures and graceful degradation.
- [ ] `SK08` Add developer docs for writing and validating custom skills.

---

## 7) Operator UX and Control Surfaces (8 items)

- [ ] `UX01` Add minimal local web dashboard for runtime health and mode toggles.
- [ ] `UX02` Add live view of recent tool executions and policy outcomes.
- [ ] `UX03` Add audit viewer with server-side redaction guarantees.
- [ ] `UX04` Add quick controls for motion/tts/home tools/wake mode.
- [ ] `UX05` Add startup diagnostics page for missing/invalid config.
- [ ] `UX06` Add structured JSON status endpoint for automation consumers.
- [ ] `UX07` Add operator actions log in dashboard (who changed what, when).
- [ ] `UX08` Add dashboard responsiveness tests (desktop/mobile).

---

## 8) Observability and Diagnostics (8 items)

- [ ] `OB01` Add persistent telemetry storage for long-range trend analysis.
- [ ] `OB02` Add metrics export endpoint (Prometheus/OpenMetrics format).
- [ ] `OB03` Add percentile latency tracking (P50/P95/P99) for STT/LLM/TTS.
- [ ] `OB04` Add structured event stream for state transitions.
- [ ] `OB05` Add per-tool success/error rate snapshots over rolling windows.
- [ ] `OB06` Add crash-restart counters and uptime tracking.
- [ ] `OB07` Add anomaly detection hooks for repeated failure bursts.
- [ ] `OB08` Add observability runbook for triage and SLO tuning.

---

## 9) Reliability, Fallbacks, and Runtime Resilience (8 items)

- [ ] `RE01` Add model failover strategy (primary/secondary LLM routing).
- [ ] `RE02` Add STT fallback chain and capability probes.
- [ ] `RE03` Add TTS fallback chain (cloud/local optional).
- [ ] `RE04` Add startup self-check gate with actionable failure messages.
- [ ] `RE05` Add degraded mode responses when integrations are down.
- [ ] `RE06` Add watchdog for stuck state loops (listening/thinking/speaking).
- [ ] `RE07` Add graceful restart support preserving pending work items.
- [ ] `RE08` Add soak tests covering failover and degraded behavior.

---

## 10) Security, Privacy, and Deployment Hygiene (8 items)

- [ ] `SE01` Add encrypted-at-rest option for memory/audit stores.
- [ ] `SE02` Add configurable data retention windows for memory/audit data.
- [ ] `SE03` Add PII detection guardrails for memory writes.
- [ ] `SE04` Add stricter token-scoping validation warnings on startup.
- [ ] `SE05` Add outbound request domain allowlist enforcement for webhooks.
- [ ] `SE06` Add signed release artifact verification and provenance docs.
- [ ] `SE07` Add deploy-time security checklist automation.
- [ ] `SE08` Add incident response runbook with rollback playbooks.

---

## 11) Immediate Execution Queue (Top-Down)

- [x] `E01` Implement `HA01` + `HA02` + `HA03` (Home Assistant conversation API tool + schema + mapping + tests).
- [x] `E02` Implement `PR01` + `PR02` + `PR03` (timer create/list/cancel tools + tests + status exposure).
- [x] `E03` Implement `HA08` + `HA09` (policy and taxonomy mapping for HA intent tool).
- [x] `E04` Implement `PR09` (persist timer/reminder data in `MemoryStore`).
- [ ] `E05` Implement `UX06` (structured status endpoint behavior contract).
- [x] `E06` Update README/runbooks for new tools and safe operating guidance.
