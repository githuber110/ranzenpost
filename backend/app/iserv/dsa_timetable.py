from datetime import date, timedelta

from .models import Lesson, TimetableWeek
from .timetable import week_bounds

DATE_FORMAT = "%d.%m.%Y"
QUERY_DATE_FORMAT = "%Y-%m-%d"
WEEKDAY_OFFSET = 1


def query_date(reference):
    return reference.strftime(QUERY_DATE_FORMAT)


def course_filter(course_ids):
    ids = sorted({int(value) for value in course_ids if value is not None})
    if not ids:
        return ""
    return "courseSubject.course:in(%s)" % "|".join(str(value) for value in ids)


def _text(value):
    return str(value or "").strip()


def _lesson_date(monday, weekday):
    return (monday + timedelta(days=int(weekday))).strftime(DATE_FORMAT)


def _teacher_codes(teachers):
    codes = [_text(teacher.get("externalId")) for teacher in teachers or [] if isinstance(teacher, dict)]
    return ", ".join(code for code in codes if code)


def _teacher_names(teachers):
    names = [_text(teacher.get("displayname")) for teacher in teachers or [] if isinstance(teacher, dict)]
    return ", ".join(name for name in names if name)


def entry_to_lesson(entry, monday):
    course_subject = entry.get("courseSubject") or {}
    subject = course_subject.get("subject") or {}
    course = course_subject.get("course") or {}
    slot = entry.get("timeTableSlot") or {}
    room = entry.get("room") or {}
    weekday = int(entry.get("weekday", 0) or 0)
    return Lesson(
        date=_lesson_date(monday, weekday),
        day_of_week=weekday + WEEKDAY_OFFSET,
        period=int(slot.get("number", 0) or 0),
        subject=_text(subject.get("acronym")) or _text(subject.get("name")),
        teacher=_teacher_codes(course_subject.get("teachers")),
        room=_text(room.get("name")),
        class_name=_text(course.get("name")),
        lesson_id=entry.get("id"),
        subject_name=_text(subject.get("name")),
        subject_color=_text(subject.get("hexColor")).lower(),
        teacher_name=_teacher_names(course_subject.get("teachers")),
        start_time=_text(slot.get("startTime")),
        end_time=_text(slot.get("endTime")),
    )


def parse_vacations(items):
    vacations = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        start = _text(item.get("startDate"))
        end = _text(item.get("endDate"))
        if not start or not end:
            continue
        vacations.append({"name": _text(item.get("name")), "start_date": start, "end_date": end})
    return vacations


def parse_current_timetable(payload, reference):
    monday, sunday = week_bounds(reference)
    lessons = []
    for block in (payload or {}).get("students") or []:
        for entry in block.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            lessons.append(entry_to_lesson(entry, monday))
    lessons.sort(key=lambda lesson: (lesson.day_of_week, lesson.period, lesson.subject))
    week = TimetableWeek(
        start_date=monday.strftime(DATE_FORMAT),
        end_date=sunday.strftime(DATE_FORMAT),
        last_updated=None,
        combined=lessons,
        plain=list(lessons),
        changes=[],
    )
    week.lesson_changes = {}
    week.cancelled = []
    week.vacations = parse_vacations((payload or {}).get("vacations"))
    return week


def reference_or_today(reference):
    return reference or date.today()
