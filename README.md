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
│  Whisper STT ────┼────►│    embody        │     │                  │
│                  │     │    smart_home    │     │  Barge-in:      │
│  Barge-in: ◄─────┼─────│    play_emotion │◄────│  VAD interrupts │
│  stop TTS        │     │    play_dance   │     │  playback       │
└─────────────────┘     └──────────────────┘     └─────────────────┘

┌──────────────────┐     ┌──────────────────┐
│  Face Tracker    │     │   Audit Log      │
│  YOLOv8 → face   │────►│   jarvis_audit   │
│  position signal │     │ ~/.jarvis/audit  │
│                  │     │   .jsonl         │
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
# Optional: TODOIST_API_TOKEN / TODOIST_PROJECT_ID / TODOIST_PERMISSION_PROFILE
# Optional: PUSHOVER_API_TOKEN / PUSHOVER_USER_KEY / NOTIFICATION_PERMISSION_PROFILE
```

Smart home safety defaults:
- Sensitive domains (`lock`, `alarm_control_panel`, `cover`) require `confirm=true` when `dry_run=false`.
- `HOME_PERMISSION_PROFILE=readonly` disables mutating `smart_home` actions but keeps `smart_home_state`.
- Operational runbook: [`docs/operations/home-control-policy.md`](docs/operations/home-control-policy.md).
- Integration runbook: [`docs/operations/integration-policy.md`](docs/operations/integration-policy.md).
- Todoist integration:
  - `TODOIST_PERMISSION_PROFILE=readonly|control`
  - `readonly` allows `todoist_list_tasks` and denies `todoist_add_task`
  - `control` allows both tools
- Pushover integration:
  - `NOTIFICATION_PERMISSION_PROFILE=off|allow`
  - `off` denies `pushover_notify`
  - `allow` enables `pushover_notify`

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
```

Equivalent scripts are available under `scripts/`:
- `scripts/check.sh`
- `scripts/test_fast.sh`
- `scripts/test_faults.sh`
- `scripts/test_soak.sh`

CI runs the same lint + test gates on every push and pull request via
[`ci.yml`](.github/workflows/ci.yml).
Workflow linting and YAML hygiene run via
[`workflow-sanity.yml`](.github/workflows/workflow-sanity.yml).
Nightly soak coverage is scheduled in
[`nightly-soak.yml`](.github/workflows/nightly-soak.yml).

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
