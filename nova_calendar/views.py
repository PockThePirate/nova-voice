"""
Nova Calendar - Views
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import datetime, timedelta
import json

from .models import Calendar, Event, Tag, Reminder, CronJob, CronJobAction


@login_required
def calendar_view(request):
    """Main calendar page"""
    calendars = Calendar.objects.filter(user=request.user)
    tags = Tag.objects.filter(user=request.user) | Tag.objects.filter(user=None)
    
    # Get default calendar or create one
    default_calendar = calendars.filter(is_default=True).first()
    if not default_calendar and calendars.exists():
        default_calendar = calendars.first()
    
    context = {
        'calendars': calendars,
        'tags': tags,
        'default_calendar': default_calendar,
    }
    return render(request, 'calendar/calendar.html', context)


@login_required
@require_http_methods(["GET"])
def get_events_api(request):
    """Get events for calendar view (filterable by date range)"""
    # Get date range from query params
    start = request.GET.get('start')
    end = request.GET.get('end')
    calendar_id = request.GET.get('calendar')
    
    # Default to current month if not specified
    if not start or not end:
        now = timezone.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
    else:
        start = datetime.fromisoformat(start.replace('Z', '+00:00'))
        end = datetime.fromisoformat(end.replace('Z', '+00:00'))
    
    # Filter events
    events = Event.objects.filter(
        calendar__user=request.user,
        start_datetime__gte=start,
        end_datetime__lte=end
    ).select_related('calendar').prefetch_related('tags')
    
    # Filter by calendar if specified
    if calendar_id:
        events = events.filter(calendar_id=calendar_id)
    
    # Format for FullCalendar
    events_data = []
    for event in events:
        events_data.append({
            'id': str(event.id),
            'title': event.title,
            'start': event.start_datetime.isoformat(),
            'end': event.end_datetime.isoformat(),
            'allDay': event.all_day,
            'backgroundColor': event.calendar.color,
            'borderColor': event.calendar.color,
            'calendarId': str(event.calendar.id),
            'calendarName': event.calendar.name,
            'description': event.description,
            'location': event.location,
            'priority': event.priority,
        })
    
    return JsonResponse({'events': events_data})


@login_required
@require_http_methods(["POST"])
def create_event_api(request):
    """Create a new event"""
    try:
        data = json.loads(request.body)
        
        # Get or create calendar
        calendar_id = data.get('calendar_id')
        if calendar_id:
            calendar = get_object_or_404(Calendar, id=calendar_id, user=request.user)
        else:
            calendar = Calendar.objects.filter(user=request.user, is_default=True).first()
            if not calendar:
                calendar = Calendar.objects.create(
                    user=request.user,
                    name='Primary',
                    is_default=True
                )
        
        # Parse datetimes
        start_datetime = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        end_datetime = datetime.fromisoformat(data['end'].replace('Z', '+00:00')) if data.get('end') else start_datetime + timedelta(hours=1)
        
        # Create event
        event = Event.objects.create(
            calendar=calendar,
            title=data.get('title', 'New Event'),
            description=data.get('description', ''),
            location=data.get('location', ''),
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            all_day=data.get('all_day', False),
            priority=data.get('priority', 3),
        )
        
        return JsonResponse({
            'success': True,
            'event': {
                'id': str(event.id),
                'title': event.title,
                'start': event.start_datetime.isoformat(),
                'end': event.end_datetime.isoformat(),
            }
        }, status=201)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["PUT"])
def update_event_api(request, event_id):
    """Update an existing event"""
    try:
        event = get_object_or_404(Event, id=event_id, calendar__user=request.user)
        data = json.loads(request.body)
        
        # Update fields
        if 'title' in data:
            event.title = data['title']
        if 'description' in data:
            event.description = data['description']
        if 'location' in data:
            event.location = data['location']
        if 'start' in data:
            event.start_datetime = datetime.fromisoformat(data['start'].replace('Z', '+00:00'))
        if 'end' in data:
            event.end_datetime = datetime.fromisoformat(data['end'].replace('Z', '+00:00'))
        if 'all_day' in data:
            event.all_day = data['all_day']
        if 'priority' in data:
            event.priority = data['priority']
        if 'calendar_id' in data:
            calendar = get_object_or_404(Calendar, id=data['calendar_id'], user=request.user)
            event.calendar = calendar
        
        event.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_event_api(request, event_id):
    """Delete an event"""
    try:
        event = get_object_or_404(Event, id=event_id, calendar__user=request.user)
        event.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["GET", "POST"])
def create_reminder_api(request, event_id):
    """Create or list reminders for an event"""
    event = get_object_or_404(Event, id=event_id, calendar__user=request.user)
    
    if request.method == 'GET':
        reminders = Reminder.objects.filter(event=event)
        data = [{
            'id': str(r.id),
            'method': r.method,
            'minutes_before': r.minutes_before,
            'sent_at': r.sent_at.isoformat() if r.sent_at else None,
        } for r in reminders]
        return JsonResponse({'reminders': data})
    
    elif request.method == 'POST':
        data = json.loads(request.body)
        reminder = Reminder.objects.create(
            event=event,
            method=data.get('method', 'email'),
            minutes_before=data.get('minutes_before', 10)
        )
        return JsonResponse({
            'success': True,
            'reminder': {
                'id': str(reminder.id),
                'minutes_before': reminder.minutes_before,
            }
        }, status=201)


@login_required
@require_http_methods(["DELETE"])
def delete_reminder_api(request, reminder_id):
    """Delete a reminder"""
    try:
        reminder = get_object_or_404(Reminder, id=reminder_id, event__calendar__user=request.user)
        reminder.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def create_calendar_api(request):
    """Create a new calendar"""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        color = data.get('color', '#3ef5ff')
        description = data.get('description', '')
        
        if not name:
            return JsonResponse({'success': False, 'error': 'Name is required'}, status=400)
        
        calendar = Calendar.objects.create(
            user=request.user,
            name=name,
            color=color,
            description=description
        )
        
        return JsonResponse({
            'success': True,
            'calendar': {
                'id': str(calendar.id),
                'name': calendar.name,
                'color': calendar.color,
            }
        }, status=201)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["DELETE"])
def delete_calendar_api(request, calendar_id):
    """Delete a calendar"""
    try:
        calendar = get_object_or_404(Calendar, id=calendar_id, user=request.user)
        event_count = calendar.events.count()
        calendar.delete()
        return JsonResponse({
            'success': True,
            'deleted_events': event_count
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def parse_quick_add_api(request):
    """Parse natural language quick add text"""
    try:
        data = json.loads(request.body)
        text = data.get('text', '')
        
        if not text:
            return JsonResponse({'success': False, 'error': 'Text is required'}, status=400)
        
        from nova_calendar.services.nlp_parser import QuickAddParser
        parser = QuickAddParser()
        parsed = parser.parse(text)
        
        # Convert datetime to ISO format
        if parsed['start']:
            parsed['start'] = parsed['start'].isoformat()
        if parsed['end']:
            parsed['end'] = parsed['end'].isoformat()
        
        return JsonResponse({'success': True, 'parsed': parsed})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def create_recurrence_api(request, event_id):
    """Create recurrence rule for an event"""
    try:
        event = get_object_or_404(Event, id=event_id, calendar__user=request.user)
        data = json.loads(request.body)
        
        # Delete existing recurrence if any
        RecurrenceRule.objects.filter(event=event).delete()
        
        # Create new recurrence rule
        recurrence = RecurrenceRule.objects.create(
            event=event,
            frequency=data.get('frequency', 'weekly'),
            interval=data.get('interval', 1),
            days_of_week=data.get('days_of_week', []),
        )
        
        return JsonResponse({
            'success': True,
            'recurrence': {
                'frequency': recurrence.frequency,
                'interval': recurrence.interval,
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@login_required
@require_http_methods(["POST"])
def create_cron_job_api(request):
    """Create a cron job for an event"""
    try:
        data = json.loads(request.body)
        event_id = data.get('event_id')
        event = get_object_or_404(Event, id=event_id, calendar__user=request.user)
        
        # Create cron job
        from datetime import datetime
        trigger_dt = datetime.fromisoformat(data['trigger_datetime'].replace('Z', '+00:00'))
        
        cron_job = CronJob.objects.create(
            event=event,
            name=data.get('name', 'Scheduled Action'),
            schedule_type=data.get('schedule_type', 'once'),
            trigger_datetime=trigger_dt,
            next_run_at=trigger_dt,
            enabled=True
        )
        
        # Create actions
        actions = data.get('actions', [])
        for idx, action_data in enumerate(actions):
            CronJobAction.objects.create(
                cron_job=cron_job,
                action_type=action_data['action_type'],
                config=action_data.get('config', {}),
                order=action_data.get('order', idx)
            )
        
        return JsonResponse({
            'success': True,
            'cron_job': {
                'id': str(cron_job.id),
                'name': cron_job.name,
                'trigger_datetime': cron_job.trigger_datetime.isoformat(),
            }
        }, status=201)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
