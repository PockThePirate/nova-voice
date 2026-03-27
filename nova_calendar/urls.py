"""
Nova Calendar - URL Configuration
"""

from django.urls import path
from . import views

app_name = 'nova_calendar'

urlpatterns = [
    # Main calendar page
    path('', views.calendar_view, name='calendar'),
    
    # Event APIs
    path('api/events/', views.get_events_api, name='api_events'),
    path('api/events/create/', views.create_event_api, name='api_create_event'),
    path('api/events/<uuid:event_id>/update/', views.update_event_api, name='api_update_event'),
    path('api/events/<uuid:event_id>/delete/', views.delete_event_api, name='api_delete_event'),
    
    # Reminder APIs
    path('api/events/<uuid:event_id>/reminders/', views.create_reminder_api, name='api_create_reminder'),
    path('api/reminders/<uuid:reminder_id>/delete/', views.delete_reminder_api, name='api_delete_reminder'),
    
    # Calendar APIs
    path('api/calendars/create/', views.create_calendar_api, name='api_create_calendar'),
    path('api/calendars/<uuid:calendar_id>/delete/', views.delete_calendar_api, name='api_delete_calendar'),
    
    # Cron Job APIs
    path('api/cron-jobs/create/', views.create_cron_job_api, name='api_create_cron_job'),
]
