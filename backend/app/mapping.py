import re

LESSON_MINUTES = 45
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

DEFAULT_COLORS = [
    "#84142a", "#f7703e", "#ec932f", "#7b791d", "#404f0e",
    "#2dae4b", "#208068", "#135859", "#31aed2", "#2486ed",
    "#372daa", "#834ac9", "#a639a3", "#7a1362",
]

COLOR_SOURCE = "color_source"
USER_COLOR = "user"
AUTO_COLOR = "auto"

NAME_SOURCE = "label_source"
AUTO_NAME = "auto"

PALETTE_MIGRATION = {
    "#0e6b70": "#135859",
    "#7a4b9c": "#834ac9",
    "#b4602a": "#f7703e",
    "#2f6b3a": "#2dae4b",
    "#9c3b5e": "#84142a",
    "#3a5a9c": "#2486ed",
    "#8a6a1f": "#7b791d",
    "#2a6f63": "#208068",
    "#5b4a9c": "#372daa",
    "#1f6b8a": "#31aed2",
    "#2563eb": "#135859",
    "#7c3aed": "#834ac9",
    "#16a34a": "#2dae4b",
    "#0891b2": "#31aed2",
    "#db2777": "#84142a",
    "#ea580c": "#f7703e",
    "#ca8a04": "#7b791d",
    "#0d9488": "#208068",
    "#9333ea": "#372daa",
}


def default_color(index):
    return DEFAULT_COLORS[index % len(DEFAULT_COLORS)]


def _color_of(entry):
    return str(entry.get("color", "") or "").strip().lower()


def has_user_color(entry):
    return isinstance(entry, dict) and entry.get(COLOR_SOURCE) == USER_COLOR and bool(_color_of(entry))


def migrate_subject_colors(config):
    subjects = config.get("subjects") or {}
    migrated = {}
    changed = False
    for code, entry in subjects.items():
        if not isinstance(entry, dict) or COLOR_SOURCE in entry:
            migrated[code] = entry
            continue
        color = _color_of(entry)
        if color:
            migrated[code] = dict(entry, color=PALETTE_MIGRATION.get(color, color), **{COLOR_SOURCE: USER_COLOR})
        else:
            migrated[code] = dict(entry, color="", **{COLOR_SOURCE: AUTO_COLOR})
        changed = True
    if not changed:
        return config
    result = dict(config)
    result["subjects"] = migrated
    return result


def _assign_auto_colors(subjects):
    taken = {_color_of(entry) for entry in subjects.values() if has_user_color(entry)}
    assigned = 0
    result = {}
    for code in sorted(subjects):
        entry = subjects[code]
        if has_user_color(entry):
            result[code] = entry
            continue
        color = _color_of(entry)
        if not color or color in taken:
            color = _free_color(taken, assigned)
        if entry.get("color") != color or entry.get(COLOR_SOURCE) != AUTO_COLOR:
            entry = dict(entry, color=color, **{COLOR_SOURCE: AUTO_COLOR})
        assigned += 1
        taken.add(color)
        result[code] = entry
    return {code: result[code] for code in subjects}


def _free_color(taken, assigned):
    for color in DEFAULT_COLORS:
        if color not in taken:
            return color
    return DEFAULT_COLORS[assigned % len(DEFAULT_COLORS)]


def distinct(values):
    return list(dict.fromkeys(v for v in values if v))


NATIVE_COLOR = re.compile(r"^#[0-9a-f]{6}$")


def _native_color(value):
    text = str(value or "").strip().lower()
    return text if NATIVE_COLOR.match(text) else ""


def _native_subjects(lessons):
    found = {}
    for lesson in lessons:
        if not lesson.subject or lesson.subject in found:
            continue
        name = str(getattr(lesson, "subject_name", "") or "").strip()
        color = _native_color(getattr(lesson, "subject_color", ""))
        if name or color:
            found[lesson.subject] = (name, color)
    return found


def _native_teachers(lessons):
    found = {}
    for lesson in lessons:
        if not lesson.teacher or lesson.teacher in found:
            continue
        name = str(getattr(lesson, "teacher_name", "") or "").strip()
        if name:
            found[lesson.teacher] = (name, str(getattr(lesson, "teacher_surname", "") or "").strip())
    return found


def _unnamed(entry, code):
    return not entry.get("label") or entry.get("label") == code


def _name_parts(value):
    return sorted(part for part in str(value or "").replace(",", " ").split() if part)


def _same_name_reordered(stored, name):
    parts = _name_parts(stored)
    return bool(parts) and parts == _name_parts(name)


def merge_discovered_codes(config, lessons):
    config = migrate_subject_colors(config)
    subjects = dict(config.get("subjects", {}))
    teachers = dict(config.get("teachers", {}))
    native_subjects = _native_subjects(lessons)
    native_teachers = _native_teachers(lessons)
    for code in distinct(lesson.subject for lesson in lessons):
        name, color = native_subjects.get(code, ("", ""))
        if code not in subjects:
            subjects[code] = {"label": name or code, "color": color, COLOR_SOURCE: AUTO_COLOR}
            continue
        entry = dict(subjects[code])
        if name and _unnamed(entry, code):
            entry["label"] = name
        if color and not has_user_color(entry) and not _color_of(entry):
            entry["color"] = color
            entry[COLOR_SOURCE] = AUTO_COLOR
        subjects[code] = entry
    subjects = _assign_auto_colors(subjects)
    for code in distinct(lesson.teacher for lesson in lessons):
        name, surname = native_teachers.get(code, ("", ""))
        if code not in teachers:
            teachers[code] = {
                "label": name or code,
                "surname": surname,
                NAME_SOURCE: AUTO_NAME if name else "",
                "is_class_teacher": False,
            }
            continue
        entry = dict(teachers[code])
        if name and (_unnamed(entry, code) or _same_name_reordered(entry.get("label"), name)):
            entry["label"] = name
            entry[NAME_SOURCE] = AUTO_NAME
        if surname:
            entry["surname"] = surname
        teachers[code] = entry
    merged = dict(config)
    merged["subjects"] = subjects
    merged["teachers"] = teachers
    return merged


def configured_time(config, period):
    times = (config or {}).get("period_times") or {}
    value = str(times.get(str(period), "") or "").strip()
    return value if CLOCK.match(value) else ""


def shift_time(value, minutes):
    match = CLOCK.match(str(value or "").strip())
    if not match:
        return ""
    total = int(match.group(1)) * 60 + int(match.group(2)) + minutes
    if total < 0 or total >= 24 * 60:
        return ""
    return "%02d:%02d" % divmod(total, 60)


def lesson_times(lesson, config):
    chosen = configured_time(config, lesson.period)
    native_start = str(getattr(lesson, "start_time", "") or "").strip()
    native_end = str(getattr(lesson, "end_time", "") or "").strip()
    if not chosen:
        return native_start, native_end
    if chosen == native_start:
        return chosen, native_end
    return chosen, shift_time(chosen, LESSON_MINUTES)


def subject_label(config, code):
    if not code:
        return ""
    return config.get("subjects", {}).get(code, {}).get("label") or code


def teacher_label(config, code):
    if not code:
        return ""
    return config.get("teachers", {}).get(code, {}).get("label") or code


def _previous_display(config, previous):
    previous = previous or {}
    return {
        "subject": subject_label(config, previous.get("subject", "")),
        "teacher": teacher_label(config, previous.get("teacher", "")),
        "room": previous.get("room", "") or "",
    }


def to_display(lesson, config, change=None):
    subject = config.get("subjects", {}).get(lesson.subject, {})
    teacher = config.get("teachers", {}).get(lesson.teacher, {})
    start_time, end_time = lesson_times(lesson, config)
    change = change or {}
    return {
        "date": lesson.date,
        "day_of_week": lesson.day_of_week,
        "period": lesson.period,
        "start_time": start_time,
        "end_time": end_time,
        "subject_code": lesson.subject,
        "subject_label": subject.get("label") or lesson.subject,
        "color": subject.get("color") or "",
        "teacher_code": lesson.teacher,
        "teacher_label": teacher.get("label") or lesson.teacher,
        "teacher_surname": teacher.get("surname") or getattr(lesson, "teacher_surname", "") or "",
        "is_class_teacher": bool(teacher.get("is_class_teacher")),
        "room": lesson.room,
        "change_kind": change.get("kind") or "",
        "changed_fields": list(change.get("fields") or []),
        "previous": _previous_display(config, change.get("previous")),
    }
