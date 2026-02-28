# Jarvis Capability Roadmap (Research-Backed)

Date: 2026-02-27

## Current Baseline

- Contract quality gates are strong:
  - `./scripts/run_eval_dataset.py docs/evals/assistant-contract.json --strict --min-pass-rate 1.0 --max-failed 0`
  - Result: `253/253` passed.
- Readiness fast gate passes:
  - `./scripts/jarvis_readiness.sh fast`
  - Result: passed.

Interpretation:
- The system is robust against a broad contract and safety regression suite.
- Remaining gaps are mostly about real-world reliability, autonomy quality, and human-level interaction consistency.

## How Close To "Real Jarvis"

Estimated capability maturity: **~70%**.

- Safety/policy controls: strong.
- Tool/integration breadth: strong.
- Long-horizon autonomy: medium.
- Memory quality and personalization depth: medium.
- Multimodal grounding robustness: medium.
- Human-like conversational continuity under real-world noise: medium.

## Highest-Leverage Gaps (What Is Left)

## P0. Upgrade From Contract Evals To Outcome Evals

Gap:
- Current evals prove interface and policy behavior well, but not enough real-world task success quality.

Do it better:
- Add eval sets from real operator transcripts and incidents.
- Score task completion, clarification quality, false-positive confirmations, and unnecessary tool calls.
- Add trace-based grading on full agent trajectories.

Repo touchpoints:
- `docs/evals/assistant-contract.json`
- `scripts/run_eval_dataset.py`
- `src/jarvis/runtime_conversation_trace.py`
- `docs/operations/observability-runbook.md`

Exit criteria:
- New "real-world" eval suite in CI.
- Stable pass threshold on 2 consecutive weeks.
- Measured drop in correction rate and re-ask loops.

## P0. Move Routing From Heuristics To Structured Policy Agent

Gap:
- Routing/posture is currently regex and keyword driven.

Evidence in code:
- Starting agent and style/risk modes are selected via heuristics in `brain.py`.

Do it better:
- Add a lightweight policy/router agent that outputs strict JSON for:
  - intent class,
  - risk class,
  - required confirmation mode,
  - specialist/handoff target.
- Add handoff input filters so only relevant context is forwarded between specialists.

Repo touchpoints:
- `src/jarvis/brain.py`
- `src/jarvis/tools/openai_tooling.py`

Exit criteria:
- Safety routing error rate <1% on adversarial eval set.
- Reduced false clarifications and false executions on ambiguous commands.

## P0. Closed-Loop Autonomy (Postconditions + Replan)

Gap:
- Autonomy cycle currently advances queued steps and enqueues follow-through items, but lacks formal world-state verification and automatic replan loops.

Progress update (2026-02-28):
- Implemented first-cut closed loop in `planner_autonomy_cycle`:
  - structured step precondition/postcondition contracts,
  - bounded retry/backoff per step,
  - failure taxonomy capture,
  - automatic replan follow-through enqueue when retries are exhausted.
- `planner_autonomy_status` now exposes retry/replan counters and aggregated failure taxonomy.

Evidence in code:
- `planner_autonomy_cycle` is largely schedule/step progression logic.

Do it better:
- For each step, require:
  - precondition check,
  - execution,
  - postcondition verification,
  - bounded retry/backoff,
  - fallback replan.
- Store step-level evidence and failure reason taxonomy per run.

Repo touchpoints:
- `src/jarvis/tools/services_domains/planner_engine_autonomy_cycle.py`
- `src/jarvis/tools/services_domains/planner_engine_autonomy_status.py`
- `docs/operations/autonomy-checkpoint-runbook.md`

Exit criteria:
- Long-horizon task success rate improves with no increase in unsafe retries.
- Autonomy incident rate (stalls/repeats/manual recoveries) drops over weekly soak.

## P1. Memory Retrieval Quality and Contradiction Handling

Gap:
- Memory retrieval is mainly lexical/FTS + heuristic scoring; contradiction resolution is limited.

Evidence in code:
- Search path is keyword/FTS/token overlap with optional MMR-like token similarity.

Do it better:
- Add embedding-backed semantic retrieval with citations/provenance.
- Add contradiction/duplication checks during write.
- Add confidence updates from explicit user confirmations/corrections.
- Add memory quality evals (`precision@k`, contradiction rate, stale recall rate).

Repo touchpoints:
- `src/jarvis/memory.py`
- `src/jarvis/runtime_memory_correction.py`
- `docs/operations/proactive-preference-loop.md`

Exit criteria:
- Semantic recall quality improves on benchmark prompts.
- Lower contradiction and stale-memory regressions.

## P1. Multimodal Grounding Calibration

Gap:
- Multimodal confidence is currently a fixed weighted heuristic.

Evidence in code:
- Confidence score is hand-weighted across face/hand/DOA/STT.

Do it better:
- Calibrate weights on recorded sessions.
- Add conflict policies (for example: low STT + stale face => no mutate without re-confirm).
- Track calibration drift and per-modality reliability.

Repo touchpoints:
- `src/jarvis/runtime_multimodal.py`
- `src/jarvis/runtime_voice_status.py`
- `docs/operations/observability-runbook.md`

Exit criteria:
- Lower false-action rate under noisy conditions.
- Better confirmation behavior for low-confidence speech turns.

## P1. Identity Assurance and Step-Up Auth

Gap:
- Operator/session controls are strong, but household voice assurance for high-risk actions should be stronger.

Evidence in code:
- Operator approval resolution/execution now requires authenticated operator identity and execution tickets.

Do it better:
- Add step-up verification for high-risk actions (challenge response + trusted channel confirmation).
- Align assurance levels per action class.
- Add replay-resistant approval attestations for externalized control channels.

Repo touchpoints:
- `src/jarvis/tools/services_domains/home_orch_plan_exec.py`
- `src/jarvis/runtime_operator_control.py`
- `docs/operations/trust-policy.md`

Exit criteria:
- High-risk actions require stronger verified identity than routine actions.
- Red-team spoof/escalation scenarios consistently blocked.

## P2. Conversation Quality Beyond Brevity/Style Controls

Gap:
- Strong policy and style controls exist, but "Jarvis feel" still needs richer discourse memory and adaptive turn planning.

Do it better:
- Add conversation-level objectives:
  - minimal-turn completion,
  - interruption recovery quality,
  - proactive relevance precision.
- Add operator-rated weekly A/B evaluation for personality drift and utility.

Repo touchpoints:
- `src/jarvis/brain.py`
- `scripts/personality_ab_eval.py`
- `docs/evals/personality-ab-prompts.json`

Exit criteria:
- Weekly trend improvements on operator-rated helpfulness and naturalness.
- Reduced verbosity drift and repeated clarification loops.

## Delivery Sequence (Recommended)

1. P0 outcome evals and trace grading.
2. P0 structured router + handoff filters.
3. P0 autonomy postcondition/replan loop.
4. P1 memory semantic retrieval + contradiction control.
5. P1 multimodal calibration + low-confidence safeguards.
6. P1 step-up auth.
7. P2 conversation polish loops.

## External References

- OpenAI Agents SDK docs (Python): https://openai.github.io/openai-agents-python/
- Handoffs (input filters + tool-based transfer model): https://openai.github.io/openai-agents-python/handoffs/
- Sessions: https://openai.github.io/openai-agents-python/sessions/
- OpenAI Evals guide: https://platform.openai.com/docs/guides/evals
- Eval design best practices: https://platform.openai.com/docs/guides/evals-design
- Trace grading: https://platform.openai.com/docs/guides/graders/trace-grading
- Home Assistant conversation API: https://developers.home-assistant.io/docs/intent_conversation_api/
- OWASP Top 10 for LLM Applications: https://owasp.org/www-project-top-10-for-large-language-model-applications/
- NIST AI RMF 1.0: https://airc.nist.gov/airmf-resources/airmf/
- NIST SP 800-63-4 (Digital Identity Guidelines): https://csrc.nist.gov/pubs/sp/800/63/4/final
- ReAct paper (reasoning + acting): https://arxiv.org/abs/2210.03629
- Tree of Thoughts: https://arxiv.org/abs/2305.10601
- Reflexion: https://arxiv.org/abs/2303.11366
- Generative Agents: https://arxiv.org/abs/2304.03442
- MemGPT: https://arxiv.org/abs/2310.08560
