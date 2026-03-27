/**
 * Nova Calendar - Core JavaScript
 * Stark-themed calendar with FullCalendar integration
 */

let calendar = null;
let visibleCalendars = new Set();

// Initialize calendar on page load
document.addEventListener('DOMContentLoaded', function() {
  initCalendar();
  loadVisibleCalendars();
});

function initCalendar() {
  const calendarEl = document.getElementById('calendar');
  
  calendar = new FullCalendar.Calendar(calendarEl, {
    initialView: 'dayGridMonth',
    headerToolbar: {
      left: 'prev,next today',
      center: 'title',
      right: 'dayGridMonth,timeGridWeek,timeGridDay,listMonth'
    },
    themeSystem: 'standard',
    editable: true,
    selectable: true,
    dayMaxEvents: true,
    height: '100%',
    
    // Event handlers
    eventClick: function(info) {
      openEventModal(info.event);
    },
    
    dateClick: function(info) {
      openEventModal(null, info.dateStr);
    },
    
    eventDrop: function(info) {
      updateEventTime(info.event);
    },
    
    eventResize: function(info) {
      updateEventTime(info.event);
    },
    
    // Fetch events from API
    events: function(info, successCallback, failureCallback) {
      fetch(`/calendar/api/events/?start=${info.startStr}&end=${info.endStr}`)
        .then(r => r.json())
        .then(data => {
          const events = data.events.map(e => ({
            id: e.id,
            title: e.title,
            start: e.start,
            end: e.end,
            allDay: e.allDay,
            backgroundColor: e.backgroundColor,
            borderColor: e.borderColor,
            extendedProps: e
          }));
          successCallback(events);
        })
        .catch(failureCallback);
    }
  });
  
  calendar.render();
}

function loadVisibleCalendars() {
  // Initialize visible calendars from checkboxes
  document.querySelectorAll('.calendar-list-item input[type="checkbox"]').forEach(cb => {
    if (cb.checked) {
      visibleCalendars.add(cb.id.replace('cal-', ''));
    }
  });
}

function toggleCalendar(calendarId) {
  const checkbox = document.getElementById(`cal-${calendarId}`);
  
  if (checkbox.checked) {
    visibleCalendars.add(calendarId);
  } else {
    visibleCalendars.delete(calendarId);
  }
  
  calendar.refetchEvents();
}

// Modal functions
function openEventModal(event = null, dateStr = null) {
  const modal = document.getElementById('eventModal');
  const title = document.getElementById('modalTitle');
  const form = document.getElementById('eventForm');
  const deleteBtn = document.getElementById('deleteBtn');
  
  // Reset form
  form.reset();
  document.getElementById('eventId').value = '';
  
  if (event) {
    // Edit existing event
    title.textContent = 'Edit Event';
    deleteBtn.style.display = 'block';
    
    document.getElementById('eventId').value = event.id;
    document.getElementById('eventTitle').value = event.title;
    document.getElementById('eventStart').value = formatDateTimeLocal(event.start);
    document.getElementById('eventEnd').value = formatDateTimeLocal(event.end);
    document.getElementById('eventAllDay').checked = event.allDay;
    document.getElementById('eventCalendar').value = event.extendedProps.calendarId || '';
    document.getElementById('eventLocation').value = event.extendedProps.location || '';
    document.getElementById('eventDescription').value = event.extendedProps.description || '';
    document.getElementById('eventPriority').value = event.extendedProps.priority || 3;
  } else {
    // Create new event
    title.textContent = 'Add Event';
    deleteBtn.style.display = 'none';
    
    if (dateStr) {
      const start = new Date(dateStr);
      const end = new Date(start.getTime() + 60 * 60 * 1000); // 1 hour default
      document.getElementById('eventStart').value = toDateTimeLocal(start);
      document.getElementById('eventEnd').value = toDateTimeLocal(end);
    }
  }
  
  modal.classList.add('active');
}

function closeEventModal() {
  document.getElementById('eventModal').classList.remove('active');
}

function openQuickAdd() {
  document.getElementById('quickAddModal').classList.add('active');
  document.getElementById('quickAddText').focus();
}

function closeQuickAdd() {
  document.getElementById('quickAddModal').classList.remove('active');
  document.getElementById('quickAddText').value = '';
  document.getElementById('quickAddPreview').style.display = 'none';
}

function openCreateCalendarModal() {
  document.getElementById('createCalendarModal').classList.add('active');
  document.getElementById('newCalendarName').focus();
}

function closeCreateCalendarModal() {
  document.getElementById('createCalendarModal').classList.remove('active');
  document.getElementById('newCalendarName').value = '';
  document.getElementById('newCalendarDesc').value = '';
  document.getElementById('newCalendarColor').value = '#3ef5ff';
}

function setColor(color) {
  document.getElementById('newCalendarColor').value = color;
}

function createCalendar(e) {
  e.preventDefault();
  
  const name = document.getElementById('newCalendarName').value.trim();
  const color = document.getElementById('newCalendarColor').value;
  const description = document.getElementById('newCalendarDesc').value.trim();
  
  if (!name) {
    alert('Calendar name is required');
    return;
  }
  
  fetch('/calendar/api/calendars/create/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ name, color, description })
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      closeCreateCalendarModal();
      location.reload();
    } else {
      alert('Error: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error creating calendar: ' + err);
  });
}

// Cron Job Modal functions
function openCronJobModal() {
  const eventId = document.getElementById('eventId').value;
  if (!eventId) return;
  
  document.getElementById('cronJobEventId').value = eventId;
  document.getElementById('cronJobModal').classList.add('active');
}

function closeCronJobModal() {
  document.getElementById('cronJobModal').classList.remove('active');
  document.getElementById('cronJobName').value = '';
}

function updateTriggerFields() {
  const trigger = document.getElementById('cronJobTrigger').value;
  document.getElementById('triggerBeforeField').style.display = (trigger === 'before') ? 'block' : 'none';
  document.getElementById('triggerCustomField').style.display = (trigger === 'custom') ? 'block' : 'none';
}

function updateActionFields() {
  const actionType = document.getElementById('cronJobActionType').value;
  document.querySelectorAll('.action-fields').forEach(el => el.style.display = 'none');
  
  if (actionType === 'whatsapp_send') {
    document.getElementById('actionWhatsappFields').style.display = 'block';
  } else if (actionType === 'email_send') {
    document.getElementById('actionEmailFields').style.display = 'block';
  }
}

function saveCronJob(e) {
  e.preventDefault();
  
  const eventId = document.getElementById('cronJobEventId').value;
  const trigger = document.getElementById('cronJobTrigger').value;
  const actionType = document.getElementById('cronJobActionType').value;
  
  let triggerDatetime;
  if (trigger === 'at_event') {
    triggerDatetime = document.getElementById('eventStart').value;
  } else if (trigger === 'before') {
    const value = parseInt(document.getElementById('triggerBeforeValue').value);
    const unit = document.getElementById('triggerBeforeUnit').value;
    // Calculate datetime based on event start minus offset
    const eventStart = new Date(document.getElementById('eventStart').value);
    const offset = unit === 'minutes' ? value * 60000 : unit === 'hours' ? value * 3600000 : value * 86400000;
    triggerDatetime = new Date(eventStart.getTime() - offset).toISOString();
  } else {
    triggerDatetime = new Date(document.getElementById('triggerCustomDatetime').value).toISOString();
  }
  
  let config = {};
  if (actionType === 'whatsapp_send') {
    config = {
      to: document.getElementById('actionTo').value,
      message: document.getElementById('actionMessage').value
    };
  } else if (actionType === 'email_send') {
    config = {
      to: document.getElementById('actionEmailTo').value,
      subject: document.getElementById('actionEmailSubject').value,
      body: document.getElementById('actionEmailBody').value
    };
  }
  
  const data = {
    event_id: eventId,
    name: document.getElementById('cronJobName').value,
    trigger_datetime: triggerDatetime,
    schedule_type: 'once',
    actions: [{
      action_type: actionType,
      config: config,
      order: 0
    }]
  };
  
  fetch('/calendar/api/cron-jobs/create/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify(data)
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      closeCronJobModal();
      alert('✅ Cron job scheduled!');
    } else {
      alert('Error: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error creating cron job: ' + err);
  });
}

function testCronJob() {
  alert('Test run feature coming soon!');
}

// Form handlers
function toggleAllDay() {
  const isAllDay = document.getElementById('eventAllDay').checked;
  const startInput = document.getElementById('eventStart');
  const endInput = document.getElementById('eventEnd');
  
  if (isAllDay) {
    startInput.type = 'date';
    endInput.type = 'date';
  } else {
    startInput.type = 'datetime-local';
    endInput.type = 'datetime-local';
  }
}

function saveEvent(e) {
  e.preventDefault();
  
  const eventId = document.getElementById('eventId').value;
  const isEdit = !!eventId;
  
  const data = {
    title: document.getElementById('eventTitle').value,
    start: new Date(document.getElementById('eventStart').value).toISOString(),
    end: new Date(document.getElementById('eventEnd').value).toISOString(),
    all_day: document.getElementById('eventAllDay').checked,
    calendar_id: document.getElementById('eventCalendar').value,
    location: document.getElementById('eventLocation').value,
    description: document.getElementById('eventDescription').value,
    priority: parseInt(document.getElementById('eventPriority').value),
  };
  
  const url = isEdit 
    ? `/calendar/api/events/${eventId}/update/`
    : '/calendar/api/events/create/';
  
  const method = isEdit ? 'PUT' : 'POST';
  
  fetch(url, {
    method: method,
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify(data)
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      closeEventModal();
      calendar.refetchEvents();
    } else {
      alert('Error: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error saving event: ' + err);
  });
}

function deleteEvent() {
  const eventId = document.getElementById('eventId').value;
  if (!eventId) return;
  
  if (!confirm('Are you sure you want to delete this event?')) return;
  
  fetch(`/calendar/api/events/${eventId}/delete/`, {
    method: 'DELETE',
    headers: {
      'X-CSRFToken': getCookie('csrftoken')
    }
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      closeEventModal();
      calendar.refetchEvents();
    } else {
      alert('Error: ' + result.error);
    }
  });
}

function updateEventTime(event) {
  const data = {
    start: event.start.toISOString(),
    end: event.end ? event.end.toISOString() : event.start.toISOString(),
  };
  
  fetch(`/calendar/api/events/${event.id}/update/`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify(data)
  })
  .catch(err => console.error('Error updating event time:', err));
}

// Quick Add with Natural Language Parsing
function parseQuickAdd() {
  const text = document.getElementById('quickAddText').value.trim();
  if (!text) return;
  
  // Send to backend for NLP parsing
  fetch('/calendar/api/quick-add/parse/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({ text: text })
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      const parsed = result.parsed;
      
      // Show preview
      document.getElementById('previewTitle').textContent = parsed.title;
      document.getElementById('previewWhen').textContent = new Date(parsed.start).toLocaleString('en-US', {
        weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
      });
      
      const durationMin = (new Date(parsed.end) - new Date(parsed.start)) / 60000;
      document.getElementById('previewDuration').textContent = durationMin >= 1440 ? 'All day' : `${durationMin} minutes`;
      
      const calendarSelect = document.getElementById('quickAddCalendar');
      document.getElementById('previewCalendar').textContent = calendarSelect.options[calendarSelect.selectedIndex]?.text || 'Default';
      
      if (parsed.is_recurring) {
        document.getElementById('previewRecurrence').style.display = 'block';
        document.getElementById('previewRecurrenceText').textContent = `Every ${parsed.recurrence.frequency}`;
      } else {
        document.getElementById('previewRecurrence').style.display = 'none';
      }
      
      document.getElementById('quickAddPreview').style.display = 'block';
      
      // Store parsed data for confirmation
      window.quickAddParsed = parsed;
    } else {
      alert('Error parsing: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error: ' + err);
  });
}

function confirmQuickAdd() {
  const parsed = window.quickAddParsed;
  if (!parsed) return;
  
  const durationMin = parseInt(document.getElementById('quickAddDuration').value);
  const calendarId = document.getElementById('quickAddCalendar').value;
  
  const data = {
    title: parsed.title,
    start: parsed.start,
    end: parsed.end,
    all_day: durationMin >= 1440,
    calendar_id: calendarId,
    location: parsed.location || '',
    description: '',
  };
  
  fetch('/calendar/api/events/create/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify(data)
  })
  .then(r => r.json())
  .then(result => {
    if (result.success) {
      closeQuickAdd();
      calendar.refetchEvents();
      
      // Create recurrence rule if needed
      if (parsed.is_recurring && result.event?.id) {
        fetch(`/calendar/api/events/${result.event.id}/recurrence/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
          },
          body: JSON.stringify(parsed.recurrence)
        }).catch(() => {}); // Ignore errors for now
      }
    } else {
      alert('Error: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error: ' + err);
  });
}

// Utility functions
function formatDateTimeLocal(date) {
  if (!date) return '';
  const d = new Date(date);
  return toDateTimeLocal(d);
}

function toDateTimeLocal(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}
