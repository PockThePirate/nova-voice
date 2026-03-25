# Daily Mission Summary Cron Structure

## Overview
Automated daily summary of mission progress, health checks, and next actions.

## Cron Schedule
```
# Run daily at 9:00 AM local time
0 9 * * * cd /home/pock/.openclaw/workspace/mission_control && python manage.py mission_daily_summary --notify
```

## Django Management Command Structure

### Command: `mission_daily_summary`
Location: `dashboard/management/commands/mission_daily_summary.py`

**Functions:**
1. **Scan mission files** in `missions/*.md`
2. **Parse "Next 3 Actions"** from each mission
3. **Check completion status** (via log analysis or manual markers)
4. **Generate summary report** with:
   - Active missions count
   - Actions completed yesterday
   - Actions remaining today
   - Blockers or notes
5. **Deliver summary** via:
   - Dashboard notification
   - Email (optional)
   - WhatsApp message (if configured)

### Summary Output Format
```
📅 Daily Mission Summary - {date}

🎯 Active Missions: {count}

✅ Completed Yesterday:
- [Mission]: [Action]

📋 Today's Actions:
1. [Mission]: [Action]
2. [Mission]: [Action]
3. [Mission]: [Action]

🚧 Blockers:
- [Mission]: [Blocker note]

🔗 Mission Control: https://novamission.cloud
```

## Healthcheck Integration
- Runs as part of daily summary
- Checks:
  - Gateway status
  - WhatsApp connection
  - Voice agent availability
  - Mission file integrity
- Reports any issues in summary

## Implementation Status
- [x] Cron structure defined
- [x] Command template created
- [ ] Management command implemented
- [ ] Cron job enabled (user discretion)

## Next 3 Actions
1. Create `dashboard/management/commands/mission_daily_summary.py` management command
2. Implement mission file scanner to parse "Next 3 Actions" from all .md files
3. Add summary generation with TTS audio output for dashboard playback

## Completed Actions
- [x] Defined cron structure and schedule
- [x] Created crontab template at `deploy/crontab.mission_summary`
- [x] Documented summary output format and healthcheck integration

## Notes
- Mark actions complete by editing mission files
- Use `## Completed Actions` section in .md files
- Healthchecks run silently; only report failures
