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
AREA_MODULES = {
    AREA_TIMETABLE: (modules.TIMETABLE,),
    AREA_ABSENCE: (modules.ABSENCES,),
    AREA_POST: (modules.LETTERS, modules.PINBOARD),
    AREA_MESSENGER: (modules.MESSENGER,),
    AREA_CONFERENCES: (modules.CONFERENCES,),
}
DEFAULT_NAVIGATION = (AREA_TIMETABLE, AREA_ABSENCE, AREA_POST, AREA_MESSENGER, AREA_CONFERENCES)

BLOCKS = (
    {"key": "today", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 3, "normal": 10, "size": SIZE_NORMAL},
    {"key": "next_lesson", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 1, "size": SIZE_COMPACT},
    {"key": "week", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 1, "size": SIZE_NORMAL},
    {"key": "letters", "module": modules.LETTERS, "area": AREA_POST, "compact": 3, "normal": 5, "size": SIZE_NORMAL},
    {"key": "noticeboard", "module": modules.PINBOARD, "area": AREA_POST, "compact": 3, "normal": 5, "size": SIZE_COMPACT},
    {"key": "absences", "module": modules.ABSENCES, "area": AREA_ABSENCE, "compact": 2, "normal": 5, "size": SIZE_NORMAL},
    {"key": "conferences", "module": modules.CONFERENCES, "area": AREA_CONFERENCES, "compact": 1, "normal": 3, "size": SIZE_NORMAL},
    {"key": "holidays", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 1, "normal": 3, "size": SIZE_COMPACT},
    {"key": "changes", "module": modules.TIMETABLE, "area": AREA_TIMETABLE, "compact": 3, "normal": 6, "size": SIZE_COMPACT},
    {"key": "chat", "module": modules.MESSENGER, "area": AREA_MESSENGER, "compact": 3, "normal": 5, "size": SIZE_COMPACT},
)
BLOCK_KEYS = tuple(block["key"] for block in BLOCKS)
BLOCK_BY_KEY = {block["key"]: block for block in BLOCKS}

DEFAULT_OVERVIEW_KEYS = ("today", "letters", "noticeboard", "conferences", "changes", "chat")


def module_of(key):
    return BLOCK_BY_KEY[key]["module"]


def default_overview_blocks():
    return [{"key": block["key"], "size": block["size"]} for block in BLOCKS if block["key"] in DEFAULT_OVERVIEW_KEYS]


def default_navigation():
    return list(DEFAULT_NAVIGATION)


def normalize_modules_disabled(raw):
    listed = raw if isinstance(raw, list) else []
    kept = []
    for entry in listed:
        name = str(entry) if isinstance(entry, str) else ""
        if name in modules.MODULES and name not in kept:
            kept.append(name)
    return kept


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
        kept.append({"key": key, "size": size if size in SIZES else BLOCK_BY_KEY[key]["size"]})
    return kept


def normalize_navigation(raw):
    listed = raw if isinstance(raw, list) else []
    kept = []
    for entry in listed:
        area = str(entry) if isinstance(entry, str) else ""
        if area in AREA_MODULES and area not in kept:
            kept.append(area)
    for area in DEFAULT_NAVIGATION:
        if area not in kept:
            kept.append(area)
    return kept


def area_enabled(area, available, disabled):
    return any(available.get(name, True) and name not in disabled for name in AREA_MODULES.get(area, ()))
