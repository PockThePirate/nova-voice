"""
Nova Calendar - Django Admin
"""

from django.contrib import admin
from .models import Calendar, Tag, Event, RecurrenceRule, Reminder, CronJob, CronJobAction


@admin.register(Calendar)
class CalendarAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'color', 'is_default', 'created_at']
    list_filter = ['user', 'is_default']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'color']
    list_filter = ['user']
    search_fields = ['name']


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'calendar', 'start_datetime', 'end_datetime', 'priority', 'status']
    list_filter = ['calendar', 'priority', 'status', 'visibility', 'all_day']
    search_fields = ['title', 'description', 'location']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['tags']
    date_hierarchy = 'start_datetime'


@admin.register(RecurrenceRule)
class RecurrenceRuleAdmin(admin.ModelAdmin):
    list_display = ['event', 'frequency', 'interval', 'count', 'until_datetime']
    list_filter = ['frequency']


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ['event', 'method', 'minutes_before', 'sent_at', 'created_at']
    list_filter = ['method', 'sent_at']
    readonly_fields = ['created_at']


@admin.register(CronJob)
class CronJobAdmin(admin.ModelAdmin):
    list_display = ['name', 'event', 'schedule_type', 'trigger_datetime', 'enabled', 'last_run_at', 'next_run_at']
    list_filter = ['schedule_type', 'enabled']
    search_fields = ['name']
    readonly_fields = ['created_at', 'updated_at', 'last_run_at', 'next_run_at']


@admin.register(CronJobAction)
class CronJobActionAdmin(admin.ModelAdmin):
    list_display = ['action_type', 'cron_job', 'order', 'success', 'last_run_at']
    list_filter = ['action_type', 'success']
    readonly_fields = ['last_run_at', 'error_message']
