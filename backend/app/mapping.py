import math
import re
import unicodedata

from . import period_grid

LESSON_MINUTES = 45
CLOCK = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

PALETTE = (
    ("white", "#ffffff", "#ffffff", "#8a9793", "#e3e8e6", "#6f7c79"),
    ("yellow", "#ffe100", "#ffe100", "#8a7a00", "#e6cf00", "#6e6300"),
    ("orange", "#ff9a1f", "#ff9a1f", "#8a4a00", "#ec8a14", "#7a4600"),
    ("red", "#d42020", "#d42020", "#ffb0b0", "#c92a2a", "#ffb0b0"),
    ("pink", "#ff69b4", "#ffb0cc", "#b8235f", "#f08ab2", "#8e1f4c"),
    ("magenta", "#c2187a", "#c2187a", "#ffb0dc", "#b8267a", "#ffb0dc"),
    ("purple", "#8f24b4", "#8f24b4", "#e2b8ff", "#9a38c0", "#e2b8ff"),
    ("lavender", "#9b7de8", "#d6c2ff", "#6f47c9", "#b39cf2", "#5b3bb0"),
    ("indigo", "#3d3ad0", "#3d3ad0", "#c0bfff", "#5a4ee6", "#c8c4ff"),
    ("blue", "#2a66d6", "#2a66d6", "#b0ccff", "#2860c8", "#b0ccff"),
    ("navy", "#1a2a66", "#1a2a66", "#9db0ff", "#243580", "#9db0ff"),
    ("sky", "#3b9cf0", "#b0d8ff", "#1c74c4", "#7ab8f2", "#0f4f8c"),
    ("cyan", "#22d3ee", "#22d3ee", "#0a6f80", "#22b8d0", "#075a68"),
    ("teal", "#0f7470", "#0f7470", "#9fe0dc", "#0f6e6a", "#9fe0dc"),
    ("mint", "#2ec48a", "#b6f0d6", "#1f8a63", "#7dd8b4", "#14624a"),
    ("green", "#2fa83c", "#4dbf57", "#1c5e22", "#3faa4c", "#164e1e"),
    ("forest", "#1f5c2c", "#1f5c2c", "#a8e6b4", "#2a6f39", "#a8e6b4"),
    ("lime", "#9be020", "#b8f03a", "#527a08", "#9fd428", "#4a6e08"),
    ("olive", "#8a8a1e", "#a8a626", "#4f4e0c", "#908e1e", "#3a3908"),
    ("brown", "#7a4a22", "#7a4a22", "#e6bd96", "#8a552a", "#e6bd96"),
    ("sand", "#c9a45c", "#e8d2a4", "#8a6a30", "#c9b07f", "#6e5426"),
    ("grey", "#8d9795", "#b9c0be", "#525c5a", "#8d9795", "#3e4745"),
    ("black", "#000000", "#262b2a", "#9aa5a1", "#000000", "#8a9793"),
    ("maroon", "#7a1236", "#7a1236", "#ffb0c8", "#8c1a42", "#ffb0c8"),
)

PALETTE_FIELDS = ("name", "base", "light_fill", "light_bar", "dark_fill", "dark_bar")
PALETTE_BY_NAME = {entry[0]: dict(zip(PALETTE_FIELDS, entry)) for entry in PALETTE}
PALETTE_NAMES = tuple(entry[0] for entry in PALETTE)
DEFAULT_COLOR_NAME = "grey"

DEFAULT_COLORS = (
    "blue", "orange", "green", "red", "purple", "yellow", "cyan", "pink", "teal", "brown",
    "indigo", "lime", "magenta", "sky", "olive", "navy", "mint", "maroon", "lavender", "forest", "sand",
)

DARK_INK = "#000000"
LIGHT_INK = "#ffffff"
BAR_SHADE = 0.55
THEMES = ("light", "dark")

COLOR_SOURCE = "color_source"
USER_COLOR = "user"
AUTO_COLOR = "auto"
COLOR_VERSION = "color_version"
CURRENT_COLOR_VERSION = 2

NAME_SOURCE = "label_source"
AUTO_NAME = "auto"

LEGACY_COLORS = {
    "#84142a": "maroon",
    "#f7703e": "orange",
    "#ec932f": "sand",
    "#7b791d": "olive",
    "#404f0e": "forest",
    "#2dae4b": "green",
    "#208068": "mint",
    "#135859": "teal",
    "#31aed2": "sky",
    "#2486ed": "blue",
    "#372daa": "indigo",
    "#834ac9": "lavender",
    "#a639a3": "magenta",
    "#7a1362": "purple",
    "#0e6b70": "teal",
    "#7a4b9c": "purple",
    "#b4602a": "brown",
    "#2f6b3a": "forest",
    "#9c3b5e": "magenta",
    "#3a5a9c": "blue",
    "#8a6a1f": "olive",
    "#2a6f63": "teal",
    "#5b4a9c": "indigo",
    "#1f6b8a": "blue",
    "#2563eb": "blue",
    "#7c3aed": "purple",
    "#16a34a": "green",
    "#0891b2": "cyan",
    "#db2777": "magenta",
    "#ea580c": "orange",
    "#ca8a04": "sand",
    "#0d9488": "teal",
    "#9333ea": "purple",
}

HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$")


def is_hex_color(value):
    return bool(HEX_COLOR.match(str(value or "").strip().lower()))


def normalize_color(value):
    text = str(value or "").strip().lower()
    if text in LEGACY_COLORS:
        return LEGACY_COLORS[text]
    return current_color(text)


def current_color(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in PALETTE_BY_NAME:
        return text
    if HEX_COLOR.match(text):
        return text
    return DEFAULT_COLOR_NAME


def palette_entry(value):
    text = str(value or "").strip().lower()
    return PALETTE_BY_NAME.get(LEGACY_COLORS.get(text, text))


def _rgb(hex_color):
    digits = hex_color.lstrip("#")
    return tuple(int(digits[index : index + 2], 16) for index in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(math.floor(channel + 0.5)))) for channel in rgb)


def _linear(channel):
    value = channel / 255
    return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4


def luminance(hex_color):
    red, green, blue = (_linear(channel) for channel in _rgb(hex_color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(hex_a, hex_b):
    lum_a, lum_b = luminance(hex_a), luminance(hex_b)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


def ink_for(fill):
    return DARK_INK if contrast_ratio(DARK_INK, fill) >= contrast_ratio(LIGHT_INK, fill) else LIGHT_INK


def bar_for(fill):
    towards = (0, 0, 0) if ink_for(fill) == DARK_INK else (255, 255, 255)
    return _hex(tuple(channel + (target - channel) * BAR_SHADE for channel, target in zip(_rgb(fill), towards)))


def subject_base(value):
    text = normalize_color(value)
    if not text:
        return ""
    if HEX_COLOR.match(text):
        return text
    return PALETTE_BY_NAME[text]["base"]


def subject_tokens(value, theme="light"):
    text = normalize_color(value)
    if not text:
        return None
    if HEX_COLOR.match(text):
        return {"fill": text, "ink": ink_for(text), "bar": bar_for(text)}
    entry = PALETTE_BY_NAME[text]
    fill = entry[f"{theme}_fill"]
    return {"fill": fill, "ink": ink_for(fill), "bar": entry[f"{theme}_bar"]}


CODE_SOURCE_DERIVED = "derived"
VOWELS = "AEIOU"


def _ascii_letters(text):
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    stripped = "".join(char for char in normalized if not unicodedata.combining(char))
    return "".join(char for char in stripped.upper() if char.isascii() and char.isalpha())


def needs_derived_subject_code(code, name):
    code = str(code or "")
    if len(code) > 4:
        return True
    return bool(name) and code == name


def derive_subject_code(name, taken):
    taken = set(taken or ())
    letters = _ascii_letters(name)
    consonants = "".join(char for char in letters if char not in VOWELS)
    candidates = []
    if len(letters) >= 2:
        candidates.append(letters[:2])
    if len(letters) >= 3:
        candidates.append(letters[:3])
    if len(consonants) >= 2:
        candidates.append(consonants[:4])
    for candidate in candidates:
        if candidate and candidate not in taken:
            return candidate
    base = candidates[0] if candidates else (letters[:2] or "XX")
    suffix = 2
    while True:
        candidate = f"{base}{suffix}"
        if candidate not in taken:
            return candidate
        suffix += 1


def _assign_subject_codes(subjects, native_subjects):
    taken = set()
    for key, entry in subjects.items():
        if not entry.get(CODE_SOURCE_DERIVED):
            taken.add(entry.get("code") or key)
    ordered = {}
    pending = []
    for key in sorted(subjects):
        entry = dict(subjects[key])
        native_name = native_subjects.get(key, ("", ""))[0]
        if entry.get(CODE_SOURCE_DERIVED):
            own = entry.get("code")
            if key in native_subjects and not needs_derived_subject_code(key, native_name):
                entry["code"] = key
                entry.pop(CODE_SOURCE_DERIVED, None)
                taken.add(key)
            elif own and own not in taken:
                taken.add(own)
            else:
                pending.append(key)
        elif "code" not in entry and needs_derived_subject_code(key, native_name):
            pending.append(key)
        ordered[key] = entry
    for key in pending:
        entry = ordered[key]
        code = derive_subject_code(native_subjects.get(key, ("", ""))[0] or key, taken)
        entry["code"] = code
        entry[CODE_SOURCE_DERIVED] = True
        taken.add(code)
    return {key: ordered[key] for key in subjects}


def default_color(index):
    return DEFAULT_COLORS[index % len(DEFAULT_COLORS)]


def _is_current(entry):
    return entry.get(COLOR_VERSION) == CURRENT_COLOR_VERSION


def _color_of(entry):
    value = entry.get("color", "")
    return current_color(value) if _is_current(entry) else normalize_color(value)


def has_user_color(entry):
    return isinstance(entry, dict) and entry.get(COLOR_SOURCE) == USER_COLOR and bool(_color_of(entry))


def _migrated_entry(entry):
    if not isinstance(entry, dict):
        return entry
    color = _color_of(entry)
    if _is_current(entry) and COLOR_SOURCE in entry:
        return entry if entry.get("color", "") == color else dict(entry, color=color)
    source = entry.get(COLOR_SOURCE) if COLOR_SOURCE in entry else (USER_COLOR if color else AUTO_COLOR)
    return dict(entry, color=color, **{COLOR_SOURCE: source, COLOR_VERSION: CURRENT_COLOR_VERSION})


def migrate_subject_colors(config):
    subjects = config.get("subjects") or {}
    migrated = {code: _migrated_entry(entry) for code, entry in subjects.items()}
    if all(migrated[code] is subjects[code] for code in subjects):
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


def _native_color(value):
    text = str(value or "").strip().lower()
    return text if HEX_COLOR.match(text) else ""


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
            subjects[code] = {"label": name or code, "color": color, COLOR_SOURCE: AUTO_COLOR, COLOR_VERSION: CURRENT_COLOR_VERSION}
            continue
        entry = dict(subjects[code])
        if name and _unnamed(entry, code):
            entry["label"] = name
        if color and not has_user_color(entry) and not _color_of(entry):
            entry["color"] = color
            entry[COLOR_SOURCE] = AUTO_COLOR
        subjects[code] = entry
    subjects = _assign_auto_colors(subjects)
    subjects = _assign_subject_codes(subjects, native_subjects)
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
    own = period_grid.own_duration(config, lesson.period)
    if not chosen and own is None:
        return native_start, native_end
    if chosen == native_start and own is None:
        return chosen, native_end
    start, end = period_grid.lesson_span(config, lesson.period, native_start, native_end)
    if start is None:
        return native_start, native_end
    return chosen or native_start, period_grid.clock_of(end) if end is not None else ""


def subject_label(config, code):
    if not code:
        return ""
    return config.get("subjects", {}).get(code, {}).get("label") or code


def teacher_label(config, code):
    if not code:
        return ""
    return config.get("teachers", {}).get(code, {}).get("label") or code


def teacher_surname(config, code):
    if not code:
        return ""
    return str(config.get("teachers", {}).get(code, {}).get("surname") or "").strip()


def _previous_display(config, previous):
    previous = previous or {}
    shown = {
        "subject": subject_label(config, previous.get("subject", "")),
        "teacher": teacher_label(config, previous.get("teacher", "")),
        "teacher_surname": teacher_surname(config, previous.get("teacher", "")),
        "room": previous.get("room", "") or "",
    }
    if previous.get("class"):
        shown["class"] = str(previous["class"])
    return shown


def _moved(value):
    if not isinstance(value, dict):
        return None
    return {"date": str(value.get("date") or ""), "period": value.get("period"), "period_end": value.get("period_end")}


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
        "subject_key": lesson.subject,
        "subject_code": subject.get("code") or lesson.subject,
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
        "classes": str(change.get("classes") or ""),
        "teacher_hidden": bool(change.get("teacher_hidden")),
        "no_details": bool(change.get("no_details")),
        "change_note": str(change.get("note") or ""),
        "moved_to": _moved(change.get("moved_to")),
        "moved_from": _moved(change.get("moved_from")),
    }
