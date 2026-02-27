# Proactive Triage And Preference Learning

## Proactive `nudge_decision`

`proactive_assistant` supports `action="nudge_decision"` to bucket candidate nudges into:

- `interrupt`
- `notify`
- `defer`

Routing is deterministic and depends on:

- `policy`: `interrupt | defer | adaptive`
- `quiet_window_active` (explicit arg, otherwise runtime quiet-window policy)
- candidate urgency inputs (`severity`, `due_at`, `expires_at`, `interrupt_allowed`)
- optional `context` inputs (`user_busy`, `conversation_active`, `presence_confidence`)
- `max_dispatch` capacity limit

The response returns per-bucket rows plus summary counts and cumulative proactive counters.
When context indicates an active/busy interaction or low presence confidence, non-critical interrupts are downgraded to `notify`/`defer`.

## Preference Learning Loop

Conversation runtime now detects explicit user style directives and updates the active voice profile for:

- `verbosity` (`brief | normal | detailed`)
- `confirmations` (`minimal | standard | strict`)
- `pace` (`slow | normal | fast`)
- `tone` (`auto | formal | witty | empathetic | direct`)

When memory is enabled, learned profile state is mirrored to memory summaries (`voice_profile:<user>`). Learned updates are exposed through runtime voice status (`preference_learning`) and observability intent metrics (`preference_update_turns`, `preference_update_fields`).

## Safety Boundaries

- Preference learning only triggers on explicit style-oriented directives (not on arbitrary requests).
- High-risk action safeguards remain unchanged (preview/approval gates, policy checks).
- Quiet-hour and policy controls still govern whether proactive actions interrupt or defer.
- Multimodal grounding is advisory for operator transparency and recommendation quality; it does not bypass policy gates.
