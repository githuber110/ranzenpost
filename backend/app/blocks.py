import re

from . import modules

SIZE_COMPACT = "compact"
SIZE_NORMAL = "normal"
SIZES = (SIZE_COMPACT, SIZE_NORMAL)

AREA_OVERVIEW = "overview"
AREA_TIMETABLE = "timetable"
AREA_ABSENCE = "absence"
AREA_POST = "post"
AREA_MESSENGER = "messenger"
AREA_CONFERENCES = "conferences"
AREA_CALENDAR = "calendar"
AREA_TASKS = "tasks"
AREA_NEWS = "news"
AREA_MAIL = "mail"
AREA_FILES = "files"
AREA_CONTACTS = "contacts"
AREA_FORUMS = "forums"
AREA_TEXTS = "texts"
AREA_INFODISPLAY = "infodisplay"
AREA_WHITEBOARDS = "whiteboards"
AREA_MODULES = {
    AREA_TIMETABLE: (modules.TIMETABLE,),
    AREA_ABSENCE: (modules.ABSENCES,),
    AREA_POST: (modules.LETTERS, modules.PINBOARD),
    AREA_MESSENGER: (modules.MESSENGER,),
    AREA_CONFERENCES: (modules.CONFERENCES,),
    AREA_CALENDAR: (modules.CALENDAR,),
    AREA_TASKS: (modules.TASKS,),
    AREA_NEWS: (modules.NEWS,),
    AREA_MAIL: (modules.MAIL,),
    AREA_FILES: (modules.FILES,),
    AREA_CONTACTS: (modules.ADDRESSBOOK, modules.MAILING_LISTS),
    AREA_FORUMS: (modules.FORUMS,),
    AREA_TEXTS: (modules.TEXTS,),
    AREA_INFODISPLAY: (modules.INFODISPLAY,),
    AREA_WHITEBOARDS: (modules.WHITEBOARDS,),
}
DEFAULT_NAVIGATION = (AREA_TIMETABLE, AREA_ABSENCE, AREA_POST, AREA_MESSENGER, AREA_CONFERENCES)

BLOCKS = (
    {"key": "today", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 3, "normal": 10, "size": SIZE_NORMAL},
    {"key": "next_day", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 3, "normal": 10, "size": SIZE_NORMAL},
    {"key": "next_lesson", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 1, "size": SIZE_COMPACT},
    {"key": "week", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 1, "size": SIZE_NORMAL},
    {"key": "letters", "module": modules.LETTERS, "area": AREA_POST, "compact": 3, "normal": 5, "size": SIZE_NORMAL},
    {"key": "noticeboard", "module": modules.PINBOARD, "area": AREA_POST, "compact": 3, "normal": 5, "size": SIZE_COMPACT},
    {"key": "absences", "module": modules.ABSENCES, "area": AREA_ABSENCE, "compact": 2, "normal": 5, "size": SIZE_NORMAL},
    {"key": "conferences", "module": modules.CONFERENCES, "area": AREA_CONFERENCES, "compact": 1, "normal": 3, "size": SIZE_NORMAL},
    {"key": "holidays", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 3, "size": SIZE_COMPACT},
    {"key": "changes", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 3, "normal": 6, "size": SIZE_COMPACT},
    {"key": "chat", "module": modules.MESSENGER, "area": AREA_MESSENGER, "compact": 3, "normal": 5, "size": SIZE_COMPACT},
    {"key": "school_events", "module": modules.CALENDAR, "area": AREA_CALENDAR, "compact": 2, "normal": 5, "size": SIZE_NORMAL},
    {"key": "tasks", "module": modules.TASKS, "area": AREA_TASKS, "compact": 3, "normal": 6, "size": SIZE_NORMAL},
    {"key": "news", "module": modules.NEWS, "area": AREA_NEWS, "compact": 3, "normal": 5, "size": SIZE_COMPACT},
    {"key": "forums", "module": modules.FORUMS, "area": AREA_FORUMS, "compact": 3, "normal": 6, "size": SIZE_COMPACT},
    {"key": "texts", "module": modules.TEXTS, "area": AREA_TEXTS, "compact": 3, "normal": 6, "size": SIZE_COMPACT},
    {"key": "infodisplay", "module": modules.INFODISPLAY, "area": AREA_INFODISPLAY, "compact": 2, "normal": 5, "size": SIZE_COMPACT},
    {"key": "whiteboards", "module": modules.WHITEBOARDS, "area": AREA_WHITEBOARDS, "compact": 2, "normal": 5, "size": SIZE_COMPACT},
)
BLOCK_KEYS = tuple(block["key"] for block in BLOCKS)
BLOCK_BY_KEY = {block["key"]: block for block in BLOCKS}

DEFAULT_OVERVIEW_KEYS = ("today", "letters", "noticeboard", "conferences", "changes", "chat", "tasks", "news", "forums")


def default_overview_blocks():
    return [{"key": block["key"], "size": block["size"]} for block in BLOCKS if block["key"] in DEFAULT_OVERVIEW_KEYS]


def normalize_modules_disabled(raw):
    listed = raw if isinstance(raw, list) else []
    kept = []
    for entry in listed:
        name = str(entry) if isinstance(entry, str) else ""
        if name in modules.MODULES and name not in kept:
            kept.append(name)
    return kept


SWITCH_END = "end"
SWITCH_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
SWITCH_BLOCKS = ("today",)


def switch_of(value):
    if isinstance(value, bool):
        return ""
    if isinstance(value, int) and 0 <= value < 24 * 60:
        return "%02d:%02d" % divmod(value, 60)
    text = value.strip() if isinstance(value, str) else ""
    return text if text == SWITCH_END or SWITCH_TIME.match(text) else ""


def normalize_overview_blocks(raw, disabled=()):
    if not isinstance(raw, list):
        return default_overview_blocks()
    off = set(disabled)
    kept = []
    seen = set()
    for entry in raw:
        key = entry.get("key") if isinstance(entry, dict) else entry
        if not isinstance(key, str) or key not in BLOCK_BY_KEY or key in seen:
            continue
        if BLOCK_BY_KEY[key]["module"] in off:
            continue
        size = entry.get("size") if isinstance(entry, dict) else None
        seen.add(key)
        normalized = {"key": key, "size": size if size in SIZES else BLOCK_BY_KEY[key]["size"]}
        turn = switch_of(entry.get("switch")) if key in SWITCH_BLOCKS and isinstance(entry, dict) else ""
        if turn:
            normalized["switch"] = turn
        kept.append(normalized)
    return kept


def normalize_navigation(raw):
    listed = raw if isinstance(raw, list) else []
    kept = []
    for entry in listed:
        area = str(entry) if isinstance(entry, str) else ""
        if area in AREA_MODULES and area not in kept:
            kept.append(area)
    for area in DEFAULT_NAVIGATION + tuple(AREA_MODULES):
        if area not in kept:
            kept.append(area)
    return kept


def area_enabled(area, available, disabled):
    return any(available.get(name, True) and name not in disabled for name in AREA_MODULES.get(area, ()))
