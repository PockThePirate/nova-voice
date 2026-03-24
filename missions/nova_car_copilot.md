# Nova Car Copilot

## Goal
Hands-free Nova assistant for commuting and driving, with reliable wake word, voice control, and clear feedback.

## Definition of Done
- I can use Nova in the car (Android + Mission Control) to handle common tasks (questions, navigation cues, status) without looking at the screen.
- Wake word + responses feel as smooth and predictable as Siri/Alexa for my core workflows.

## Milestones
- M1: Mission Control web experience is reliable and pleasant on desktop and phone (current work).
- M2: Android Nova Voice app is stable on the S25, with wake word and gateway connection.
- M3: Streaming audio backend replaces browser SpeechRecognition for web.
- M4: Daily/weekly mission summaries and healthchecks run automatically.

## Status
- Phase: Early build / integration.
- Notes: Web wake-word and voice are functional but in active development. Streaming backend is stubbed and being wired in.

## Next 3 Actions
1. Wire Missions panel into Mission Control dashboard (list missions + view this file).
2. Add mission log download button to Mission Control.
3. Define a daily mission summary cron structure (even before we enable it).

## Decisions / Notes
- Voice/wake-word changes are gated: Nova must not change them without explicit approval.
- Mission logs live in `mission_control/missions/` and are treated as first-class artifacts.
