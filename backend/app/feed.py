import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from . import cancellations, feed_ics, holidays, marks, messages
from .iserv.absences import berlin_offset
from .subscriptions import (
    COMPONENT_ABSENCES,
    COMPONENT_MARKS,
    COMPONENT_PUBLIC_HOLIDAYS,
    COMPONENT_SCHOOL_HOLIDAYS,
    COMPONENT_TIMETABLE,
    label_carries_child_name,
)

LESSON_MINUTES = 45
WEEKS_BACK = 2
WEEKS_AHEAD = 3
HOLIDAY_DAYS_AHEAD = 365
MARK_DAYS_BACK = 30
STALE_AFTER_SECONDS = 24 * 60 * 60
STATE_RETENTION_SECONDS = 30 * 24 * 60 * 60
STATE_TOUCH_SECONDS = 60 * 60
CHILD_TAG_LENGTH = 16
UID_DOMAIN = "ranzenpost.local"
DEFAULT_CALENDAR_COLOR = "#0e6b70"

CHANGE_PREFIX_KEYS = {
    "cancelled": "timetable.change.cancelled",
    "changed": "timetable.change.changed",
    "added": "timetable.change.added",
}
CHANGE_STATUS_KEYS = {
    "cancelled": "timetable.banner.cancelled",
    "changed": "timetable.banner.changed",
    "added": "timetable.banner.added",
}
FIELD_LABEL_KEYS = {
    "subject": "timetable.field.subject",
    "teacher": "timetable.field.teacher",
    "room": "timetable.field.room",
}
FIELD_VALUE_SOURCES = {
    "subject": ("subject_label", "subject_code"),
    "teacher": ("teacher_label", "teacher_code"),
    "room": ("room", ""),
}
HOLIDAY_FALLBACK_KEYS = {
    holidays.KIND_SCHOOL: "holidays.day.free",
    holidays.KIND_PUBLIC: "holidays.day.public",
}
MARK_SUMMARY_KEY = "calendar.mark.summary"
MARK_SUMMARY_NAMED_KEY = "calendar.mark.summary.named"
MARK_NOTICE_KEY = "calendar.mark.notice"
OWN_DROP_NOTICE_KEY = "calendar.cancellation.notice"
MARK_FALLBACK_PREFIX = "!"
ABSENCE_STATUS_KEYS = {
    "accepted": "absence.status.accepted",
    "open": "absence.status.open",
    "rejected": "absence.status.rejected",
}
ABSENCE_FEED_STATUSES = ("accepted", "")
ABSENCE_KIND_SICK = "sick"

_STATE_LOCK = threading.Lock()


@dataclass(frozen=True)
class FeedEvent:
    uid: str
    summary: str
    description: str
    location: str
    start: object
    end: object
    all_day: bool
    transparent: bool
    color: str = ""
    category: str = ""


def child_tag(child_id):
    return hashlib.sha256(str(child_id or "").encode("utf-8")).hexdigest()[:CHILD_TAG_LENGTH]


def lesson_window(today):
    monday = today - timedelta(days=today.weekday())
    start = monday - timedelta(days=7 * WEEKS_BACK)
    end = monday + timedelta(days=7 * (WEEKS_AHEAD + 1) - 1)
    return start, end


def berlin_moment(epoch):
    naive = datetime.fromtimestamp(epoch, timezone.utc).replace(tzinfo=None)
    offset = 2 if berlin_offset(naive + timedelta(hours=2)) == 2 else 1
    return naive + timedelta(hours=offset)


def _text(language, key, variables=None):
    return messages.text_in(language, key, variables)


def _translated(language, key, variables=None):
    if not key:
        return ""
    rendered = messages.text_in(language, key, variables)
    return "" if rendered == key else rendered


def _optional_text(language, key):
    return _translated(language, key)


def _german_date(value):
    return value.strftime("%d.%m.%Y")


def _detail_line(language, label_key, value):
    return _text(language, "calendar.detail.line", {"label": _text(language, label_key), "value": value})


def _lesson_time_range(start_time):
    hour, minute = (int(part) for part in str(start_time).split(":"))
    start = timedelta(hours=hour, minutes=minute)
    end = start + timedelta(minutes=LESSON_MINUTES)
    return _clock(start), _clock(end)


def _clock(span):
    total = int(span.total_seconds() // 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _lesson_start(day, start_time):
    hour, minute = (int(part) for part in str(start_time).split(":"))
    return datetime(day.year, day.month, day.day, hour, minute)


def _field_value(lesson, name):
    primary, secondary = FIELD_VALUE_SOURCES[name]
    return lesson.get(primary) or (lesson.get(secondary) if secondary else "") or ""


def _subject_of(language, lesson):
    return (
        lesson.get("subject_label")
        or lesson.get("subject_code")
        or _text(language, "timetable.lesson.fallback")
    )


def lesson_summary(language, lesson):
    subject = _subject_of(language, lesson)
    teacher = lesson.get("teacher_label") or lesson.get("teacher_code") or ""
    key = "calendar.event.summary" if teacher else "calendar.event.summary.noTeacher"
    title = _text(
        language,
        key,
        {"period": lesson.get("period", ""), "subject": subject, "teacher": teacher},
    )
    prefix_key = CHANGE_PREFIX_KEYS.get(lesson.get("change_kind") or "")
    if not prefix_key:
        return title
    return _text(
        language,
        "calendar.event.summary.prefixed",
        {"prefix": _text(language, prefix_key), "title": title},
    )


def lesson_description(language, lesson, day, parallel_count):
    none_text = _text(language, "common.none")
    rows = [_detail_line(language, "calendar.detail.date", _german_date(day))]
    start_time = lesson.get("start_time")
    if start_time:
        opening, closing = _lesson_time_range(start_time)
        rows.append(
            _detail_line(
                language,
                "calendar.detail.time",
                _text(language, "calendar.detail.timeRange", {"start": opening, "end": closing}),
            )
        )
    rows.append(
        _detail_line(
            language,
            "timetable.fact.period",
            _text(language, "timetable.fact.periodValue", {"period": lesson.get("period", "")}),
        )
    )
    rows.append(_detail_line(language, "timetable.field.subject", _subject_of(language, lesson)))
    rows.append(
        _detail_line(language, "timetable.field.teacher", _field_value(lesson, "teacher") or none_text)
    )
    rows.append(_detail_line(language, "timetable.field.room", _field_value(lesson, "room") or none_text))
    if lesson.get("is_class_teacher"):
        rows.append(
            _detail_line(language, "timetable.fact.role", _text(language, "timetable.fact.classTeacher"))
        )
    status_key = CHANGE_STATUS_KEYS.get(lesson.get("change_kind") or "")
    if status_key:
        rows.append(_detail_line(language, "calendar.detail.status", _text(language, status_key)))
    rows.extend(_change_rows(language, lesson, none_text))
    if parallel_count > 1:
        rows.append(
            _text(language, "calendar.detail.parallel", {"count": parallel_count})
        )
    return "\n".join(rows)


def _change_rows(language, lesson, none_text):
    fields = [name for name in (lesson.get("changed_fields") or []) if name in FIELD_LABEL_KEYS]
    if not fields:
        return []
    previous = lesson.get("previous") or {}
    rows = [_text(language, "timetable.changes.title")]
    for name in fields:
        rows.append(
            _text(
                language,
                "calendar.detail.changeLine",
                {
                    "field": _text(language, FIELD_LABEL_KEYS[name]),
                    "before": previous.get(name) or none_text,
                    "after": _field_value(lesson, name) or none_text,
                },
            )
        )
    return rows


def _lesson_identity(lesson):
    return (
        str(lesson.get("date") or ""),
        int(lesson.get("period") or 0),
        str(lesson.get("subject_code") or ""),
        str(lesson.get("teacher_code") or ""),
        str(lesson.get("room") or ""),
        str(lesson.get("change_kind") or ""),
    )


def lessons_in_window(snapshot, child_id, start, end):
    child = (snapshot.get("children") or {}).get(child_id) or {}
    weeks = child.get("weeks") or {}
    collected = {}
    for week in weeks.values():
        if not isinstance(week, dict):
            continue
        for lesson in week.get("lessons") or []:
            day = holidays.parse_day(lesson.get("date"))
            if day is None or day < start or day > end:
                continue
            collected[_lesson_identity(lesson)] = (day, lesson)
    return collected


def _grouped_lessons(collected):
    grouped = {}
    for identity, (day, lesson) in collected.items():
        grouped.setdefault((day, int(lesson.get("period") or 0)), []).append((identity, lesson))
    for slot in grouped.values():
        slot.sort(key=lambda item: item[0][2:])
    return grouped


def subject_color(config, lesson):
    subjects = config.get("subjects") or {}
    entry = subjects.get(lesson.get("subject_code") or "")
    configured = entry.get("color") if isinstance(entry, dict) else ""
    return configured or lesson.get("color") or ""


def subject_category(language, lesson):
    return _subject_of(language, lesson)


def dropped_slots(entries, child_id):
    slots = set()
    for entry in entries or []:
        if child_id and entry.get("child_id") != child_id:
            continue
        day = holidays.parse_day(entry.get("date"))
        if day is None:
            continue
        slots.add((day, int(entry.get("period") or 0)))
    return slots


def timetable_events(language, tag, collected, day_map, blocked, config=None, dropped=()):
    settings = config or {}
    off = set(dropped)
    events = []
    unscheduled = {}
    for (day, period), slot in sorted(_grouped_lessons(collected).items()):
        if blocked or (day_map.get(day.isoformat()) or {}).get("overrides_lessons"):
            continue
        own_drop = (day, period) in off
        for index, (_, lesson) in enumerate(slot):
            uid = f"{tag}-{day.strftime('%Y%m%d')}-p{period}-{index}@{UID_DOMAIN}"
            if not lesson.get("start_time"):
                unscheduled.setdefault(day, []).append(lesson)
                continue
            shown = dict(lesson, change_kind="cancelled") if own_drop else lesson
            start = _lesson_start(day, lesson["start_time"])
            description = lesson_description(language, shown, day, len(slot))
            if own_drop:
                notice = _translated(language, OWN_DROP_NOTICE_KEY)
                if notice:
                    description = "\n".join([description, notice])
            events.append(
                FeedEvent(
                    uid=uid,
                    summary=lesson_summary(language, shown),
                    description=description,
                    location=lesson.get("room") or "",
                    start=start,
                    end=start + timedelta(minutes=LESSON_MINUTES),
                    all_day=False,
                    transparent=shown.get("change_kind") == "cancelled",
                    color=subject_color(settings, lesson),
                    category=subject_category(language, lesson),
                )
            )
    events.extend(_unscheduled_events(language, tag, unscheduled))
    return events


def _unscheduled_events(language, tag, unscheduled):
    events = []
    for day, lessons in sorted(unscheduled.items()):
        rows = [_text(language, "calendar.notice.unscheduled.description")]
        rows.extend(lesson_summary(language, lesson) for lesson in lessons)
        events.append(
            FeedEvent(
                uid=f"{tag}-{day.strftime('%Y%m%d')}-unscheduled@{UID_DOMAIN}",
                summary=_text(language, "calendar.notice.unscheduled.summary"),
                description="\n".join(rows),
                location="",
                start=day,
                end=day + timedelta(days=1),
                all_day=True,
                transparent=True,
            )
        )
    return events


def mark_window(today):
    return today - timedelta(days=MARK_DAYS_BACK), today + timedelta(days=HOLIDAY_DAYS_AHEAD)


def _mark_subject(language, config, entry):
    code = str(entry.get("subject_code") or "")
    subjects = config.get("subjects") or {}
    stored = subjects.get(code)
    label = stored.get("label") if isinstance(stored, dict) else ""
    return _subject_of(language, {"subject_code": code, "subject_label": label or ""})


def _mark_color(config, entry):
    subjects = config.get("subjects") or {}
    stored = subjects.get(str(entry.get("subject_code") or ""))
    return stored.get("color") or "" if isinstance(stored, dict) else ""


def mark_summary(language, config, entry):
    subject = _mark_subject(language, config, entry)
    period = int(entry.get("period") or 0)
    name = str(entry.get("name") or "")
    variables = {"subject": subject, "period": period, "name": name}
    rendered = _translated(
        language, MARK_SUMMARY_NAMED_KEY if name else MARK_SUMMARY_KEY, variables
    )
    if rendered:
        return rendered
    plain = _text(
        language, "calendar.event.summary.noTeacher", {"period": period, "subject": subject}
    )
    return _text(
        language,
        "calendar.event.summary.prefixed",
        {"prefix": name or MARK_FALLBACK_PREFIX, "title": plain},
    )


def mark_description(language, config, entry, day, start_time, lesson):
    none_text = _text(language, "common.none")
    rows = [_detail_line(language, "calendar.detail.date", _german_date(day))]
    if start_time:
        opening, closing = _lesson_time_range(start_time)
        rows.append(
            _detail_line(
                language,
                "calendar.detail.time",
                _text(language, "calendar.detail.timeRange", {"start": opening, "end": closing}),
            )
        )
    rows.append(
        _detail_line(
            language,
            "timetable.fact.period",
            _text(
                language,
                "timetable.fact.periodValue",
                {"period": int(entry.get("period") or 0)},
            ),
        )
    )
    rows.append(
        _detail_line(language, "timetable.field.subject", _mark_subject(language, config, entry))
    )
    if lesson is not None:
        rows.append(
            _detail_line(
                language, "timetable.field.teacher", _field_value(lesson, "teacher") or none_text
            )
        )
        rows.append(
            _detail_line(language, "timetable.field.room", _field_value(lesson, "room") or none_text)
        )
        status_key = CHANGE_STATUS_KEYS.get(lesson.get("change_kind") or "")
        if status_key:
            rows.append(_detail_line(language, "calendar.detail.status", _text(language, status_key)))
    notice = _translated(language, MARK_NOTICE_KEY)
    if notice:
        rows.append(notice)
    return "\n".join(rows)


def mark_events(language, config, snapshot, entries, child_id, today, now_epoch):
    start, end = mark_window(today)
    times = config.get("period_times") or {}
    events = []
    for entry in entries:
        if entry.get("child_id") != child_id:
            continue
        if not marks.in_range(entry, start, end):
            continue
        day = holidays.parse_day(entry.get("date"))
        start_time = str(times.get(str(int(entry.get("period") or 0))) or "")
        lesson = marks.resolved_lesson(snapshot, entry, now_epoch)
        summary = mark_summary(language, config, entry)
        description = mark_description(language, config, entry, day, start_time, lesson)
        uid = f"mark-{entry.get('id', '')}@{UID_DOMAIN}"
        location = (lesson or {}).get("room") or ""
        if start_time:
            opening = _lesson_start(day, start_time)
            begin = opening
            finish = opening + timedelta(minutes=LESSON_MINUTES)
            all_day = False
        else:
            begin = day
            finish = day + timedelta(days=1)
            all_day = True
        events.append(
            FeedEvent(
                uid=uid,
                summary=summary,
                description=description,
                location=location,
                start=begin,
                end=finish,
                all_day=all_day,
                transparent=False,
                color=_mark_color(config, entry),
                category=_mark_subject(language, config, entry),
            )
        )
    return events


def stored_absences(snapshot, child_id):
    child = ((snapshot or {}).get("children") or {}).get(child_id) or {}
    entries = child.get("absences")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def absence_is_settled(entry):
    status = str(entry.get("status") or "")
    if status == "accepted":
        return True
    return status == "" and str(entry.get("kind") or "") == ABSENCE_KIND_SICK


def _safe_text(value, config):
    text = " ".join(str(value or "").split())
    if not text or label_carries_child_name(text, config):
        return ""
    return text


def absence_summary(language, entry):
    kind = _optional_text(language, entry.get("label_key")) or _text(
        language, "absence.entry.fallback"
    )
    target = _optional_text(language, entry.get("target_key"))
    if not target:
        return kind
    return _text(language, "calendar.event.summary.prefixed", {"prefix": kind, "title": target})


def _absence_period(entry, name):
    value = entry.get(name)
    if isinstance(value, bool) or value in (None, ""):
        return 0
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def absence_description(language, config, entry, first, last):
    rows = [
        _detail_line(
            language,
            "absence.fact.range",
            _german_date(first)
            if first == last
            else _text(
                language,
                "calendar.detail.dateRange",
                {"start": _german_date(first), "end": _german_date(last)},
            ),
        )
    ]
    opening = _absence_period(entry, "from_period")
    closing = _absence_period(entry, "till_period")
    if opening and closing:
        rows.append(
            _detail_line(
                language,
                "absence.fact.hours",
                _text(language, "absence.fact.hoursRange", {"from": opening, "till": closing}),
            )
        )
    status_key = ABSENCE_STATUS_KEYS.get(str(entry.get("status") or ""))
    if status_key:
        rows.append(_detail_line(language, "absence.fact.status", _text(language, status_key)))
    subject = _safe_text(entry.get("subject"), config)
    if subject:
        rows.append(_detail_line(language, "absence.fact.subject", subject))
    comment = _safe_text(entry.get("comment"), config)
    if comment:
        rows.append(_detail_line(language, "absence.fact.comment", comment))
    return "\n".join(rows)


def absence_events(language, tag, config, snapshot, child_id, today):
    start, end = mark_window(today)
    times = config.get("period_times") or {}
    events = []
    for entry in stored_absences(snapshot, child_id):
        if not absence_is_settled(entry):
            continue
        first = holidays.parse_day(entry.get("from_date"))
        last = holidays.parse_day(entry.get("till_date")) or first
        if first is None:
            continue
        if last < first:
            last = first
        if last < start or first > end:
            continue
        opening = _absence_period(entry, "from_period")
        closing = _absence_period(entry, "till_period")
        begin_time = str(times.get(str(opening)) or "") if opening else ""
        end_time = str(times.get(str(closing)) or "") if closing else ""
        uid = f"{tag}-absence-{entry.get('kind', '')}-{entry.get('id', '')}@{UID_DOMAIN}"
        summary = absence_summary(language, entry)
        description = absence_description(language, config, entry, first, last)
        if first == last and begin_time and end_time:
            begin = _lesson_start(first, begin_time)
            finish = _lesson_start(first, end_time) + timedelta(minutes=LESSON_MINUTES)
            if finish <= begin:
                finish = begin + timedelta(minutes=LESSON_MINUTES)
            all_day = False
        else:
            begin = first
            finish = last + timedelta(days=1)
            all_day = True
        events.append(
            FeedEvent(
                uid=uid,
                summary=summary,
                description=description,
                location="",
                start=begin,
                end=finish,
                all_day=all_day,
                transparent=all_day,
            )
        )
    return events


def free_spans(day_map, start, end, kind):
    spans = []
    current = None
    day = start
    while day <= end:
        info = day_map.get(day.isoformat()) or {}
        matches = (
            bool(info.get("free"))
            and bool(info.get("overrides_lessons"))
            and info.get("kind") == kind
        )
        if not matches:
            if current:
                spans.append(current)
                current = None
            day += timedelta(days=1)
            continue
        marker = info.get("period_id") or ""
        if current and current["marker"] == marker and current["end"] + timedelta(days=1) == day:
            current["end"] = day
        else:
            if current:
                spans.append(current)
            current = {
                "marker": marker,
                "start": day,
                "end": day,
                "name": info.get("name") or "",
                "name_key": info.get("name_key") or "",
            }
        day += timedelta(days=1)
    if current:
        spans.append(current)
    return spans


def _span_title(language, span, kind):
    return (
        _optional_text(language, span["name_key"])
        or span["name"]
        or _text(language, HOLIDAY_FALLBACK_KEYS[kind])
    )


def holiday_events(language, tag, day_map, start, end, kind, split_days):
    events = []
    for span in free_spans(day_map, start, end, kind):
        title = _span_title(language, span, kind)
        pieces = (
            [(day, day) for day in _days_between(span["start"], span["end"])]
            if split_days
            else [(span["start"], span["end"])]
        )
        for first, last in pieces:
            events.append(
                FeedEvent(
                    uid=f"{tag}-holiday-{kind}-{first.isoformat()}-{last.isoformat()}@{UID_DOMAIN}",
                    summary=title,
                    description=_detail_line(
                        language,
                        "calendar.detail.date",
                        _text(
                            language,
                            "calendar.detail.dateRange",
                            {"start": _german_date(first), "end": _german_date(last)},
                        )
                        if last != first
                        else _german_date(first),
                    ),
                    location="",
                    start=first,
                    end=last + timedelta(days=1),
                    all_day=True,
                    transparent=True,
                )
            )
    return events


def _days_between(start, end):
    days = []
    day = start
    while day <= end:
        days.append(day)
        day += timedelta(days=1)
    return days


def _notice(language, tag, today, marker, summary_key, description_key, variables=None):
    return FeedEvent(
        uid=f"{tag}-notice-{marker}@{UID_DOMAIN}",
        summary=_text(language, summary_key),
        description=_text(language, description_key, variables),
        location="",
        start=today,
        end=today + timedelta(days=1),
        all_day=True,
        transparent=True,
    )


def notice_events(language, tag, today, blocked, window, last_success, now_epoch):
    events = []
    if blocked:
        events.append(
            _notice(
                language,
                tag,
                today,
                "holidays",
                "calendar.notice.holidays.summary",
                "calendar.notice.holidays.description",
                {"start": _german_date(window[0]), "end": _german_date(window[1])},
            )
        )
    if not last_success:
        events.append(
            _notice(
                language,
                tag,
                today,
                "nodata",
                "calendar.notice.noData.summary",
                "calendar.notice.noData.description",
            )
        )
    elif now_epoch - last_success > STALE_AFTER_SECONDS:
        events.append(
            _notice(
                language,
                tag,
                today,
                "stale",
                "calendar.notice.stale.summary",
                "calendar.notice.stale.description",
                {"time": berlin_moment(last_success).strftime("%d.%m.%Y %H:%M")},
            )
        )
    return events


def calendar_name(language, subscription):
    return subscription.get("label") or _text(language, "calendar.name.fallback")


def build_events(
    subscription, config, snapshot, day_map, blocked, today, now_epoch, mark_entries=(),
    cancellation_entries=(),
):
    language = messages.normalize_language(config.get("language"))
    child_id = subscription.get("child_id", "")
    tag = child_tag(child_id)
    components = subscription.get("components") or []
    window = lesson_window(today)
    events = []
    if COMPONENT_MARKS in components:
        events.extend(
            mark_events(language, config, snapshot, mark_entries, child_id, today, now_epoch)
        )
    if COMPONENT_ABSENCES in components:
        events.extend(absence_events(language, tag, config, snapshot, child_id, today))
    if COMPONENT_TIMETABLE in components:
        collected = lessons_in_window(snapshot, child_id, window[0], window[1])
        events.extend(
            timetable_events(
                language,
                tag,
                collected,
                day_map,
                blocked,
                config,
                dropped_slots(cancellation_entries, child_id),
            )
        )
        events.extend(
            notice_events(
                language,
                tag,
                today,
                blocked,
                window,
                _last_success(snapshot, child_id),
                now_epoch,
            )
        )
    holiday_end = today + timedelta(days=HOLIDAY_DAYS_AHEAD)
    if COMPONENT_SCHOOL_HOLIDAYS in components:
        events.extend(
            holiday_events(language, tag, day_map, window[0], holiday_end, holidays.KIND_SCHOOL, False)
        )
    if COMPONENT_PUBLIC_HOLIDAYS in components:
        events.extend(
            holiday_events(language, tag, day_map, window[0], holiday_end, holidays.KIND_PUBLIC, True)
        )
    events.sort(key=lambda event: (_sort_day(event.start).isoformat(), event.uid))
    return events


def _sort_day(value):
    return value.date() if isinstance(value, datetime) else value


def _last_success(snapshot, child_id):
    child = (snapshot.get("children") or {}).get(child_id) or {}
    value = child.get("last_success")
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def content_hash(event):
    blob = "|".join(
        [
            event.uid,
            event.summary,
            event.description,
            event.location,
            _stamp(event.start),
            _stamp(event.end),
            "1" if event.all_day else "0",
            "1" if event.transparent else "0",
            event.color,
            event.category,
        ]
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _stamp(value):
    return value.isoformat()


def calendar_color(subscription):
    chosen = subscription.get("color") or ""
    if feed_ics.parse_hex_color(chosen) is None:
        return DEFAULT_CALENDAR_COLOR
    return chosen


def render(store, name, events, now, color=DEFAULT_CALENDAR_COLOR):
    stamp = feed_ics.format_utc(now)
    epoch = int(now.replace(tzinfo=timezone.utc).timestamp())
    blocks = []
    with _STATE_LOCK:
        state = store.load_calendar_state()
        changed = False
        for event in events:
            digest = content_hash(event)
            entry = state.get(event.uid)
            if not isinstance(entry, dict) or entry.get("hash") != digest or not entry.get("last_modified"):
                sequence = int(entry.get("seq", -1)) + 1 if isinstance(entry, dict) else 0
                entry = {"hash": digest, "seq": sequence, "last_modified": stamp, "seen_at": epoch}
                state[event.uid] = entry
                changed = True
            elif epoch - int(entry.get("seen_at") or 0) > STATE_TOUCH_SECONDS:
                entry["seen_at"] = epoch
                changed = True
            blocks.append(feed_ics.render_event(event, int(entry["seq"]), entry["last_modified"]))
        kept = {
            uid: entry
            for uid, entry in state.items()
            if isinstance(entry, dict) and epoch - int(entry.get("seen_at") or 0) <= STATE_RETENTION_SECONDS
        }
        if changed or len(kept) != len(state):
            store.save_calendar_state(kept)
    return feed_ics.render_calendar(name, blocks, color)


def build_feed(subscription, store, holiday_calendar, now=None):
    moment = now or datetime.now(timezone.utc).replace(tzinfo=None)
    epoch = int(moment.replace(tzinfo=timezone.utc).timestamp())
    today = holidays.berlin_today(moment)
    config = store.load_config()
    language = messages.normalize_language(config.get("language"))
    window = lesson_window(today)
    payload = holiday_calendar.range_info(
        window[0], today + timedelta(days=HOLIDAY_DAYS_AHEAD), config
    )
    blocked = payload.get("status") != holidays.STATUS_OK
    day_map = payload.get("days") or {}
    snapshot = store.load_calendar_snapshot()
    events = build_events(
        subscription,
        config,
        snapshot,
        day_map,
        blocked,
        today,
        epoch,
        marks.entries_of(store.load_marks()),
        cancellations.entries_of(store.load_cancellations()),
    )
    return render(
        store,
        calendar_name(language, subscription),
        events,
        moment,
        calendar_color(subscription),
    )
