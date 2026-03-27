"""
Nova Calendar - Django Models
Calendar management with cron job automation
"""

import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Calendar(models.Model):
    """Calendar container for events"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calendars')
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#3ef5ff')  # Hex color
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Ensure only one default calendar per user
        if self.is_default:
            Calendar.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class Tag(models.Model):
    """Tags for categorizing events"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calendar_tags', null=True, blank=True)
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#ff3ef5')
    
    class Meta:
        ordering = ['name']
        unique_together = ['user', 'name']
    
    def __str__(self):
        return self.name


class Event(models.Model):
    """Calendar events"""
    PRIORITY_CHOICES = [
        (1, 'Low'),
        (2, 'Below Average'),
        (3, 'Normal'),
        (4, 'High'),
        (5, 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('confirmed', 'Confirmed'),
        ('tentative', 'Tentative'),
        ('cancelled', 'Cancelled'),
    ]
    
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('public', 'Public'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    calendar = models.ForeignKey(Calendar, on_delete=models.CASCADE, related_name='events')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    location = models.CharField(max_length=200, blank=True)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    priority = models.IntegerField(choices=PRIORITY_CHOICES, default=3)
    tags = models.ManyToManyField(Tag, blank=True, related_name='events')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='confirmed')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='private')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['start_datetime']
        indexes = [
            models.Index(fields=['start_datetime']),
            models.Index(fields=['calendar', 'start_datetime']),
        ]
    
    def __str__(self):
        return f"{self.title} ({self.start_datetime})"
    
    @property
    def duration_minutes(self):
        """Calculate event duration in minutes"""
        delta = self.end_datetime - self.start_datetime
        return int(delta.total_seconds() / 60)


class RecurrenceRule(models.Model):
    """iCal-style recurrence rules for events"""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ]
    
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name='recurrence_rule')
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    interval = models.PositiveIntegerField(default=1)  # Every N days/weeks/etc
    days_of_week = models.JSONField(default=list, blank=True)  # [0,1,2] for Mon-Wed
    days_of_month = models.JSONField(default=list, blank=True)  # [1,15] for 1st & 15th
    months_of_year = models.JSONField(default=list, blank=True)  # [1,6,12] for Jan/Jun/Dec
    count = models.PositiveIntegerField(null=True, blank=True)  # End after N occurrences
    until_datetime = models.DateTimeField(null=True, blank=True)  # End by date
    
    def __str__(self):
        return f"{self.frequency} recurrence for {self.event.title}"


class Reminder(models.Model):
    """Email reminders for events"""
    METHOD_CHOICES = [
        ('email', 'Email'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='reminders')
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='email')
    minutes_before = models.PositiveIntegerField()  # e.g., 10, 60, 1440 (1 day)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['minutes_before']
    
    def __str__(self):
        return f"{self.method} reminder for {self.event.title} ({self.minutes_before} min before)"
    
    @property
    def trigger_datetime(self):
        """Calculate when this reminder should fire"""
        from datetime import timedelta
        return self.event.start_datetime - timedelta(minutes=self.minutes_before)


class CronJob(models.Model):
    """Scheduled jobs triggered by events"""
    SCHEDULE_TYPE_CHOICES = [
        ('once', 'Once'),
        ('recurring', 'Recurring'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='cron_jobs')
    name = models.CharField(max_length=100)
    schedule_type = models.CharField(max_length=20, choices=SCHEDULE_TYPE_CHOICES, default='once')
    trigger_datetime = models.DateTimeField()  # When to fire
    cron_expression = models.CharField(max_length=100, blank=True)  # For recurring jobs
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['trigger_datetime']
        indexes = [
            models.Index(fields=['enabled', 'next_run_at']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.event.title})"


class CronJobAction(models.Model):
    """Individual actions within a cron job"""
    ACTION_TYPE_CHOICES = [
        ('whatsapp_send', 'Send WhatsApp'),
        ('nova_voice_announce', 'Nova Voice Announcement'),
        ('run_script', 'Run Script'),
        ('email_send', 'Send Email'),
        ('webhook_post', 'Webhook POST'),
        ('mission_control_task', 'Mission Control Task'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cron_job = models.ForeignKey(CronJob, on_delete=models.CASCADE, related_name='actions')
    action_type = models.CharField(max_length=50, choices=ACTION_TYPE_CHOICES)
    config = models.JSONField()  # Action-specific configuration
    order = models.PositiveIntegerField(default=0)  # Execution order
    success = models.BooleanField(null=True, blank=True)  # Last run result
    last_run_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.action_type} for {self.cron_job.name}"
