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
1. Create Android Nova Voice app skeleton with wake word detection (M2 milestone)
2. Wire streaming audio backend to replace browser SpeechRecognition (M3 milestone)
3. Add weekly mission summary with automatic healthcheck reporting (M4 milestone)

## Completed Actions
- [x] Wire Missions panel into Mission Control dashboard
- [x] Add mission log download button  
- [x] Implement "Play Summary" button with Nova TTS
- [x] Design daily summary cron with weekday/weekend mission selection
- [x] Wire first OpenClaw cron job (runs daily 9 AM UTC)

## Daily Summary Cron Rules
**Weekdays (Mon-Fri) 06:00–07:00:** Focus on work missions (Nova Car Copilot, professional tasks)
**Weekends (Sat-Sun) 09:00–10:00:** Focus on programming/education/home missions (learning, side projects, personal goals)

Logic: Cron checks day of week, picks appropriate mission category, generates summary with relevant next actions.

## Decisions / Notes
- Voice/wake-word changes are gated: Nova must not change them without explicit approval.
- Mission logs live in `mission_control/missions/` and are treated as first-class artifacts.
