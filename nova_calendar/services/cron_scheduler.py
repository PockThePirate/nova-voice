"""
Calendar Cron Scheduler - Checks and executes due cron jobs every minute
"""

import logging
from datetime import timedelta
from django.utils import timezone
from nova_calendar.models import CronJob, CronJobAction
from django.contrib.auth.models import User

logger = logging.getLogger('nova_calendar')


class CalendarCronScheduler:
    """
    Scheduler that runs every minute to check and execute due cron jobs.
    """
    
    def __init__(self):
        self.logger = logger
    
    def check_and_run_due_jobs(self):
        """
        Find all due cron jobs and execute them.
        Call this every minute from a management command or cron job.
        """
        now = timezone.now()
        
        # Find all enabled jobs that are due
        due_jobs = CronJob.objects.filter(
            enabled=True,
            next_run_at__lte=now,
            next_run_at__isnull=False
        ).select_related('event').prefetch_related('actions')
        
        executed_count = 0
        failed_count = 0
        
        for job in due_jobs:
            try:
                self.execute_job(job)
                executed_count += 1
            except Exception as e:
                self.logger.error(f"Failed to execute cron job {job.id}: {e}")
                failed_count += 1
        
        return {
            'executed': executed_count,
            'failed': failed_count,
            'total_due': due_jobs.count()
        }
    
    def execute_job(self, job: CronJob):
        """
        Execute a single cron job and all its actions.
        """
        self.logger.info(f"Executing cron job: {job.name} for event: {job.event.title}")
        
        # Execute each action in order
        for action in job.actions.all().order_by('order'):
            try:
                self.execute_action(action, job.event)
                action.success = True
                action.last_run_at = timezone.now()
                action.error_message = ''
            except Exception as e:
                self.logger.error(f"Action {action.id} failed: {e}")
                action.success = False
                action.error_message = str(e)
            
            action.save()
        
        # Update job last run time
        job.last_run_at = timezone.now()
        
        # Calculate next run time for recurring jobs
        if job.schedule_type == 'recurring' and job.cron_expression:
            job.next_run_at = self.calculate_next_run(job.cron_expression)
        else:
            job.next_run_at = None
            job.enabled = False  # Disable one-time jobs after execution
        
        job.save()
        
        self.logger.info(f"Cron job {job.id} completed successfully")
    
    def execute_action(self, action: CronJobAction, event):
        """
        Execute a single cron job action.
        """
        config = action.config
        
        if action.action_type == 'whatsapp_send':
            self.send_whatsapp(config, event)
        
        elif action.action_type == 'email_send':
            self.send_email(config, event)
        
        elif action.action_type == 'nova_voice_announce':
            self.trigger_nova_voice(config, event)
        
        elif action.action_type == 'run_script':
            self.run_script(config, event)
        
        elif action.action_type == 'webhook_post':
            self.send_webhook(config, event)
        
        elif action.action_type == 'mission_control_task':
            self.create_mission_task(config, event)
        
        else:
            raise ValueError(f"Unknown action type: {action.action_type}")
    
    def send_whatsapp(self, config: dict, event):
        """
        Send WhatsApp message.
        Config: {to: "+1...", message: "..."}
        """
        to_number = config.get('to', '')
        message = config.get('message', '').replace('{event_title}', event.title)
        
        if not to_number:
            raise ValueError("WhatsApp 'to' number is required")
        
        # Use OpenClaw's message tool
        from openclaw_cli import send_message
        send_message(
            channel='whatsapp',
            to=to_number,
            message=message
        )
        
        self.logger.info(f"WhatsApp sent to {to_number}: {message[:50]}...")
    
    def send_email(self, config: dict, event):
        """
        Send email.
        Config: {to: "...", subject: "...", body: "..."}
        """
        from django.core.mail import send_mail
        from django.conf import settings
        
        to_email = config.get('to', '')
        subject = config.get('subject', f'Reminder: {event.title}')
        body = config.get('body', f'Event reminder: {event.title}\n\nWhen: {event.start_datetime}\nWhere: {event.location}')
        
        if not to_email:
            # Fall back to user's email
            to_email = event.calendar.user.email
        
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
        
        self.logger.info(f"Email sent to {to_email}: {subject}")
    
    def trigger_nova_voice(self, config: dict, event):
        """
        Trigger Nova voice announcement.
        Config: {message: "...", voice: "Nova"}
        """
        message = config.get('message', f'Reminder: {event.title} starts soon')
        
        # Use OpenClaw agent to speak
        from openclaw_cli import agent_speak
        agent_speak(
            agent='nova',
            message=message
        )
        
        self.logger.info(f"Nova voice announcement: {message[:50]}...")
    
    def run_script(self, config: dict, event):
        """
        Run a shell script.
        Config: {path: "/path/to/script.sh", args: [...]}
        """
        import subprocess
        
        script_path = config.get('path', '')
        args = config.get('args', [])
        
        if not script_path:
            raise ValueError("Script path is required")
        
        cmd = [script_path] + args
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Script failed: {result.stderr}")
        
        self.logger.info(f"Script executed: {script_path}")
    
    def send_webhook(self, config: dict, event):
        """
        Send webhook POST request.
        Config: {url: "...", method: "POST", body: {...}}
        """
        import requests
        
        url = config.get('url', '')
        method = config.get('method', 'POST').upper()
        body = config.get('body', {})
        
        # Substitute event data in body
        body = self.substitute_event_data(body, event)
        
        response = requests.request(
            method=method,
            url=url,
            json=body,
            timeout=30
        )
        
        response.raise_for_status()
        
        self.logger.info(f"Webhook sent to {url}: {response.status_code}")
    
    def create_mission_task(self, config: dict, event):
        """
        Create a Mission Control task.
        Config: {mission_id: "...", action: "start_mission"}
        """
        # This would integrate with Mission Control's task system
        # For now, just log it
        mission_id = config.get('mission_id', '')
        action = config.get('action', 'create_task')
        
        self.logger.info(f"Mission Control task: {action} for mission {mission_id}")
    
    def substitute_event_data(self, data: dict, event) -> dict:
        """
        Replace placeholders in data with event information.
        """
        import json
        data_str = json.dumps(data)
        
        replacements = {
            '{event_title}': event.title,
            '{event_description}': event.description,
            '{event_location}': event.location,
            '{event_start}': str(event.start_datetime),
            '{event_end}': str(event.end_datetime),
            '{calendar_name}': event.calendar.name,
        }
        
        for placeholder, value in replacements.items():
            data_str = data_str.replace(placeholder, str(value))
        
        return json.loads(data_str)
    
    def calculate_next_run(self, cron_expression: str):
        """
        Calculate next run time from cron expression.
        For now, just returns None - proper cron parsing would use python-crontab
        """
        # TODO: Implement proper cron parsing
        # For now, recurring jobs need manual next_run_at updates
        return None
