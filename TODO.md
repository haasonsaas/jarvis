# Jarvis Functional Roadmap

## Research Anchors (2025–2026)
- Head nods improve perceived affiliation/engagement in feedback signals: https://link.springer.com/article/10.1007/s10919-026-00500-y
- Real-time nod timing prediction for attentive listening avatars (VAP-based): https://arxiv.org/abs/2507.23298
- Nods have structured cycles (anticipatory rise, declination, final lowering): https://journals.plos.org/plosone/article/file?type=printable&id=10.1371/journal.pone.0303950
- Turn-taking + gaze timing matters for social ECAs: https://ieeexplore.ieee.org/iel5/6403618/6406254/06406356.pdf
- Delays reduce gaze toward robot and increase gaze aversion: https://www.nature.com/articles/s41598-025-17140-9
- Incremental listen/think/speak improves streaming latency tradeoffs: https://arxiv.org/html/2601.19952v1
- Streaming TTS latency/accuracy tradeoffs + TTFB targets: https://deepgram.com/learn/streaming-tts-latency-accuracy-tradeoff-2026
- JARVIS persona traits (concise, composed, dry wit, proactive): https://ironman.fandom.com/wiki/J.A.R.V.I.S.
- JARVIS interaction style examples: https://www.imdb.com/title/tt0371746/characters/nm0079273/
- JARVIS dialogue/quote archive for tone sampling: https://marvelcinematicuniverse.fandom.com/wiki/J.A.R.V.I.S./Quote
- Practical JARVIS personality template (formal, witty, proactive): https://docsbot.ai/prompts/technical/jarvis-personality
- Product vision gap vs. “JARVIS-like” assistants: https://digitalgods.ai/we-dont-want-ai-we-want-jarvis-2/
- Human gaze follows robot head orientation even when task-irrelevant: https://www.nature.com/articles/s41598-026-39130-1
- Turn-taking + backchannel prediction from multimodal cues: https://arxiv.org/html/2505.12654v1
- Streaming ASR with lower latency via intended query detection: https://arxiv.org/pdf/2208.13322
- Streaming ASR finite look-ahead attention (latency/quality tradeoff): https://arxiv.org/html/2506.03722v1
- Survey of generative nonverbal behavior (gaze, nods, facial cues): https://link.springer.com/article/10.1007/s11370-025-00674-2
- Conversational behavior reasoning for full-duplex speech: https://openreview.net/pdf/bf108aaf700284ffc109a7db5e8c659786344b98.pdf

## TODO (sliced by function)

### 1) Conversation + Turn-Taking
- [ ] Add explicit turn-taking model that blends VAD, DoA, and gaze (short pauses, nods, and gaze aversion cues during waits).
- [ ] Add short “thinking” filler audio and timing guardrails to reduce perceived latency (target sub-200ms TTFB for TTS).
- [ ] Integrate “listen-while-speak” semantics for immediate interruption handling (LTS-style split brain).
- [ ] Add full-duplex reasoning heuristics (intent + speech act inference) to decide when to interrupt vs. wait.
- [ ] Add user-specific backchannel cadence preferences (quiet vs. active listener).
  - Implemented: turn-taking score + filler audio + barge-in handling.

### 2) Embodied Behavior (Gaze, Nods, Timing)
- [ ] Implement nod/tilt timing rules: acknowledge on user completion; avoid nod spam mid-sentence.
- [ ] Add gaze aversion on long delays (as delay grows, increase aversion to reduce “stare”).
- [ ] Add micro-confirmation gestures (small nod/tilt) when tool actions start/finish.
- [ ] Add nod shape variants (single, double, slow) matching conversational intent.
- [ ] Add “polite” head dip for acknowledgements (micro bow) and “processing” micro-tilt loop.
  - Implemented: nod cadence guardrails + attention hold/timeout for face/hand/DoA.
  - Implemented: tool feedback micro-nods on tool start/finish.

### 3) Perception Stack
- [ ] Prioritized attention mux: face > hand > DoA, with confidence decay + timeout.
- [ ] Add “attention memory” that keeps last focus target for 1–2s to avoid rapid flips.
- [ ] Add minimal hand confidence metrics + region-of-interest gating for false positives.
- [ ] Add attention strength signal history (short-term buffer) to smooth out noisy detections.
- [ ] Add gaze-led turn-yield detection (look away when user finishes).

### 4) Action Sequencing + Motion Primitives
- [ ] Build a small library of “gesture macros” (acknowledge, shrug, curious lean) that compile to sequences.
- [ ] Add background idle choreographies (gentle sway, antenna wave), auto-paused during speech.
- [ ] Add sequence interruption/cancel semantics (barge-in should stop current motion sequence).
- [ ] Add low-amplitude “listening loop” (lean + minimal nod) for extended user monologues.
- [ ] Add motion blending between choreographies and LLM intent gestures.
  - Implemented: motion sequence runner + initial gesture macros.

### 5) Tool Policy + Safety
- [ ] Add tool policy guardrails for smart-home operations (explicit user confirmation for sensitive domains).
- [ ] Add per-action cooldowns to avoid rapid repeat commands.
- [ ] Add action audit trail summaries for user review (not just raw logs).
- [ ] Add user-visible tool execution summary tool (“what I just did” recap).
  - Implemented: per-action cooldowns for smart-home tool.

### 6) Voice + Audio UX
- [ ] Add streaming TTS chunk normalization (loudness leveling, RMS smoothing).
- [ ] Add “latency budget” logging for STT → LLM → TTS stages to identify slow hops.
- [ ] Implement progressive prosody controls (speech rate or pauses based on response confidence).
- [ ] Add low-latency “pre-response” earcon variants that reflect tone (neutral/alert/positive).
- [ ] Add adaptive pause insertion when user shows confusion (repeat back core intent).
  - Implemented: TTS RMS normalization + latency logging.
  - Implemented: confidence-based sentence pauses.

### 11) Backchannel + Feedback
- [ ] Add lightweight backchannel scheduler (subtle nod/tilt on user pauses).
- [ ] Use DoA/face confidence to bias backchannel timing.
- [ ] Add nod intensity tiers based on confidence + user sentiment.
  - Implemented: backchannel nod scheduler in listening state.
  - Implemented: attention-weighted backchannel gating.

### 12) Multimodal Intent
- [ ] Add intended-query gate to ignore off-axis chatter (ASR intent detection or simple heuristic).
- [ ] Add “attention confirmation” when confidence is low (short prompt: “Did you mean me?”).
- [ ] Add multi-speaker disambiguation (“which of you asked?”) when two DoA sources present.
  - Implemented: attention confidence gate + confirmation prompt.

### 7) Memory + Personalization
- [ ] Add a lightweight memory summary store (recent preferences + “last discussed”).
- [ ] Add recall rules: use memory only when relevant and confirm before using sensitive data.
- [ ] Add “voice of JARVIS” preference memory (tone/verbosity) per user.
  - Implemented: basic SQLite memory store + retrieval hook + memory tools.
  - Implemented: sensitivity filtering + relevance gating for recall.
  - Implemented: memory summary store tools (topics + summaries).
- [ ] Add hybrid memory search (keyword + vector blending) with configurable weights.
- [ ] Add query expansion for conversational memory search (keyword extraction fallback).
- [ ] Add temporal decay for stale memories (half-life config; no decay for evergreen).
- [ ] Add MMR re-ranking for diversity in memory search results.
- [ ] Add memory sources + scope filtering (session memory vs evergreen memory).
- [ ] Add memory sync cadence + warm-on-session-start behavior.
- [ ] Add memory status/probe endpoints (counts, provider status, FTS availability).

### 7b) Task Orchestration
- [ ] Add explicit planner (multi-step tasks, retries, status).
- [ ] Add task queue with priorities + deadlines.
- [ ] Provide task progress summaries.
  - Implemented: lightweight task plan storage + status updates.
  - Implemented: next-step helper for orchestration.
  - Implemented: task progress summary tool.
- [ ] Add task plan retries + failure reasons per step.
- [ ] Add plan-level metadata (owner, created_from, tags) for routing.
- [ ] Add orchestration memory snapshots per plan (context pack).
- [ ] Add “execution constraints” per plan (silent mode, no tools, max cost).

### 8) Reliability + Telemetry
- [ ] Add watchdog for presence loop + perception threads (auto-restart on failure).
- [ ] Add health endpoint or log snapshot for quick diagnostics.
- [ ] Add memory/indexer health status (provider, FTS-only mode, last sync, errors).
- [ ] Add structured tool execution logs + summary rollups (success/fail/latency).
- [ ] Add session telemetry (turn count, latency breakdown, barge-in rate).
- [ ] Add rolling “last 5 errors” buffer for quick status responses.

### 9) Content + Personality
- [ ] Add “short answer by default” gate; require user intent for longer responses.
- [ ] Add sarcasm/irony guardrails for sensitive topics.
- [ ] Add persona mode flags (JARVIS terse/composed vs friendly verbose).
- [ ] Add “dry wit” style triggers for low-stakes queries (weather, time, reminders).
- [ ] Add escalation policy for urgency (from polite -> clipped when high risk).

### 10) UX + Setup
- [ ] Provide a one-time calibration flow for head limits, audio level, and face/hand thresholds.
- [ ] Add quick toggles: `--no-motion`, `--no-hands`, `--no-home`.
- [ ] Add session bootstrap summary (capabilities, connected providers, memory state).
- [ ] Add onboarding prompt that explains Jarvis’s limits + confirmation safety model.

### 13) Tool Policy + Execution Guardrails (OpenClaw-inspired)
- [ ] Add tool policy profiles (global + per-agent allow/deny lists).
- [ ] Add provider-specific tool policies (per model/provider allowlist).
- [ ] Add subagent depth limits + always-deny tool list for subagents.
- [ ] Add tool policy matching with glob patterns and alias normalization.
- [ ] Add tool summary capture (reason + effect + external side-effects).
- [ ] Add tool result sanitization before memory storage.
- [ ] Add tool memory redaction rules (mask tokens, addresses, access codes).

### 14) Sessions + Memory Lifecycle
- [ ] Add session-level memory buffers (short-term memory separate from long-term).
- [ ] Add session transcript compaction + guardrails to avoid tool loops.
- [ ] Add session-scoped memory read permissions (workspace/path filters).
- [ ] Add memory import/export hooks (per-session and per-user snapshots).
- [ ] Add session-level privacy modes (no storage, anonymized storage).
