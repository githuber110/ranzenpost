import hashlib
import logging
import re
from datetime import date, datetime
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup

from ..pathpattern import path_pattern
from .pages import path_of, squeezed

logger = logging.getLogger(__name__)

EXERCISE_PATH = "/iserv/exercise"
PAST_EXERCISE_PATH = "/iserv/exercise/past/exercise"
EXERCISE_ROOT = EXERCISE_PATH + "/"
DETAIL_PATH = re.compile(r"^/iserv/exercise/show/([^/?#]+)/?$")
TABLE_ID = "crud-table"
PAGE_LIMIT = 20
TITLE_LIMIT = 300
TEXT_LIMIT = 300
TAG_LIMIT = 30
EXTRA_LIMIT = 12
TITLE = "title"
START = "start"
DUE = "due"
TAGS = "tags"
DONE = "done"
FIELDS = (TITLE, START, DUE, TAGS, DONE)
COLUMN_LABELS = {
    TITLE: ("aufgabe", "titel", "bezeichnung", "task", "title", "exercise", "name"),
    START: ("starttermin", "startdatum", "beginn", "start date", "starts", "start", "von", "from"),
    DUE: ("abgabetermin", "abgabedatum", "abgabe", "fällig", "fällig am", "ende", "bis", "due date", "due", "deadline", "end date", "end", "until"),
    TAGS: ("tags", "tag", "schlagwörter", "schlagworte", "stichwörter", "labels"),
    DONE: ("erledigt", "abgegeben", "status", "done", "completed", "finished", "submitted", "handed in"),
}
YES_WORDS = frozenset({"ja", "yes", "erledigt", "abgegeben", "done", "completed", "submitted", "finished", "✓", "✔"})
NO_WORDS = frozenset({"nein", "no", "offen", "open", "nicht erledigt", "nicht abgegeben", "not done", "pending", "✗"})
YES_CLASSES = ("fa-check", "glyphicon-ok", "check", "text-success", "done", "success")
NO_CLASSES = ("fa-times", "fa-xmark", "glyphicon-remove", "text-danger", "times", "danger")
DATE_DE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4})(?:,?\s+(\d{1,2}):(\d{2}))?")
DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?")
DATE_SLASH = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?:,?\s+(\d{1,2}):(\d{2})\s*([ap]\.?m\.?)?)?", re.IGNORECASE)
SORT_ATTRIBUTES = ("data-sort", "data-order", "data-value", "datetime", "title")
NOISE = re.compile(r"[\s:▲▼↑↓⇅]+")
WORDS = re.compile(r"[^\W\d_]+")
WORD_MIN = 4
COMPOUND_MIN = 5
FIRST_PAGE = "1"
_NOTED = set()


class ExerciseShapeError(ValueError):
    pass


def note_once(kind, path, reason):
    key = (kind, path_pattern(path), reason)
    if key in _NOTED:
        return
    _NOTED.add(key)
    logger.info("%s page shape unknown at %s: %s", kind, path_pattern(path), reason)


def _label_key(text):
    return NOISE.sub(" ", str(text or "").casefold()).strip()


def _label_within(words, label):
    parts = WORDS.findall(label)
    if not parts or (len(parts) == 1 and len(label) < WORD_MIN):
        return False
    size = len(parts)
    if any(words[index:index + size] == parts for index in range(len(words) - size + 1)):
        return True
    return size == 1 and len(label) >= COMPOUND_MIN and any(word != label and word.endswith(label) for word in words)


def _field_of(label, taken):
    key = _label_key(label)
    if not key:
        return None
    for field in FIELDS:
        if field not in taken and key in COLUMN_LABELS[field]:
            return field
    words = WORDS.findall(key)
    for field in FIELDS:
        if field in taken:
            continue
        if any(_label_within(words, word) for word in COLUMN_LABELS[field]):
            return field
    return None


def map_columns(labels):
    mapping = {}
    taken = set()
    for index, label in enumerate(labels):
        field = _field_of(label, taken)
        if field is not None:
            mapping[index] = field
            taken.add(field)
    return mapping


def _header_cells(table):
    head = table.find("thead")
    row = head.find("tr") if head is not None else None
    if row is None:
        first = table.find("tr")
        if first is not None and first.find("th") is not None and first.find("td") is None:
            row = first
    if row is None:
        return None, []
    return row, row.find_all(["th", "td"], recursive=False)


def _span(cell):
    try:
        return max(1, int(cell.get("colspan") or 1))
    except (TypeError, ValueError):
        return 1


def header_labels(table):
    _row, cells = _header_cells(table)
    labels = []
    for cell in cells:
        labels.extend([squeezed(cell.get_text(" "), TITLE_LIMIT)] + [""] * (_span(cell) - 1))
    return labels


def _moment(year, month, day, hour=None, minute=None):
    try:
        if hour is None:
            return date(int(year), int(month), int(day)).isoformat()
        return datetime(int(year), int(month), int(day), int(hour), int(minute)).strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return ""


def parse_moment(text):
    value = str(text or "").strip()
    if not value:
        return ""
    match = DATE_ISO.search(value)
    if match:
        return _moment(*match.groups())
    match = DATE_DE.search(value)
    if match:
        day, month, year, hour, minute = match.groups()
        return _moment(year, month, day, hour, minute)
    match = DATE_SLASH.search(value)
    if match:
        first, second, year, hour, minute, meridiem = match.groups()
        if int(first) > 12:
            day, month = first, second
        elif int(second) > 12:
            month, day = first, second
        else:
            return ""
        if hour is not None and meridiem:
            hour = str(int(hour) % 12 + (12 if meridiem.lower().startswith("p") else 0))
        return _moment(year, month, day, hour, minute)
    return ""


def _cell_moment(cell):
    for name in SORT_ATTRIBUTES:
        for holder in [cell] + cell.find_all(True):
            found = parse_moment(holder.get(name)) if holder.get(name) else ""
            if found:
                return found
    return parse_moment(cell.get_text(" "))


def _classes(cell):
    names = []
    for holder in [cell] + cell.find_all(True):
        names.extend(str(name).lower() for name in holder.get("class") or [])
    return names


def _done_of(cell):
    text = squeezed(cell.get_text(" "), TEXT_LIMIT).casefold()
    if text in YES_WORDS:
        return True
    if text in NO_WORDS:
        return False
    box = cell.find("input", attrs={"type": "checkbox"})
    if box is not None and not text:
        return box.has_attr("checked")
    classes = _classes(cell)
    if any(marker in name for name in classes for marker in NO_CLASSES):
        return False
    if any(marker in name for name in classes for marker in YES_CLASSES):
        return True
    return None


def _tags_of(cell):
    marked = cell.find_all(class_=re.compile(r"\b(label|badge|tag)\b"))
    if not marked:
        marked = [item for item in cell.find_all(["a", "li"]) if squeezed(item.get_text(" "), TEXT_LIMIT)]
    if marked:
        values = [squeezed(item.get_text(" "), TAG_LIMIT * 4) for item in marked]
    else:
        values = [squeezed(part, TAG_LIMIT * 4) for part in cell.get_text(",").split(",")]
    tags = []
    for value in values:
        if value and value not in tags:
            tags.append(value)
    return tags[:TAG_LIMIT]


def _only_controls(cell):
    if squeezed(cell.get_text(" "), TEXT_LIMIT):
        return False
    return cell.find(["input", "button", "select"]) is not None or not cell.find(True)


def _detail_path(row):
    for anchor in row.find_all("a", href=True):
        path = path_of(anchor["href"])
        if DETAIL_PATH.match(path):
            return path
    return ""


def _row_cells(row):
    cells = []
    for cell in row.find_all(["td", "th"], recursive=False):
        cells.extend([cell] + [None] * (_span(cell) - 1))
    return cells


def _task_id(path, title, start):
    match = DETAIL_PATH.match(path or "")
    if match:
        return match.group(1)
    digest = hashlib.sha256("\n".join((title, start)).encode("utf-8")).hexdigest()
    return "h" + digest[:16]


def unique_id(task, seen):
    if task["id"] not in seen:
        return task["id"]
    if task["path"]:
        return None
    number = 2
    while "%s-%d" % (task["id"], number) in seen:
        number += 1
    return "%s-%d" % (task["id"], number)


def _positional(cells):
    found = {}
    moments = []
    for index, cell in enumerate(cells):
        if cell is None or _only_controls(cell):
            continue
        if TITLE not in found:
            found[TITLE] = index
            continue
        if _cell_moment(cell):
            moments.append(index)
    if moments:
        found[START] = moments[0]
    if len(moments) > 1:
        found[DUE] = moments[1]
    return {index: field for field, index in found.items()}


def parse_task_row(row, mapping, labels, past):
    cells = _row_cells(row)
    real = [cell for cell in cells if cell is not None]
    path = _detail_path(row)
    if not real or (len(real) == 1 and not path):
        return None
    if all(_only_controls(cell) for cell in real):
        return None
    columns = mapping or _positional(cells)
    values = {TITLE: "", START: "", DUE: "", TAGS: [], DONE: None}
    texts = {START: "", DUE: "", DONE: ""}
    extra = []
    for index, cell in enumerate(cells):
        if cell is None:
            continue
        field = columns.get(index)
        text = squeezed(cell.get_text(" "), TEXT_LIMIT)
        if field == TITLE:
            values[TITLE] = squeezed(cell.get_text(" "), TITLE_LIMIT)
        elif field in (START, DUE):
            values[field] = _cell_moment(cell)
            texts[field] = text
        elif field == TAGS:
            values[TAGS] = _tags_of(cell)
        elif field == DONE:
            values[DONE] = _done_of(cell)
            texts[DONE] = text
        elif text and len(extra) < EXTRA_LIMIT:
            label = labels[index] if index < len(labels) else ""
            extra.append({"label": label, "value": text})
    if not values[TITLE] and path:
        anchor = next((item for item in row.find_all("a", href=True) if path_of(item["href"]) == path and squeezed(item.get_text(" "), TEXT_LIMIT)), None)
        values[TITLE] = squeezed(anchor.get_text(" "), TITLE_LIMIT) if anchor is not None else ""
    if not values[TITLE] and not path:
        if not extra:
            return None
        values[TITLE] = extra.pop(0)["value"]
    return {
        "id": _task_id(path, values[TITLE], texts[START]),
        "title": values[TITLE],
        "start": values[START],
        "start_text": texts[START],
        "due": values[DUE],
        "due_text": texts[DUE],
        "tags": values[TAGS],
        "done": values[DONE],
        "done_text": texts[DONE],
        "past": bool(past),
        "path": path,
        "extra": extra,
    }


def _table(soup):
    table = soup.find("table", id=TABLE_ID)
    if table is not None:
        return table
    for candidate in soup.find_all("table"):
        if any(DETAIL_PATH.match(path_of(anchor["href"])) for anchor in candidate.find_all("a", href=True)):
            return candidate
    return None


def _body_rows(table, header_row):
    body = table.find("tbody")
    rows = body.find_all("tr", recursive=False) if body is not None else table.find_all("tr")
    return [row for row in rows if row is not header_row and row.find_parent("thead") is None]


def _first_page(query):
    pairs = parse_qsl(query, keep_blank_values=True)
    return not pairs or (len(pairs) == 1 and pairs[0] == ("page", FIRST_PAGE))


def page_links(soup, list_path):
    links = []
    for holder in soup.find_all(class_=re.compile(r"\bpagination\b")):
        for anchor in holder.find_all("a", href=True):
            parts = urlsplit(urljoin(list_path, anchor["href"].strip()))
            if path_of(parts.path).rstrip("/") != list_path.rstrip("/") or _first_page(parts.query):
                continue
            target = list_path.rstrip("/") + "?" + parts.query
            if target not in links:
                links.append(target)
    return links


def parse_exercises(html, list_path=EXERCISE_PATH, past=False):
    soup = BeautifulSoup(html or "", "html.parser")
    table = _table(soup)
    if table is None:
        note_once("exercise", list_path, "no task table")
        raise ExerciseShapeError("exercise list carries no task table")
    header_row, _cells = _header_cells(table)
    labels = header_labels(table)
    mapping = map_columns(labels)
    if labels and TITLE not in mapping.values():
        note_once("exercise", list_path, "no title column among %d columns" % len(labels))
    tasks = []
    seen = set()
    for row in _body_rows(table, header_row):
        task = parse_task_row(row, mapping, labels, past)
        if task is None:
            continue
        task_id = unique_id(task, seen)
        if task_id is None:
            continue
        seen.add(task_id)
        tasks.append(dict(task, id=task_id))
    return {"tasks": tasks, "labels": labels, "pages": page_links(soup, list_path)}


def is_exercise_page(path):
    path = path_of(path or "")
    return path.rstrip("/") == EXERCISE_PATH or path.startswith(EXERCISE_ROOT)
