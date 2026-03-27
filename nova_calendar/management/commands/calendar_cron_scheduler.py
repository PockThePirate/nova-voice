"""
Management command to run calendar cron scheduler
Run this every minute via system cron or OpenClaw gateway cron
"""

from django.core.management.base import BaseCommand
from nova_calendar.services.cron_scheduler import CalendarCronScheduler


class Command(BaseCommand):
    help = 'Run calendar cron job scheduler - checks and executes due jobs'
    
    def handle(self, *args, **options):
        self.stdout.write('Starting calendar cron scheduler...')
        
        scheduler = CalendarCronScheduler()
        result = scheduler.check_and_run_due_jobs()
        
        self.stdout.write(
            self.style.SUCCESS(
                f"Scheduler completed: {result['executed']} executed, "
                f"{result['failed']} failed, {result['total_due']} total due"
            )
        )
        
        return result
