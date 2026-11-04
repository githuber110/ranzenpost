import json
import re

from .conference_booking import moment_of
from .conferences import PageReader
from .errors import DataError

PRINT = "print"
COURSE_SELECTION = "course-selection"
VIDEO_ROOMS = "videoconference"
POLLS = "poll"
TASK_LIST = "todo"
UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
PAGE_MODULES = {
    PRINT: {
        "path": "/iserv/print",
        "prefix": "/iserv/print/",
        "pages": None,
        "never": frozenset({"download", "cancel", "abort"}),
    },
    COURSE_SELECTION: {
        "path": "/iserv/courseselection",
        "prefix": "/iserv/courseselection/",
        "pages": re.compile(r"/iserv/courseselection/\d+/?"),
        "never": frozenset({"export", "download", "choose", "select", "enroll"}),
    },
    VIDEO_ROOMS: {
        "path": "/iserv/videoconference/",
        "prefix": "/iserv/videoconference/",
        "pages": None,
        "never": frozenset({"join", "joinroom", "start", "enter", "guest", "invite", "end", "leave", "meeting", "bbb"}),
    },
    POLLS: {
        "path": "/iserv/poll",
        "prefix": "/iserv/poll/",
        "pages": re.compile(r"/iserv/poll/(?:\d+|%s)(?:/results?)?/?" % UUID),
        "never": frozenset({"vote", "export", "download", "answer", "choose", "close", "participate"}),
    },
}
PAGE_QUERY = re.compile(r"page=\d+")
TODO_PATH = "/iserv/todo/api/frontend/tasks"
TODO_PREFIX = "/iserv/todo/"
MAX_TEXT = 2000
MAX_TITLE = 400


def within(prefix):
    root = prefix.rstrip("/")

    def check(path):
        clean = str(path or "").split("?", 1)[0]
        return clean == root or clean.startswith(root + "/")

    return check


def page_allowed(slug, path):
    rule = PAGE_MODULES[slug]
    clean, _, query = str(path or "").partition("?")
    if query and not PAGE_QUERY.fullmatch(query):
        return False
    if clean.rstrip("/") == rule["prefix"].rstrip("/"):
        return True
    return bool(rule["pages"] and rule["pages"].fullmatch(clean))


def read_module_page(html, url, slug):
    rule = PAGE_MODULES[slug]
    allowed = lambda path: page_allowed(slug, path)
    return PageReader(url, prefix=rule["prefix"], read_only=True, never=rule["never"], allowed=allowed).read(html)


def _text(value, limit):
    return " ".join(str(value if value is not None else "").split())[:limit]


def _task(entry):
    due = moment_of(entry.get("due")) if entry.get("due") else None
    return {
        "id": _text(entry.get("uid"), MAX_TITLE),
        "summary": _text(entry.get("summary"), MAX_TITLE),
        "description": _text(entry.get("description"), MAX_TEXT),
        "date": due.date().isoformat() if due else "",
        "time": due.strftime("%H:%M") if due else "",
    }


def _completed(entry):
    value = entry.get("completed")
    if value is None or isinstance(value, bool):
        return bool(value)
    if moment_of(value) is None:
        raise DataError("the to-do answer has an unknown state")
    return True


def read_todo(text):
    try:
        data = json.loads(text or "")
    except ValueError as error:
        raise DataError("the to-do answer is not JSON") from error
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        raise DataError("the to-do answer lacks its tasks")
    if not all(isinstance(entry, dict) and (entry.get("uid") or entry.get("summary")) for entry in tasks):
        raise DataError("the to-do answer lists something else than tasks")
    done = [_completed(entry) for entry in tasks]
    return {
        "open": [_task(entry) for entry, finished in zip(tasks, done) if not finished],
        "done": [_task(entry) for entry, finished in zip(tasks, done) if finished],
    }
