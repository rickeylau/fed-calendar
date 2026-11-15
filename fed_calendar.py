#!/usr/bin/env python3
"""Generate a subscribed calendar from the Fed Board monthly calendars."""
import calendar
import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

ET = ZoneInfo('America/New_York')
BASE = 'https://www.federalreserve.gov/newsevents/'
OUTPUT = Path('fed.ics')
# Change to False if these already appear in Economic Calendar.
INCLUDE_FOMC = True
INCLUDE_BEIGE_BOOK = True
MONTHS_BACK = 1
MONTHS_AHEAD = 2
TIME_RE = re.compile(r'^(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?$', re.I)
DAY_RE = re.compile(r'^\d{1,2}(?:\s*,\s*\d{1,2})*$')
TITLE_RE = re.compile(r'^(?:Speech|Discussion|Testimony|Remarks|Panel|Conversation|Interview|Welcoming Remarks|Opening Remarks|Closing Remarks)\b', re.I)
HEADINGS = {'speeches', 'testimony', 'fomc meetings', 'beige book', 'statistical releases', 'other', 'board meetings'}


def month_shift(year, month, offset):
    n = year * 12 + month - 1 + offset
    return n // 12, n % 12 + 1


def clean(s):
    return ' '.join(s.split())


def parse_month(html, year, month, url):
    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    # The monthly text page uses section headings and rows of time,
    # event title/description and release day(s).
    lines = [clean(x) for x in soup.stripped_strings if clean(x)]
    month_label = f'{calendar.month_name[month]} {year}'
    try:
        start = next(i for i, x in enumerate(lines) if x.lower() == month_label.lower())
    except StopIteration:
        raise ValueError(f'Month label missing: {month_label}')
    section = None
    blocks = []
    current = None
    sections_seen = set()
    for line in lines[start + 1:]:
        key = line.lower()
        if key.startswith('last update:') or key == 'back to top':
            break
        if key in HEADINGS and not (current and key == 'beige book' and section == 'beige book'):
            if current:
                blocks.append(current)
            section = key
            sections_seen.add(key)
            current = None
        elif (match := TIME_RE.fullmatch(line)):
            if current:
                blocks.append(current)
            h, m, ap = match.groups()
            current = (section, time(int(h) % 12 + (12 if ap.lower() == 'p' else 0), int(m)), [])
        elif current:
            current[2].append(line)
    if current:
        blocks.append(current)
    if not sections_seen:
        raise ValueError(f'No calendar sections: {url}')
    events = []
    for section, clock, body in blocks:
        if section not in {'speeches', 'testimony', 'fomc meetings', 'beige book'}:
            continue
        if section == 'fomc meetings' and not INCLUDE_FOMC:
            continue
        if section == 'beige book' and not INCLUDE_BEIGE_BOOK:
            continue
        if not body:
            continue
        title = body[0]
        if section in {'speeches', 'testimony'}:
            if not TITLE_RE.match(title):
                # Keep unfamiliar official event labels instead of guessing.
                print(f'NOTICE: new event label in {section}: {title}')
            summary = 'Fed ' + title
        elif section == 'fomc meetings':
            if title.lower() == 'fomc meeting':
                summary = 'FOMC Rate Decision (Meeting)'
            else:
                summary = title
        else:
            summary = title
        # A section ends at the next time or heading; the release day is
        # a standalone numeric field in the official monthly page.
        day_index = next((i for i in range(len(body)-1, 0, -1) if DAY_RE.fullmatch(body[i])), None)
        if day_index is None:
            raise ValueError(f'Missing release date for {title}: {url}')
        detail = '\n'.join(x for x in body[1:day_index] if x not in {'Watch Live', 'Time:', 'Release Date(s):'})
        for day in map(int, re.findall(r'\d+', body[day_index])):
            when = datetime.combine(date(year, month, day), clock, ET)
            events.append((when, summary, detail, url))
    return events


def build():
    today = datetime.now(ET).date()
    all_events = []
    with requests.Session() as session:
        session.headers['User-Agent'] = 'FedCalendar/1.0 (public calendar subscription)'
        for offset in range(-MONTHS_BACK, MONTHS_AHEAD + 1):
            y, m = month_shift(today.year, today.month, offset)
            url = BASE + f'{y}-{calendar.month_name[m].lower()}.htm'
            r = session.get(url, timeout=30)
            if r.status_code == 404 and offset > 0:
                print(f'Not published yet: {url}')
                continue
            r.raise_for_status()
            events = parse_month(r.text, y, m, url)
            print(f'{y}-{m:02}: {len(events)} selected events')
            all_events.extend(events)
    if not all_events:
        raise RuntimeError('No events found; refusing to replace existing calendar.')
    cal = Calendar()
    cal.add('prodid', '-//Fed Calendar//EN')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Fed Calendar')
    cal.add('x-wr-timezone', 'America/New_York')
    cal.add('x-wr-caldesc', 'Federal Reserve Board speeches and monetary policy events')
    seen = set()
    now = datetime.now(timezone.utc)
    for when, summary, detail, url in sorted(all_events):
        # Include the topic to distinguish multiple speeches by one speaker.
        key = f'{when.date()}|{summary}|{detail}'
        uid = hashlib.sha256(key.encode()).hexdigest() + '@fed-calendar'
        if uid in seen:
            continue
        seen.add(uid)
        event = Event()
        event.add('uid', uid)
        event.add('dtstamp', now)
        event.add('dtstart', when.astimezone(timezone.utc))
        event.add('dtend', (when + timedelta(minutes=15)).astimezone(timezone.utc))
        event.add('summary', summary)
        event.add('description', f'{detail}\n\nSource: {url}\nEnd time is a 15-minute display placeholder, not the official duration.')
        event.add('url', url)
        event.add('transp', 'TRANSPARENT')
        cal.add_component(event)
    data = cal.to_ical()
    # Do not create an hourly commit merely because DTSTAMP changed.
    def without_stamp(raw):
        return re.sub(rb'(?m)^DTSTAMP:[^\r\n]*\r?\n', b'', raw)
    if OUTPUT.exists() and without_stamp(OUTPUT.read_bytes()) == without_stamp(data):
        print('No event changes.')
        return
    temp = OUTPUT.with_suffix('.tmp')
    temp.write_bytes(data)
    temp.replace(OUTPUT)
    print(f'Wrote {len(seen)} events to {OUTPUT}')


if __name__ == '__main__':
    build()
