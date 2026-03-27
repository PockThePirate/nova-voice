"""
Natural Language Parser for Quick Add
Parse phrases like "lunch with John tomorrow at noon" into structured event data
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class QuickAddParser:
    """
    Parse natural language event descriptions into structured data.
    
    Examples:
        "lunch with John tomorrow at noon"
        "dentist appointment next Monday 2pm"
        "team meeting every Monday 9am"
        "birthday party March 15th all day"
    """
    
    def __init__(self):
        self.ct = ZoneInfo('America/Chicago')
        self.now = datetime.now(self.ct)
        
        # Relative date patterns
        self.relative_dates = {
            'today': 0,
            'tonight': 0,
            'tomorrow': 1,
            'tmr': 1,
            'next week': 7,
            'week from now': 7,
            'next month': 30,
            'month from now': 30,
        }
        
        # Day of week mapping
        self.days_of_week = {
            'monday': 0, 'mon': 0,
            'tuesday': 1, 'tue': 1, 'tues': 1,
            'wednesday': 2, 'wed': 2,
            'thursday': 3, 'thu': 3, 'thur': 3, 'thurs': 3,
            'friday': 4, 'fri': 4,
            'saturday': 5, 'sat': 5,
            'sunday': 6, 'sun': 6,
        }
        
        # Time patterns
        self.time_patterns = {
            'morning': (8, 0),
            'noon': (12, 0),
            'afternoon': (14, 0),
            'evening': (18, 0),
            'night': (20, 0),
            'midnight': (0, 0),
        }
    
    def parse(self, text: str, default_duration_minutes: int = 60) -> dict:
        """
        Parse natural language text into event data.
        
        Args:
            text: Natural language description
            default_duration_minutes: Default event duration
            
        Returns:
            dict with keys: title, start, end, all_day, is_recurring, recurrence
            
        Example:
            parser.parse("lunch with John tomorrow at noon")
            → {
                'title': 'Lunch with John',
                'start': datetime(2026, 3, 28, 12, 0),
                'end': datetime(2026, 3, 28, 13, 0),
                'all_day': False,
                'is_recurring': False,
                'recurrence': None
            }
        """
        text = text.lower().strip()
        
        result = {
            'title': text,
            'start': None,
            'end': None,
            'all_day': False,
            'is_recurring': False,
            'recurrence': None,
            'location': '',
        }
        
        # Check for all-day event
        if 'all day' in text or 'all-day' in text or 'allday' in text:
            result['all_day'] = True
        
        # Check for recurrence
        recurrence_keywords = ['every', 'each', 'recurring', 'repeat']
        if any(kw in text for kw in recurrence_keywords):
            result['is_recurring'] = True
            result['recurrence'] = self._parse_recurrence(text)
        
        # Extract time
        time_parsed = self._parse_time(text)
        
        # Extract date
        date_parsed = self._parse_date(text)
        
        # Build datetime
        if date_parsed and time_parsed:
            result['start'] = date_parsed.replace(
                hour=time_parsed['hour'],
                minute=time_parsed['minute']
            )
        elif date_parsed:
            if result['all_day']:
                result['start'] = date_parsed
            else:
                result['start'] = date_parsed.replace(
                    hour=time_parsed.get('hour', 9),
                    minute=time_parsed.get('minute', 0)
                )
        elif time_parsed:
            # No date, assume today or next occurrence of time
            result['start'] = self.now.replace(
                hour=time_parsed['hour'],
                minute=time_parsed['minute'],
                second=0,
                microsecond=0
            )
            # If time already passed today, move to tomorrow
            if result['start'] < self.now:
                result['start'] += timedelta(days=1)
        else:
            # No date or time, default to tomorrow at 9am
            result['start'] = (self.now + timedelta(days=1)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
        
        # Set end time
        if result['start']:
            if result['all_day']:
                result['end'] = result['start'] + timedelta(days=1)
            else:
                result['end'] = result['start'] + timedelta(minutes=default_duration_minutes)
        
        # Extract title (remove parsed parts)
        result['title'] = self._extract_title(text)
        
        # Extract location
        location_patterns = [
            r'at\s+([^(at|on|in)]+?)(?:\s+(?:at|on|in|\d)|$)',
            r'in\s+([^(at|on|in)]+?)(?:\s+(?:at|on|in|\d)|$)',
            r'@\s*([^\s]+)',
        ]
        for pattern in location_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                result['location'] = match.group(1).strip()
                break
        
        return result
    
    def _parse_time(self, text: str) -> dict:
        """Extract time from text."""
        
        # Check for named times (noon, morning, etc.)
        for name, (hour, minute) in self.time_patterns.items():
            if name in text:
                return {'hour': hour, 'minute': minute}
        
        # Check for explicit times (2pm, 14:00, 2:30pm, etc.)
        time_patterns = [
            r'(\d{1,2})\s*:\s*(\d{2})\s*(am|pm)?',  # 2:30pm or 14:30
            r'(\d{1,2})\s*(am|pm)',  # 2pm
            r'(\d{4})',  # 1400 (military time)
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) == 3 and groups[0] and groups[1]:  # 2:30pm
                    hour = int(groups[0])
                    minute = int(groups[1])
                    ampm = groups[2]
                    if ampm and ampm.lower() == 'pm' and hour != 12:
                        hour += 12
                    elif ampm and ampm.lower() == 'am' and hour == 12:
                        hour = 0
                    return {'hour': hour, 'minute': minute}
                
                elif len(groups) == 2 and groups[1]:  # 2pm
                    hour = int(groups[0])
                    ampm = groups[1]
                    if ampm.lower() == 'pm' and hour != 12:
                        hour += 12
                    elif ampm.lower() == 'am' and hour == 12:
                        hour = 0
                    return {'hour': hour, 'minute': 0}
                
                elif len(groups) == 1 and groups[0] and len(groups[0]) == 4:  # 1400
                    time_str = groups[0]
                    return {'hour': int(time_str[:2]), 'minute': int(time_str[2:])}
        
        return {'hour': 9, 'minute': 0}  # Default to 9am
    
    def _parse_date(self, text: str) -> datetime:
        """Extract date from text."""
        
        # Check for relative dates (today, tomorrow, etc.)
        for name, days in self.relative_dates.items():
            if name in text:
                return (self.now + timedelta(days=days)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
        
        # Check for day of week (next Monday, this Friday, etc.)
        for day_name, weekday in self.days_of_week.items():
            if day_name in text:
                # Find next occurrence of this day
                days_ahead = weekday - self.now.weekday()
                if days_ahead < 0:  # Already passed this week
                    days_ahead += 7
                if 'next' in text or days_ahead == 0:
                    days_ahead += 7
                return (self.now + timedelta(days=days_ahead)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
        
        # Check for explicit dates (March 15, 3/15, 2026-03-15, etc.)
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-]?(\d{2,4})?',  # 3/15 or 3-15-2026
            r'(\w+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s*(\d{4})?',  # March 15, 2026
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                if len(groups) >= 2 and groups[0].isdigit():  # 3/15/2026
                    month = int(groups[0])
                    day = int(groups[1])
                    year = int(groups[2]) if groups[2] else self.now.year
                    if len(str(year)) == 2:
                        year = 2000 + year
                    try:
                        return datetime(year, month, day, tzinfo=self.ct)
                    except:
                        pass
                
                elif len(groups) >= 2:  # March 15, 2026
                    month_name = groups[0]
                    day = int(groups[1])
                    year = int(groups[2]) if groups[2] else self.now.year
                    
                    # Convert month name to number
                    months = {
                        'jan': 1, 'january': 1,
                        'feb': 2, 'february': 2,
                        'mar': 3, 'march': 3,
                        'apr': 4, 'april': 4,
                        'may': 5,
                        'jun': 6, 'june': 6,
                        'jul': 7, 'july': 7,
                        'aug': 8, 'august': 8,
                        'sep': 9, 'september': 9,
                        'oct': 10, 'october': 10,
                        'nov': 11, 'november': 11,
                        'dec': 12, 'december': 12,
                    }
                    month = months.get(month_name[:3].lower())
                    if month:
                        try:
                            return datetime(year, month, day, tzinfo=self.ct)
                        except:
                            pass
        
        return None
    
    def _parse_recurrence(self, text: str) -> dict:
        """Parse recurrence pattern from text."""
        
        recurrence = {
            'frequency': 'weekly',
            'interval': 1,
            'days_of_week': [],
        }
        
        # Check for daily
        if 'every day' in text or 'daily' in text:
            recurrence['frequency'] = 'daily'
        
        # Check for weekly
        elif 'every week' in text or 'weekly' in text:
            recurrence['frequency'] = 'weekly'
        
        # Check for monthly
        elif 'every month' in text or 'monthly' in text:
            recurrence['frequency'] = 'monthly'
        
        # Check for specific days (every Monday, every Mon/Wed/Fri)
        day_matches = re.findall(r'\b(mon|tue|wed|thu|fri|sat|sun)\b', text)
        if day_matches:
            recurrence['days_of_week'] = [
                self.days_of_week[day] for day in day_matches
            ]
        
        # Check for interval (every 2 weeks, every 3 days)
        interval_match = re.search(r'every\s+(\d+)\s+(day|week|month)', text)
        if interval_match:
            recurrence['interval'] = int(interval_match.group(1))
            freq_map = {'day': 'daily', 'week': 'weekly', 'month': 'monthly'}
            recurrence['frequency'] = freq_map.get(interval_match.group(2), 'weekly')
        
        return recurrence
    
    def _extract_title(self, text: str) -> str:
        """Extract event title by removing parsed parts."""
        title = text
        
        # Remove time patterns
        title = re.sub(r'\d{1,2}:\d{2}\s*(am|pm)?', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\d{1,2}\s*(am|pm)', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\d{4}', '', title)  # Military time
        
        # Remove date patterns
        title = re.sub(r'\d{1,2}[/-]\d{1,2}[/-]?\d{0,4}', '', title)
        title = re.sub(r'\w+\s+\d{1,2}(st|nd|rd|th)?,?\s*\d{0,4}', '', title, flags=re.IGNORECASE)
        
        # Remove relative dates
        for date_word in list(self.relative_dates.keys()) + list(self.days_of_week.keys()):
            title = re.sub(rf'\b{date_word}\b', '', title, flags=re.IGNORECASE)
        
        # Remove recurrence keywords
        title = re.sub(r'\b(every|each|recurring|repeat|all\s*[-]?day)\b', '', title, flags=re.IGNORECASE)
        
        # Remove location prepositions
        title = re.sub(r'\b(at|in|on)\s+\S+', '', title, flags=re.IGNORECASE)
        
        # Clean up
        title = ' '.join(title.split())
        title = title.strip(' ,.-')
        
        # Capitalize title
        if title:
            title = title.title()
        
        return title or 'New Event'
