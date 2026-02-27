# Personality Research Notes

Last updated: 2026-02-27

## Goal

Tune Jarvis personality for higher trust and "assistant presence" without degrading safety or task completion.

## Sources reviewed

1. Amazon Alexa conversation design: personality guidance  
   https://developer.amazon.com/en-US/alexa/alexa-haus/guidelines-and-resources/conversation-design/personality
2. Amazon Alexa conversation design: cooperative principles  
   https://developer.amazon.com/en-US/alexa/alexa-haus/guidelines-and-resources/conversation-design/cooperative-principles
3. Google Assistant conversation design: personality  
   https://developers.google.com/assistant/conversation-design/personality
4. Google Assistant conversation design: turn taking  
   https://developers.google.com/assistant/conversation-design/turn-taking
5. Nielsen Norman Group: chatbot UX principles  
   https://www.nngroup.com/articles/chatbots/
6. Rasa design guidance on assistant humanization  
   https://rasa.com/blog/11-tips-for-humanizing-your-assistant/

## Practical takeaways

- Keep persona consistent but subordinate to usefulness.
- Use concise responses by default for voice channels.
- Distinguish social moments from task/safety moments.
- In high-risk contexts, prioritize explicit language over personality flair.
- Add personality controls that operators can tune per user and context.

## Implementation mapping (Wave 5)

- Added `jarvis` persona style as a first-class mode.
- Added context-driven "persona posture" routing:
  - `social`, `task`, `safety`.
- Added per-user voice profile `tone` control:
  - `auto`, `formal`, `witty`, `empathetic`, `direct`.
- Updated operator console controls to expose the new persona and tone paths.
- Updated system status voice profile contract to include `tone`.

## Open follow-ups

- Run human-eval A/B sessions for `jarvis` vs `composed`.
- Tune social/safety posture classifiers using real transcripts.
- Add weekly drift checks for over-verbosity and confirmation friction.
