# Jarvis Functional Roadmap

## Research Anchors (2025–2026)
- Head nods improve perceived affiliation/engagement in feedback signals: https://link.springer.com/article/10.1007/s10919-026-00500-y
- Turn-taking + gaze timing matters for social ECAs: https://ieeexplore.ieee.org/iel5/6403618/6406254/06406356.pdf
- Delays reduce gaze toward robot and increase gaze aversion: https://www.nature.com/articles/s41598-025-17140-9
- Incremental listen/think/speak improves streaming latency tradeoffs: https://arxiv.org/html/2601.19952v1
- Streaming TTS latency/accuracy tradeoffs + TTFB targets: https://deepgram.com/learn/streaming-tts-latency-accuracy-tradeoff-2026
- JARVIS persona traits (concise, composed, dry wit, proactive): https://ironman.fandom.com/wiki/J.A.R.V.I.S.
- JARVIS interaction style examples: https://www.imdb.com/title/tt0371746/characters/nm0079273/

## TODO (sliced by function)

### 1) Conversation + Turn-Taking
- [ ] Add explicit turn-taking model that blends VAD, DoA, and gaze (short pauses, nods, and gaze aversion cues during waits).
- [ ] Add short “thinking” filler audio and timing guardrails to reduce perceived latency (target sub-200ms TTFB for TTS).
- [ ] Integrate “listen-while-speak” semantics for immediate interruption handling (LTS-style split brain).

### 2) Embodied Behavior (Gaze, Nods, Timing)
- [ ] Implement nod/tilt timing rules: acknowledge on user completion; avoid nod spam mid-sentence.
- [ ] Add gaze aversion on long delays (as delay grows, increase aversion to reduce “stare”).
- [ ] Add micro-confirmation gestures (small nod/tilt) when tool actions start/finish.
  - Implemented: nod cadence guardrails + attention hold/timeout for face/hand/DoA.

### 3) Perception Stack
- [ ] Prioritized attention mux: face > hand > DoA, with confidence decay + timeout.
- [ ] Add “attention memory” that keeps last focus target for 1–2s to avoid rapid flips.
- [ ] Add minimal hand confidence metrics + region-of-interest gating for false positives.

### 4) Action Sequencing + Motion Primitives
- [ ] Build a small library of “gesture macros” (acknowledge, shrug, curious lean) that compile to sequences.
- [ ] Add background idle choreographies (gentle sway, antenna wave), auto-paused during speech.
- [ ] Add sequence interruption/cancel semantics (barge-in should stop current motion sequence).
  - Implemented: motion sequence runner + initial gesture macros.

### 5) Tool Policy + Safety
- [ ] Add tool policy guardrails for smart-home operations (explicit user confirmation for sensitive domains).
- [ ] Add per-action cooldowns to avoid rapid repeat commands.
- [ ] Add action audit trail summaries for user review (not just raw logs).

### 6) Voice + Audio UX
- [ ] Add streaming TTS chunk normalization (loudness leveling, RMS smoothing).
- [ ] Add “latency budget” logging for STT → LLM → TTS stages to identify slow hops.
- [ ] Implement progressive prosody controls (speech rate or pauses based on response confidence).

### 7) Memory + Personalization
- [ ] Add a lightweight memory summary store (recent preferences + “last discussed”).
- [ ] Add recall rules: use memory only when relevant and confirm before using sensitive data.

### 8) Reliability + Telemetry
- [ ] Add watchdog for presence loop + perception threads (auto-restart on failure).
- [ ] Add health endpoint or log snapshot for quick diagnostics.

### 9) Content + Personality
- [ ] Add “short answer by default” gate; require user intent for longer responses.
- [ ] Add sarcasm/irony guardrails for sensitive topics.

### 10) UX + Setup
- [ ] Provide a one-time calibration flow for head limits, audio level, and face/hand thresholds.
- [ ] Add quick toggles: `--no-motion`, `--no-hands`, `--no-home`.
