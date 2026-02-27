# Jarvis — AI Assistant on Reachy Mini

An embodied AI assistant inspired by Jarvis from Iron Man, running on the
[Reachy Mini](https://huggingface.co/reachy-mini) robot with Claude as its brain.

## Design Principles

1. **Latency is king.** First audible response within 300-600ms (filler or real).
   Full answer streams after. People forgive dumb; they don't forgive slow.

2. **Presence, not request/response.** A continuous 30Hz "presence loop" runs
   independent of the LLM — breathing, micro-nods, gaze tracking. The robot
   feels alive even when silent.

3. **Embodiment as policy, not library calls.** The LLM outputs an "embodiment
   plan" (intent, prosody, motion primitives) with each response. A renderer
   maps those to physical behavior. No random "play happy" uncanny valley.

4. **Barge-in.** User can interrupt at any time. TTS stops immediately, new
   utterance is captured. This single behavior makes it feel 10x more real.

5. **Guardrails.** Destructive smart home actions use dry-run by default.
   Everything is audit-logged. Permissions model for sensitive operations.

6. **Honest state broadcasting.** It's obvious when Jarvis is listening vs idle
   vs muted, through posture and behavior, not just an LED.

## Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                      PRESENCE LOOP (30Hz)                         │
│  Always running. Receives lightweight signals, outputs motion.    │
│                                                                   │
│  Signals in:              States:                                 │
│    vad_energy ──┐          IDLE     → breathing, drift            │
│    doa_angle  ──┤          LISTENING → orient, micro-nods, lean   │
│    face_pos   ──┼────────► THINKING → look away, processing anim │
│    llm_state  ──┤          SPEAKING → stable gaze, intent motion  │
│    embody_cmd ──┘          MUTED    → privacy posture             │
└───────────────────────────────────────────────────────────────────┘

┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Audio Input    │     │   Claude Brain    │     │   Audio Output  │
│                  │     │                  │     │                  │
│  Mic → VAD ──────┼────►│  Agent SDK       │────►│  Stream TTS     │
│       ↓          │     │  + MCP tools:    │     │  (ElevenLabs)   │
│  Whisper STT ────┼────►│    embody/robot │     │                  │
│                  │     │    smart_home/* │     │  Barge-in:      │
│  Barge-in: ◄─────┼─────│    todoist/*    │◄────│  VAD interrupts │
│  stop TTS        │     │    memory/*     │     │  playback       │
└─────────────────┘     └──────────────────┘     └─────────────────┘

┌──────────────────┐     ┌──────────────────┐
│  Face Tracker    │     │   Audit Log      │
│  YOLOv8 → face   │────►│ ~/.jarvis/audit  │
│  position signal │     │   .jsonl         │
│                  │     │ (rotating)       │
└──────────────────┘     └──────────────────┘
```

## Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Presence Loop | Custom 30Hz controller | Continuous micro-behaviors, state machine |
| Brain | Claude Agent SDK + custom MCP tools | Reasoning, conversation, embodiment plans |
| Speech-to-Text | Whisper (local, `faster-whisper`) | Transcribe user speech |
| Text-to-Speech | ElevenLabs API (streaming) | Jarvis voice, sentence-level streaming |
| VAD | Silero VAD | End-of-utterance + barge-in detection |
| Face Tracking | YOLOv8 (`ultralytics`) | Face position → presence loop signal |
| Robot Control | Reachy Mini SDK | Head (6DOF), body, antennas, emotions |
| Smart Home | Home Assistant REST API | Lights, climate, media — with dry-run + audit |

## Setup

```bash
cd jarvis
uv sync
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, ELEVENLABS_API_KEY
# Optional: HASS_URL, HASS_TOKEN for smart home
# Optional: HOME_PERMISSION_PROFILE=readonly (state only) or control (default)
# Optional: HOME_REQUIRE_CONFIRM_EXECUTE=true (require confirm=true on all executes)
# Optional: HOME_CONVERSATION_ENABLED=true (enable HA conversation intent tool)
# Optional: HOME_CONVERSATION_PERMISSION_PROFILE=readonly|control (default readonly)
# Optional: SAFE_MODE_ENABLED=true (force mutating actions into restricted/dry-run behavior)
# Optional: TODOIST_API_TOKEN / TODOIST_PROJECT_ID / TODOIST_PERMISSION_PROFILE
# Optional: TODOIST_TIMEOUT_SEC=10.0 / PUSHOVER_TIMEOUT_SEC=10.0
# Optional: PUSHOVER_API_TOKEN / PUSHOVER_USER_KEY / NOTIFICATION_PERMISSION_PROFILE
# Optional: NUDGE_POLICY=interrupt|defer|adaptive / NUDGE_QUIET_HOURS_START / NUDGE_QUIET_HOURS_END
# Optional: EMAIL_SMTP_HOST / EMAIL_FROM / EMAIL_DEFAULT_TO / EMAIL_PERMISSION_PROFILE / EMAIL_TIMEOUT_SEC
# Optional: WEATHER_UNITS=metric|imperial / WEATHER_TIMEOUT_SEC
# Optional: WEBHOOK_ALLOWLIST=example.com,api.example.com / WEBHOOK_AUTH_TOKEN / WEBHOOK_TIMEOUT_SEC
# Optional: SLACK_WEBHOOK_URL / DISCORD_WEBHOOK_URL
# Optional: IDENTITY_ENFORCEMENT_ENABLED / IDENTITY_DEFAULT_USER / IDENTITY_DEFAULT_PROFILE
# Optional: IDENTITY_USER_PROFILES / IDENTITY_TRUSTED_USERS
# Optional: IDENTITY_REQUIRE_APPROVAL / IDENTITY_APPROVAL_CODE
# Optional: PLAN_PREVIEW_REQUIRE_ACK=true (require preview_token before risky execute tools)
# Optional: MEMORY_RETENTION_DAYS / AUDIT_RETENTION_DAYS (0 disables pruning)
# Optional: MEMORY_PII_GUARDRAILS_ENABLED=true|false
# Optional: MEMORY_ENCRYPTION_ENABLED / AUDIT_ENCRYPTION_ENABLED / JARVIS_DATA_KEY
# Optional: WAKE_MODE / WAKE_CALIBRATION_PROFILE / WAKE_WORDS / WAKE_WORD_SENSITIVITY / VOICE_TIMEOUT_PROFILE
# Optional: STT_FALLBACK_ENABLED / WHISPER_MODEL_FALLBACK / TTS_FALLBACK_TEXT_ONLY
# Optional: MODEL_FAILOVER_ENABLED / MODEL_SECONDARY_MODE / WATCHDOG_* / TURN_TIMEOUT_ACT_SEC / STARTUP_STRICT
# Optional: OPERATOR_SERVER_ENABLED / OPERATOR_SERVER_HOST / OPERATOR_SERVER_PORT / OPERATOR_AUTH_TOKEN
# Optional: WEBHOOK_INBOUND_ENABLED / WEBHOOK_INBOUND_TOKEN
# Optional: RECOVERY_JOURNAL_PATH (persistent interrupted-action journal)
# Optional: OBSERVABILITY_* (DB/state/event paths, burst threshold, snapshot interval)
# Optional: SKILLS_ENABLED / SKILLS_DIR / SKILLS_ALLOWLIST / SKILLS_REQUIRE_SIGNATURE / SKILLS_SIGNATURE_KEY
```

Smart home safety defaults:
- Sensitive domains (`lock`, `alarm_control_panel`, `cover`, `climate`) require `confirm=true` when `dry_run=false`.
- `HOME_PERMISSION_PROFILE=readonly` disables mutating `smart_home` actions but keeps `smart_home_state`.
- `HOME_REQUIRE_CONFIRM_EXECUTE=true` enforces `confirm=true` for all non-dry-run `smart_home` actions.
- `SAFE_MODE_ENABLED=true` keeps mutating actions in restricted mode (dry-run where supported, blocked otherwise).
- `PLAN_PREVIEW_REQUIRE_ACK=true` enforces a two-step preview+ack flow (`preview_token`) before mutating medium/high-risk actions.
  - First call can pass `preview_only=true` to get a plan preview token.
  - Execute call must include matching `preview_token=<token>` before token expiry.
- `NUDGE_POLICY` controls due-reminder interrupts: `interrupt`, `defer`, or `adaptive` (quiet-window aware).
- Operational runbook: [`docs/operations/home-control-policy.md`](docs/operations/home-control-policy.md).
- Integration runbook: [`docs/operations/integration-policy.md`](docs/operations/integration-policy.md).
- Trust/identity runbook: [`docs/operations/trust-policy.md`](docs/operations/trust-policy.md).
- Dialogue response mode auto-switches by request context:
  - `brief` for urgent/short-answer requests,
  - `deep` for explicit detailed walkthrough requests,
  - `normal` otherwise.
- First-response strategy auto-selects per request:
  - `answer` for direct questions,
  - `act` for explicit action requests,
  - `clarify` when an action request is ambiguous (`it/that/this` targets).
- Confidence policy auto-calibrates language:
  - `cautious` for volatile/time-sensitive prompts (`latest`, `today`, `right now`),
  - `calibrated` for estimate/prediction prompts,
  - `direct` for stable factual prompts.
- Wake-word false-trigger suppression supports calibration profiles (`default`, `quiet_room`, `noisy_room`, `tv_room`, `far_field`):
  - profile tunes wake sensitivity, minimum post-wake phrase length, and adaptive suppression window after repeated wake-only triggers.
- Follow-up intent carryover preserves unresolved action context across short multi-turn replies:
  - short fragments like `the bedroom` or `and in the office` inherit prior unresolved action targets.
  - explicit new action phrasing (e.g. `turn on the kitchen lights`) remains a new request.
- Runtime STT confidence diagnostics are exposed in operator status:
  - `voice_attention.stt_diagnostics` reports confidence score/band, model source, fallback usage, and transcript quality signals.
- Low-confidence action requests trigger a lightweight repair loop:
  - Jarvis asks `I may have misheard you as ...` and accepts either `confirm` or an immediate corrected phrase.
- Home Assistant conversation tool requires both:
  - `HOME_CONVERSATION_ENABLED=true`
  - `HOME_CONVERSATION_PERMISSION_PROFILE=control`
  - and tool argument `confirm=true`
- Home Assistant helper tools:
  - `home_assistant_todo` (`list|add|remove`) for native HA to-do entities
  - `home_assistant_timer` (`state|start|pause|cancel|finish`) for HA timer entities
  - `home_assistant_area_entities` for area-aware entity resolution
  - `media_control` for simplified `media_player` actions (`play`, `pause`, `volume_set`, etc.)
- Automation consumers can use:
  - `system_status` (includes `schema_version`)
  - `system_status.scorecard` (unified latency/reliability/initiative/trust scoring)
  - `system_status.turn_timeouts` (listen/think/speak/act timeout budgets)
  - `system_status.integrations.*.circuit_breaker` (open/remaining/failure state per integration)
  - `system_status.recovery_journal` (interrupted-action reconciliation summary)
  - `jarvis_scorecard` (standalone scorecard payload for dashboards and alerts)
  - `system_status_contract` (stable required-field contract)
- Memory retrieval now includes confidence/provenance details:
  - scoped classes: `preferences`, `people`, `projects`, `household_rules` (tagged as `scope:<name>`).
  - `memory_search` and `memory_recent` apply explicit scope policy (`scopes=...`) and expose `scope=...`, `confidence=...`, `source=...`, and `trail=id/source/created_at`.
  - `memory_status` includes `confidence_model` and `scope_policy` metadata for retrieval transparency.
- Audit logs now include readable authorization outcomes:
  - audit entries include `decision_outcome`, `decision_reason`, and `decision_explanation`.
  - this makes allow/deny/failure rationale machine-filterable and human-readable in `/api/audit`.
- Operator console/API security:
  - Set `OPERATOR_AUTH_TOKEN` when binding `OPERATOR_SERVER_HOST` to a non-loopback interface.
  - When token is set, `/api/*`, `/metrics`, and `/events` require `X-Operator-Token` or `Authorization: Bearer <token>`.
  - The dashboard root (`/`) remains reachable and supports token entry for browser-based API calls.
  - `GET /api/control-schema` returns action/payload requirements for automation clients.
  - `GET /api/conversation-trace` returns live turn flow/tool/policy/latency trace rows used by the dashboard panel.
  - Control actions include explicit sleep/wake toggles via `set_sleeping` (`sleeping=true|false`).
- Release checklist: [`docs/operations/release-checklist.md`](docs/operations/release-checklist.md).
- Security maintenance: [`docs/operations/security-maintenance.md`](docs/operations/security-maintenance.md).
- Error taxonomy: [`docs/operations/error-taxonomy.md`](docs/operations/error-taxonomy.md).
- Observability runbook: [`docs/operations/observability-runbook.md`](docs/operations/observability-runbook.md).
- Skills developer guide: [`docs/operations/skills-development.md`](docs/operations/skills-development.md).
- Provenance verification: [`docs/operations/provenance-verification.md`](docs/operations/provenance-verification.md).
- Incident response: [`docs/operations/incident-response.md`](docs/operations/incident-response.md).
- Todoist integration:
  - `TODOIST_PERMISSION_PROFILE=readonly|control`
  - `readonly` allows `todoist_list_tasks` and denies `todoist_add_task`
  - `control` allows both tools
  - `TODOIST_TIMEOUT_SEC` controls request timeout (default `10.0`)
  - `todoist_list_tasks` supports `format=short|verbose` (default `short`)
- Pushover integration:
  - `NOTIFICATION_PERMISSION_PROFILE=off|allow`
  - `off` denies `pushover_notify`, `slack_notify`, and `discord_notify`
  - `allow` enables all channel notification tools
  - `PUSHOVER_TIMEOUT_SEC` controls request timeout (default `10.0`)
- Email integration:
  - `email_send` requires `confirm=true` and `EMAIL_PERMISSION_PROFILE=control`
  - `email_summary` shows recent outbound email metadata
  - required SMTP env for send: `EMAIL_SMTP_HOST`, `EMAIL_FROM`, `EMAIL_DEFAULT_TO`
- Slack/Discord hooks:
  - `slack_notify` uses `SLACK_WEBHOOK_URL`
  - `discord_notify` uses `DISCORD_WEBHOOK_URL`
- Productivity tools:
  - timers: `timer_create`, `timer_list`, `timer_cancel`
  - reminders: `reminder_create`, `reminder_list`, `reminder_complete`
  - optional due reminder push dispatch: `reminder_notify_due`
  - calendar read helpers via Home Assistant: `calendar_events`, `calendar_next_event`
- Weather integration:
  - `weather_lookup` (Open-Meteo backend; `WEATHER_UNITS=metric|imperial`)
- Webhook integration:
  - `webhook_trigger` enforces `https` + `WEBHOOK_ALLOWLIST` domain policy
  - optional bearer token injection via `WEBHOOK_AUTH_TOKEN`
  - when identity enforcement is enabled, high-risk calls require `approval_code` or a trusted requester with `approved=true`

### First-Time Operator Checklist

1. Copy `.env.example` to `.env`, then set required keys: `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY`.
2. If using integrations, set both values for each pair:
   - `HASS_URL` and `HASS_TOKEN`
   - `PUSHOVER_API_TOKEN` and `PUSHOVER_USER_KEY`
3. Choose explicit permission profiles before first run:
   - `HOME_PERMISSION_PROFILE=readonly` (recommended first boot)
   - `TODOIST_PERMISSION_PROFILE=readonly`
   - `NOTIFICATION_PERMISSION_PROFILE=off`
4. Run local validation gates:
   - `make check`
   - `make test-faults`
5. Start in simulation mode and confirm no startup warnings are emitted:
   - `uv run python -m jarvis --sim --no-vision`
6. If Home Assistant is enabled, run a `dry_run=true` smart-home request first before any live execute.

## Usage

```bash
# Full Jarvis experience
uv run python -m jarvis

# Without face tracking (audio only)
uv run python -m jarvis --no-vision

# Text output instead of TTS (debugging)
uv run python -m jarvis --no-tts

# Simulation mode (no robot connected)
uv run python -m jarvis --sim

# Verbose logging
uv run python -m jarvis --debug

# Create a backup bundle (memory, audit logs, runtime state, operator settings)
uv run python -m jarvis --backup ~/.jarvis/backups/jarvis-$(date +%Y%m%d-%H%M%S).tar.gz

# Restore from a backup bundle (overwrite existing files)
uv run python -m jarvis --restore ~/.jarvis/backups/jarvis-20260227-120000.tar.gz --force

# Open operator console
open http://127.0.0.1:8765
```

## Developer Checks

```bash
# Full lint + full test suite
make check

# Fast local regression pass
make test-fast

# Fault-injection oriented subset (network, HTTP, summary, and storage taxonomy)
make test-faults

# Soak/stability subset
make test-soak

# Deployment/security gate (lint + tests + fault subset + workflow pin checks)
make security-gate

# Marker-based subsets
uv run pytest -q -m fast
uv run pytest -q -m fault
uv run pytest -q -m slow
```

Equivalent scripts are available under `scripts/`:
- `scripts/check.sh`
- `scripts/test_fast.sh`
- `scripts/test_faults.sh`
- `scripts/test_soak.sh`
- `scripts/security_gate.sh`

CI runs the same lint + test gates on every push and pull request via
[`ci.yml`](.github/workflows/ci.yml).
Workflow linting and YAML hygiene run via
[`workflow-sanity.yml`](.github/workflows/workflow-sanity.yml).
Nightly soak coverage is scheduled in
[`nightly-soak.yml`](.github/workflows/nightly-soak.yml).

### CI Workflow Intent and Failure Routing

| Workflow | Intent | Failure routing (first stop) |
|---|---|---|
| `ci.yml` / `lint` | Static checks (`ruff`) | `src/`, `tests/`, and Python style issues in the failing path |
| `ci.yml` / `tests` | Full regression (`pytest`) | Failing test module and corresponding implementation area |
| `ci.yml` / `faults` | Fault-injection taxonomy + error-path contract | `tests/test_tools_services.py` fault tests and `src/jarvis/tools/services.py` normalization paths |
| `workflow-sanity.yml` | Workflow hygiene (`actionlint`, tabs, script executability/shebang) | `.github/workflows/*` and `scripts/*.sh` |
| `shellcheck.yml` | Shell script linting | `scripts/*.sh` syntax/quoting/safety |
| `security.yml` | Scheduled/PR CodeQL scan | Security findings in SARIF report; route by file ownership |
| `nightly-soak.yml` | Long-run stability signal | `tests/test_main_audio.py -k soak`, audio/runtime regressions |

## Project Structure

```
jarvis/
├── pyproject.toml
├── .env.example
├── ~/.jarvis/audit.jsonl      # Auto-created audit log (runtime path)
├── src/
│   └── jarvis/
│       ├── __main__.py        # Entry point + conversation loop
│       ├── config.py          # Settings & env vars
│       ├── brain.py           # Claude Agent SDK orchestrator
│       ├── observability.py   # Telemetry store + metrics export
│       ├── operator_server.py # Local operator dashboard/API
│       ├── skills.py          # Local skill discovery + lifecycle
│       ├── presence.py        # 30Hz presence loop (the soul)
│       ├── tools/
│       │   ├── robot.py       # embody, play_emotion, play_dance
│       │   └── services.py    # smart_home + Todoist + Pushover + memory/planning tools
│       ├── audio/
│       │   ├── vad.py         # Silero voice activity detection
│       │   ├── stt.py         # faster-whisper transcription
│       │   └── tts.py         # ElevenLabs synthesis
│       ├── vision/
│       │   └── face_tracker.py  # YOLOv8 detection → presence signals
│       └── robot/
│           └── controller.py  # Reachy Mini SDK wrapper
```
