import re

from bs4 import BeautifulSoup

from .exercises import header_labels, note_once, parse_moment
from .pages import path_of, squeezed

FORUMS_PATH = "/iserv/forums"
FORUM_ROOT = "/iserv/forum/"
READ_PATH = "/iserv/forum/read"
FORUM_PATH = re.compile(r"^/iserv/forum/((?:group/)?[^/?#]+)/?$")
RESERVED = frozenset({"read", "search", "settings", "unread", "change", "new", "add", "group"})
TABLE_MARK = re.compile(r"forum", re.IGNORECASE)
TITLE = "title"
UNREAD = "unread"
LAST = "last"
COLUMN_WORDS = {
    TITLE: ("titel", "title", "forum", "foren", "forums", "name"),
    UNREAD: ("neu", "new", "ungelesen", "unread"),
    LAST: ("letzter beitrag", "last post", "letzte beiträge", "latest post", "zuletzt"),
}
EMPTY_COUNTS = frozenset({"", "-", "–", "—", "0"})
COUNT = re.compile(r"^\d{1,6}$")
TITLE_LIMIT = 200
TEXT_LIMIT = 300
EXTRA_LIMIT = 8


class ForumShapeError(ValueError):
    pass


def _key(text):
    return " ".join(str(text or "").casefold().replace(":", " ").split())


def _column_of(label):
    key = _key(label)
    if not key:
        return None
    for column, words in COLUMN_WORDS.items():
        if key in words:
            return column
    for column, words in COLUMN_WORDS.items():
        if any(word in key.split() for word in words if " " not in word):
            return column
    return None


def _span(cell):
    try:
        return max(1, int(cell.get("colspan") or 1))
    except (TypeError, ValueError):
        return 1


def spread_cells(row):
    cells = []
    for cell in row.find_all(["td", "th"], recursive=False):
        cells.extend([cell] + [None] * (_span(cell) - 1))
    return cells


def _controls_only(cell):
    if cell is None:
        return True
    if squeezed(cell.get_text(" "), TEXT_LIMIT):
        return False
    return cell.find("a", href=True) is None


def forum_key(path):
    match = FORUM_PATH.match(path_of(path or "").rstrip("/") or "")
    if not match:
        return ""
    key = match.group(1)
    head = key.split("/", 1)[0]
    if key == head and head in RESERVED:
        return ""
    return key


def _table(soup):
    for table in soup.find_all("table"):
        if TABLE_MARK.search(str(table.get("id") or "")):
            return table
    for table in soup.find_all("table"):
        if any(forum_key(anchor["href"]) for anchor in table.find_all("a", href=True)):
            return table
    return None


def _header_row(table):
    head = table.find("thead")
    row = head.find("tr") if head is not None else None
    if row is None:
        first = table.find("tr")
        if first is not None and first.find("th") is not None and first.find("td") is None:
            row = first
    return row


def _columns(labels):
    found = {}
    for index, label in enumerate(labels):
        column = _column_of(label)
        if column is not None and column not in found:
            found[column] = index
    return found


def _trimmed(items, empty):
    end = len(items)
    while end and empty(items[end - 1]):
        end -= 1
    return items[:end]


def _aligned(cells, labels, index):
    row = _trimmed(cells, _controls_only)
    head = _trimmed(labels, lambda label: not label)
    if index is None or index >= len(head):
        return None
    position = index + len(row) - len(head)
    if 0 <= position < len(row):
        return row[position]
    return None


def count_of(cell):
    if cell is None:
        return None
    text = squeezed(cell.get_text(" "), TEXT_LIMIT)
    if text in EMPTY_COUNTS:
        return 0
    if COUNT.match(text):
        return int(text)
    digits = re.findall(r"\d{1,6}", text)
    if len(digits) == 1 and len(text) <= 12:
        return int(digits[0])
    return None


def _forum_anchor(row, title_cell):
    holders = ([title_cell] if title_cell is not None else []) + [row]
    for holder in holders:
        anchors = [anchor for anchor in holder.find_all("a", href=True) if forum_key(anchor["href"])]
        texts = [anchor for anchor in anchors if squeezed(anchor.get_text(" "), TITLE_LIMIT)]
        if texts or anchors:
            return (texts or anchors)[0]
    return None


def _description(cell, title):
    if cell is None:
        return ""
    text = squeezed(cell.get_text(" "), TEXT_LIMIT)
    if title and text.startswith(title):
        text = text[len(title):].strip(" -–·:")
    return text


def _forum_row(row, labels, columns, category):
    cells = spread_cells(row)
    title_cell = _aligned(cells, labels, columns.get(TITLE))
    anchor = _forum_anchor(row, title_cell)
    if anchor is None:
        return None
    path = path_of(anchor["href"]).rstrip("/")
    title = squeezed(anchor.get_text(" "), TITLE_LIMIT) or (squeezed(title_cell.get_text(" "), TITLE_LIMIT) if title_cell is not None else "")
    unread_cell = _aligned(cells, labels, columns.get(UNREAD))
    last_cell = _aligned(cells, labels, columns.get(LAST))
    last = squeezed(last_cell.get_text(" "), TEXT_LIMIT) if last_cell is not None else ""
    used = {id(cell) for cell in (title_cell, unread_cell, last_cell) if cell is not None}
    extra = []
    for index, cell in enumerate(cells):
        if cell is None or id(cell) in used or anchor in cell.find_all("a"):
            continue
        text = squeezed(cell.get_text(" "), TEXT_LIMIT)
        if text and len(extra) < EXTRA_LIMIT:
            label = _label_for(cells, labels, cell)
            extra.append({"label": label, "value": text})
    return {
        "id": forum_key(path),
        "title": title,
        "description": _description(title_cell, title),
        "category": category,
        "unread": count_of(unread_cell) if UNREAD in columns else None,
        "last_post": last,
        "last_post_date": parse_moment(last),
        "path": path,
        "extra": extra,
    }


def _label_for(cells, labels, wanted):
    for index in range(len(labels)):
        if _aligned(cells, labels, index) is wanted:
            return labels[index]
    return ""


def _category_of(row):
    cells = [cell for cell in row.find_all(["td", "th"], recursive=False)]
    if len(cells) != 1:
        return None
    if any(forum_key(anchor["href"]) for anchor in row.find_all("a", href=True)):
        return None
    return squeezed(cells[0].get_text(" "), TITLE_LIMIT)


def _read_form(soup):
    for form in soup.find_all("form"):
        if path_of(form.get("action") or "").rstrip("/") == READ_PATH and str(form.get("method") or "get").lower() == "post":
            return True
    return False


def parse_forums(html, list_path=FORUMS_PATH):
    soup = BeautifulSoup(html or "", "html.parser")
    table = _table(soup)
    mark_read = _read_form(soup)
    if table is None:
        note_once("forum", list_path, "no forum table")
        raise ForumShapeError("forum overview carries no forum table")
    header = _header_row(table)
    labels = header_labels(table) if header is not None else []
    columns = _columns(labels)
    if labels and UNREAD not in columns:
        note_once("forum", list_path, "no unread column among %d columns" % len(labels))
    forums = []
    seen = set()
    category = ""
    skipped = 0
    for row in table.find_all("tr"):
        if row is header or row.find_parent("thead") is not None or row.find_parent("table") is not table:
            continue
        if all(_controls_only(cell) for cell in row.find_all(["td", "th"], recursive=False)):
            continue
        heading = _category_of(row)
        if heading is not None:
            category = heading
            continue
        forum = _forum_row(row, labels, columns, category)
        if forum is None:
            skipped += 1
            continue
        if forum["id"] in seen:
            continue
        seen.add(forum["id"])
        forums.append(forum)
    if skipped and not forums:
        note_once("forum", list_path, "%d item rows unreadable, no forum link found" % skipped)
        raise ForumShapeError("forum table rows carry no readable forum")
    if skipped:
        note_once("forum", list_path, "skipped %d unreadable item rows" % skipped)
    return {"forums": forums, "mark_read": mark_read, "complete": not skipped}


def total_unread(forums):
    return sum(forum["unread"] for forum in forums if isinstance(forum.get("unread"), int) and not isinstance(forum.get("unread"), bool))


def is_forum_page(path):
    path = path_of(path or "").rstrip("/")
    return path == FORUMS_PATH or path == FORUM_ROOT.rstrip("/") or path.startswith(FORUM_ROOT) or path.startswith(FORUMS_PATH + "/")
