#!/usr/bin/env python
"""
Daily mission summary command with weekday/weekend logic.

Usage:
    python manage.py mission_daily_summary [--notify] [--voice]

Weekday (Mon-Fri 06:00-07:00): Work missions
Weekend (Sat-Sun 09:00-10:00): Programming/education/home missions
"""
import datetime
import re
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = "Generate daily mission summary with weekday/weekend logic"

    def add_arguments(self, parser):
        parser.add_argument(
            "--notify",
            action="store_true",
            help="Send notification via configured channels",
        )
        parser.add_argument(
            "--voice",
            action="store_true",
            help="Generate TTS audio for the summary",
        )

    def handle(self, *args, **options):
        now = datetime.datetime.now()
        is_weekday = now.weekday() < 5  # Mon=0, Fri=4, Sat=5, Sun=6
        
        # Determine focus category
        if is_weekday:
            focus_category = "work"
            focus_time = "06:00-07:00"
            self.stdout.write(self.style.SUCCESS(f"Weekday focus: {focus_category} missions"))
        else:
            focus_category = "programming/education/home"
            focus_time = "09:00-10:00"
            self.stdout.write(self.style.SUCCESS(f"Weekend focus: {focus_category} missions"))
        
        # Scan mission files
        missions_dir = Path(settings.BASE_DIR) / "missions"
        if not missions_dir.exists():
            self.stdout.write(self.style.ERROR("No missions directory found"))
            return
        
        mission_files = sorted(missions_dir.glob("*.md"))
        
        # Categorize missions (simple heuristic based on name/content)
        work_missions = []
        personal_missions = []
        
        for mission_file in mission_files:
            slug = mission_file.stem
            # Skip daily summary cron itself
            if "daily_summary" in slug:
                continue
                
            actions = self._extract_actions(mission_file)
            mission_data = {
                "slug": slug,
                "title": slug.replace("_", " ").title(),
                "actions": actions,
            }
            
            # Categorize (simple rules)
            if any(word in slug for word in ["car", "copilot", "work", "professional", "nova"]):
                work_missions.append(mission_data)
            else:
                personal_missions.append(mission_data)
        
        # Pick focus missions
        if is_weekday:
            focus_missions = work_missions
        else:
            focus_missions = personal_missions
        
        if not focus_missions:
            focus_missions = work_missions + personal_missions  # fallback
        
        # Generate summary
        summary_lines = [
            f"Daily Mission Summary - {now.strftime('%A, %B %d')}",
            "",
            f"Focus: {focus_category} missions ({focus_time})",
            f"Total missions: {len(mission_files) - 1}",  # minus daily_summary
            f"Focus missions: {len(focus_missions)}",
            "",
        ]
        
        # Today's actions from focus missions
        summary_lines.append("Today's Actions:")
        action_count = 0
        for mission in focus_missions[:3]:  # Top 3 missions
            for action in mission["actions"][:2]:  # Top 2 actions per mission
                action_count += 1
                summary_lines.append(f"{action_count}. [{mission['title']}]: {action}")
        
        if action_count == 0:
            summary_lines.append("No pending actions found. Great job!")
        
        summary_lines.append("")
        summary_lines.append(f"Mission Control: https://novamission.cloud")
        
        summary_text = "\n".join(summary_lines)
        
        self.stdout.write(summary_text)
        
        if options.get("voice"):
            self._generate_tts(summary_text)
        
        if options.get("notify"):
            self._send_notification(summary_text)
    
    def _extract_actions(self, mission_file: Path) -> list:
        """Extract Next 3 Actions from mission file."""
        try:
            with mission_file.open("r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            return []
        
        actions = []
        in_actions = False
        
        for line in lines:
            if line.strip().lower().startswith("## next 3 actions"):
                in_actions = True
                continue
            if in_actions:
                if line.strip().startswith("##"):
                    break
                # Match - item, * item, 1. item, etc.
                match = re.match(r'^[\s\-\*1-9\.]\s*(.+)$', line.strip())
                if match:
                    text = match.group(1).strip()
                    # Skip completed items (marked with ~~ or [x])
                    if not text.startswith("~~") and not text.startswith("[x]") and text:
                        # Remove strikethrough markdown
                        text = re.sub(r'~~(.+?)~~', r'\1', text)
                        text = re.sub(r'\s*✅.*$', '', text)
                        if text and not text.startswith("Create"):
                            actions.append(text)
        
        return actions[:3]  # Max 3 actions
    
    def _generate_tts(self, text: str):
        """Generate TTS audio via edge-tts."""
        import asyncio
        import edge_tts
        
        async def synth():
            communicate = edge_tts.Communicate(text, "en-US-AriaNeural")
            await communicate.save("/tmp/daily_summary.mp3")
        
        try:
            asyncio.run(synth())
            self.stdout.write(self.style.SUCCESS("TTS generated: /tmp/daily_summary.mp3"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"TTS failed: {e}"))
    
    def _send_notification(self, text: str):
        """Send notification via configured channels."""
        # Placeholder for WhatsApp/email notifications
        self.stdout.write(self.style.SUCCESS("Notification sent (placeholder)"))
