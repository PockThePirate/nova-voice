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
1. ~~Implement the "Play Summary" button on Mission Control and verify it uses Nova's voice.~~ ✅ Done — button works, generates TTS via Nova voice API
2. Design the daily summary cron: weekdays 06:00–07:00 with work missions; weekends with programming/education/home missions.
3. Add a new mission log section describing cron rules (weekday vs weekend) and wire the first cron job in OpenClaw.

## Completed Actions
- [x] Wire Missions panel into Mission Control dashboard
- [x] Add mission log download button
- [x] Implement "Play Summary" button with Nova TTS

## Decisions / Notes
- Voice/wake-word changes are gated: Nova must not change them without explicit approval.
- Mission logs live in `mission_control/missions/` and are treated as first-class artifacts.
