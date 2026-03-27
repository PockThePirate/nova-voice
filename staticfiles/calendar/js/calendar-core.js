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
      location.reload(); // Reload to show new calendar
    } else {
      alert('Error: ' + result.error);
    }
  })
  .catch(err => {
    alert('Error creating calendar: ' + err);
  });
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

// Quick Add (simple version - full NLP later)
function parseQuickAdd() {
  const text = document.getElementById('quickAddText').value.trim();
  if (!text) return;
  
  // Simple parsing - will enhance with NLP library later
  const preview = document.getElementById('quickAddPreview');
  document.getElementById('previewTitle').textContent = text;
  document.getElementById('previewWhen').textContent = 'Tomorrow (demo)';
  document.getElementById('previewDuration').textContent = '1 hour';
  preview.style.display = 'block';
}

function confirmQuickAdd() {
  const text = document.getElementById('quickAddText').value.trim();
  if (!text) return;
  
  // Create event with parsed data (demo for now)
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(12, 0, 0, 0);
  
  const data = {
    title: text,
    start: tomorrow.toISOString(),
    end: new Date(tomorrow.getTime() + 60 * 60 * 1000).toISOString(),
    all_day: false,
    calendar_id: document.getElementById('eventCalendar')?.value || '',
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
    } else {
      alert('Error: ' + result.error);
    }
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
