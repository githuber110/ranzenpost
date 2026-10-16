import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

LIST_TABLE_ID = "crud-table"
ROLE_FROM = "from"
ROLE_TILL = "till"
ROLE_PERIOD = "period"
ROLE_NAME = "name"
ROLE_CLASS = "class"
ROLE_STATUS = "status"
ROLE_CREATED = "created"
ROLE_REASON = "reason"
ROLE_WORDS = (
    (ROLE_CREATED, frozenset("erstellt created eingetragen eingereicht angelegt submitted gemeldet reported added".split())),
    (ROLE_CLASS, frozenset("klasse klassen class classes kurs course gruppe group stufe jahrgang grade form".split())),
    (ROLE_STATUS, frozenset("status zustand state".split())),
    (ROLE_NAME, frozenset("name schueler schuelerin student pupil kind child person benutzer user".split())),
    (ROLE_FROM, frozenset("von from beginn begin start ab since".split())),
    (ROLE_TILL, frozenset("bis until till to ende end".split())),
    (
        ROLE_REASON,
        frozenset(
            "grund reason bemerkung kommentar comment notiz note anmerkung beschreibung description text art typ type "
            "kategorie category abwesenheitsart abwesenheitsgrund".split()
        ),
    ),
    (
        ROLE_PERIOD,
        frozenset(
            "zeitraum datum date dates period zeit time tag tage day days wann when abwesenheit abwesend absence absent dauer duration".split()
        ),
    ),
)
ROLE_PREFIXES = {ROLE_CLASS: ("klasse",), ROLE_NAME: ("schueler", "student")}
ROLE_SUFFIXES = {ROLE_NAME: ("name",)}
STATUS_OPEN = "open"
STATUS_ACCEPTED = "accepted"
STATUS_REJECTED = "rejected"
STATUS_WORDS = (
    (STATUS_REJECTED, frozenset("unentschuldigt unexcused abgelehnt rejected declined denied".split())),
    (STATUS_ACCEPTED, frozenset("entschuldigt excused bestaetigt confirmed akzeptiert accepted genehmigt approved angenommen".split())),
    (STATUS_OPEN, frozenset("offen open neu new ausstehend pending unbearbeitet eingereicht submitted".split())),
)
NEGATION_WORDS = frozenset("nicht not kein keine no".split())
PENDING_WORDS = frozenset("noch yet bearbeitet processed geprueft reviewed".split())
GERMAN_DATE = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})(?!\d)")
ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
CLOCK = re.compile(r"(?<![\d.:])(\d{1,2}):(\d{2})(?![\d])")
ID_SEGMENT = re.compile(r"/iserv/absence/(?:[^/?#]+/)*?(\d+)(?:[/?#]|$)")
TOKEN = re.compile(r"[^\W\d_]+")
FOLDED = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}
EMPTY_ROW_CLASSES = frozenset({"empty", "dataTables_empty", "no-results", "no-data"})
FILTER_PREFIX = "filter["
EARLIEST_DAY = date(2000, 1, 1)
LATEST_DAYS_AHEAD = 5 * 366
UPPER_BOUND_WORDS = frozenset("to till until end bis ende".split())
SKIPPED_INPUT_TYPES = frozenset({"submit", "button", "image", "reset", "file", "password"})
LIST_PATH = "/iserv/absence/"
DELETE_SEGMENTS = frozenset("delete remove".split())
EDIT_SEGMENTS = frozenset("edit update".split())


class OlderAbsenceShapeError(ValueError):
    pass


@dataclass
class OlderAbsenceRow:
    name: str
    from_date: str
    till_date: str
    from_time: str = ""
    till_time: str = ""
    status: str = ""
    class_text: str = ""
    created: str = ""
    reason: str = ""
    entry_id: str = ""
    delete_path: str = ""
    detail_path: str = ""


@dataclass
class OlderAbsenceList:
    roles: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    unreadable: int = 0


def fold(text):
    lowered = unicodedata.normalize("NFC", str(text or "")).casefold()
    return "".join(FOLDED.get(char, char) for char in lowered)


def words_of(text):
    return frozenset(TOKEN.findall(fold(text)))


def header_role(text):
    words = words_of(text)
    if not words:
        return ""
    for role, known in ROLE_WORDS:
        if words & known or any(_compound(word, role) for word in words):
            return role
    return ""


def _compound(word, role):
    return word.startswith(ROLE_PREFIXES.get(role, ())) or word.endswith(ROLE_SUFFIXES.get(role, ()))


def status_of(text):
    words = words_of(text)
    if words & NEGATION_WORDS:
        return _negated_status(words)
    for status, known in STATUS_WORDS:
        if words & known:
            return status
    return ""


def _negated_status(words):
    if words & PENDING_WORDS:
        return STATUS_OPEN
    if words & dict(STATUS_WORDS)[STATUS_ACCEPTED]:
        return STATUS_REJECTED
    return ""


def list_table(html):
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.find("table", id=LIST_TABLE_ID)


def older_list_present(html):
    return list_table(html) is not None


def _span(cell):
    try:
        return max(1, min(int(str(cell.get("colspan") or "1").strip()), 50))
    except ValueError:
        return 1


def _text(cell):
    return " ".join(cell.get_text(" ").split()) if cell is not None else ""


def _expanded(cells):
    expanded = []
    for cell in cells:
        expanded.extend([cell] * _span(cell))
    return expanded


def _header_cells(table):
    head = table.find("thead")
    rows = head.find_all("tr") if head is not None else []
    rows = rows or [row for row in table.find_all("tr") if row.find("th") is not None][:1]
    if not rows:
        return []
    return _expanded(rows[-1].find_all(("th", "td"), recursive=False))


def column_roles(table):
    roles = {}
    for index, cell in enumerate(_header_cells(table)):
        role = header_role(_text(cell))
        if role and role not in roles:
            roles[role] = index
    return roles


def _data_rows(table):
    body = table.find_all("tbody")
    rows = [row for part in body for row in part.find_all("tr")] if body else table.find_all("tr")
    return [row for row in rows if row.find("td") is not None and row.find_parent("thead") is None]


def _empty_row(row, width):
    classes = {str(name) for name in row.get("class") or []}
    cells = row.find_all(("td", "th"), recursive=False)
    if classes & EMPTY_ROW_CLASSES:
        return True
    if any({str(name) for name in cell.get("class") or []} & EMPTY_ROW_CLASSES for cell in cells):
        return True
    if len(cells) == 1 and (width > 1 or _span(cells[0]) > 1):
        return True
    return not any(_text(cell) for cell in cells) and row.find("input") is None


def _calendar_day(year, month, day):
    year = int(year)
    if year < 100:
        year += 2000
    try:
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        return ""


def dates_in(text):
    found = []
    for match in sorted(list(GERMAN_DATE.finditer(text)) + list(ISO_DATE.finditer(text)), key=lambda item: item.start()):
        if match.re is GERMAN_DATE:
            day, month, year = match.groups()
        else:
            year, month, day = match.groups()
        value = _calendar_day(year, month, day)
        if value:
            found.append(value)
    return found


def times_in(text):
    found = []
    for hour, minute in CLOCK.findall(text):
        if int(hour) < 24 and int(minute) < 60:
            found.append("%02d:%s" % (int(hour), minute))
    return found


def _cell(cells, roles, role):
    index = roles.get(role)
    if index is None or index >= len(cells):
        return None
    return cells[index]


def _entry_id(row):
    for field_node in row.find_all("input"):
        if str(field_node.get("type") or "").lower() == "checkbox":
            value = str(field_node.get("value") or "").strip()
            if value and value.lower() != "on" and len(value) <= 64:
                return value
    for anchor in row.find_all("a", href=True):
        match = ID_SEGMENT.search(str(anchor.get("href") or ""))
        if match:
            return match.group(1)
    return ""


def action_paths(row, segments):
    found = []
    for anchor in row.find_all("a", href=True):
        path = urlsplit(str(anchor.get("href") or "").strip()).path
        parts = [part.casefold() for part in path.split("/") if part]
        if path.startswith(LIST_PATH) and set(parts) & segments and any(part.isdigit() for part in parts):
            found.append(path)
    return found


def _delete_path(row, entry_id):
    for path in action_paths(row, DELETE_SEGMENTS):
        if entry_id and entry_id in path.split("/"):
            return path
    return ""


def _detail_path(row, entry_id):
    if not entry_id:
        return ""
    shapes = {(entry_id,), (entry_id, "show"), (entry_id, "view"), (entry_id, "detail"), ("show", entry_id), ("view", entry_id), ("detail", entry_id)}
    for anchor in row.find_all("a", href=True):
        path = urlsplit(str(anchor.get("href") or "").strip()).path
        parts = tuple(part.casefold() if not part.isdigit() else part for part in path[len(LIST_PATH):].split("/") if part)
        if path.startswith(LIST_PATH) and parts in shapes:
            return path
    return ""


def _range(cells, roles):
    span_cell = _cell(cells, roles, ROLE_PERIOD)
    from_cell = _cell(cells, roles, ROLE_FROM)
    till_cell = _cell(cells, roles, ROLE_TILL)
    if from_cell is not None:
        starts = dates_in(_text(from_cell))
        ends = dates_in(_text(till_cell)) if till_cell is not None else []
        start_times = times_in(_text(from_cell))
        end_times = times_in(_text(till_cell)) if till_cell is not None else []
        first = starts[0] if starts else ""
        last = ends[-1] if ends else (starts[-1] if starts else "")
        return first, last, start_times[0] if start_times else "", end_times[-1] if end_times else ""
    text = _text(span_cell)
    days = dates_in(text)
    clocks = times_in(text)
    first = days[0] if days else ""
    last = days[-1] if days else ""
    return first, last, clocks[0] if clocks else "", clocks[-1] if len(clocks) > 1 else ""


def _row(row, roles):
    cells = _expanded(row.find_all(("td", "th"), recursive=False))
    name = _text(_cell(cells, roles, ROLE_NAME))
    first, last, start_time, end_time = _range(cells, roles)
    if not name or not first:
        return None
    if last < first:
        last = first
    created = dates_in(_text(_cell(cells, roles, ROLE_CREATED)))
    entry_id = _entry_id(row)
    return OlderAbsenceRow(
        name=name,
        from_date=first,
        till_date=last,
        from_time=start_time,
        till_time=end_time,
        status=status_of(_text(_cell(cells, roles, ROLE_STATUS))),
        class_text=_text(_cell(cells, roles, ROLE_CLASS)),
        created=created[0] if created else "",
        reason=_text(_cell(cells, roles, ROLE_REASON)),
        entry_id=entry_id,
        delete_path=_delete_path(row, entry_id),
        detail_path=_detail_path(row, entry_id),
    )


def _filter_form(soup):
    best = None
    best_count = 0
    for form in soup.find_all("form"):
        if str(form.get("method") or "get").strip().lower() != "get":
            continue
        count = sum(1 for node in form.find_all(("input", "select")) if str(node.get("name") or "").startswith(FILTER_PREFIX))
        if count > best_count:
            best, best_count = form, count
    return best


def _form_targets_list(form, page_path):
    action = str(form.get("action") or "").strip()
    if not action or action == "#":
        return True
    return urlsplit(action).path.rstrip("/") == page_path.rstrip("/")


def _option_value(option):
    value = option.get("value")
    return str(value if value is not None else option.get_text(" ")).strip()


def _select_pairs(name, select):
    options = select.find_all("option")
    if select.has_attr("multiple") or name.endswith("[]"):
        return [(name, value) for value in (_option_value(option) for option in options) if value]
    chosen = next((option for option in options if option.has_attr("selected")), options[0] if options else None)
    return [(name, _option_value(chosen))] if chosen is not None else []


def _bound_name(name):
    return words_of(name.replace("[", " ").replace("]", " ")) & UPPER_BOUND_WORDS


def _date_value(node, name, today):
    if _bound_name(name):
        return str(node.get("max") or "").strip() or (today + timedelta(days=LATEST_DAYS_AHEAD)).isoformat()
    return str(node.get("min") or "").strip() or EARLIEST_DAY.isoformat()


def filter_query(html, page_path, today):
    soup = BeautifulSoup(html or "", "html.parser")
    form = _filter_form(soup)
    if form is None or not _form_targets_list(form, page_path):
        return []
    pairs = []
    for node in form.find_all(("input", "select", "textarea")):
        name = str(node.get("name") or "").strip()
        if not name:
            continue
        if node.name == "select":
            pairs.extend(_select_pairs(name, node))
            continue
        if node.name == "textarea":
            pairs.append((name, node.get_text()))
            continue
        kind = str(node.get("type") or "text").strip().lower()
        if kind in SKIPPED_INPUT_TYPES:
            continue
        if kind in ("checkbox", "radio"):
            if node.has_attr("checked"):
                pairs.append((name, str(node.get("value") or "on")))
            continue
        if kind == "date" and name.startswith(FILTER_PREFIX):
            pairs.append((name, _date_value(node, name, today)))
            continue
        pairs.append((name, str(node.get("value") or "")))
    return pairs


def row_key(row):
    if row.entry_id:
        return ("id", row.entry_id)
    return (
        "row", row.name, row.from_date, row.till_date, row.from_time, row.till_time,
        row.status, row.class_text, row.created, row.reason,
    )


def merged_rows(first, second):
    rows = list(first.rows)
    listed = Counter(row_key(row) for row in rows)
    taken = Counter()
    for row in second.rows:
        key = row_key(row)
        taken[key] += 1
        if taken[key] > listed[key]:
            rows.append(row)
    return OlderAbsenceList(roles=first.roles or second.roles, rows=rows, unreadable=max(first.unreadable, second.unreadable))


def parse_older_absences(html):
    table = list_table(html)
    if table is None:
        raise OlderAbsenceShapeError("the older absence list is missing")
    roles = column_roles(table)
    width = len(_header_cells(table))
    rows = [row for row in _data_rows(table) if not _empty_row(row, width)]
    result = OlderAbsenceList(roles=roles)
    if not rows:
        return result
    if ROLE_NAME not in roles or not ({ROLE_PERIOD, ROLE_FROM} & set(roles)):
        raise OlderAbsenceShapeError("the older absence list has no name or date column")
    for row in rows:
        parsed = _row(row, roles)
        if parsed is None:
            result.unreadable += 1
        else:
            result.rows.append(parsed)
    if not result.rows:
        raise OlderAbsenceShapeError("no row of the older absence list could be read")
    return result
