import re
from urllib.parse import urljoin

from .exercises import header_labels, parse_moment
from .pages import path_of, squeezed

TEXT_LIMIT = 300
WORDS = re.compile(r"[^\W\d_]+")
SORT_ATTRIBUTES = ("data-sort", "data-order", "data-value", "datetime", "title")
ADDRESS = re.compile(r"^[^@\s<>\"]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z0-9-]{2,63}$")
ADDRESS_IN_TEXT = re.compile(r"[^@\s<>\"(),;:]{1,64}@[A-Za-z0-9.-]{1,253}\.[A-Za-z]{2,63}")
MAILTO = "mailto:"


def _span(cell):
    try:
        return max(1, int(cell.get("colspan") or 1))
    except (TypeError, ValueError):
        return 1


def _key(text):
    return " ".join(WORDS.findall(str(text or "").casefold()))


def column_map(labels, columns):
    mapping = {}
    taken = set()
    for index, label in enumerate(labels):
        key = _key(label)
        if not key:
            continue
        for field, words in columns.items():
            if field in taken:
                continue
            if key in words or any(_key(word) and (" " + _key(word) + " ") in (" " + key + " ") for word in words):
                mapping[index] = field
                taken.add(field)
                break
    return mapping


def row_cells(row):
    cells = []
    for cell in row.find_all(["td", "th"], recursive=False):
        cells.extend([cell] + [None] * (_span(cell) - 1))
    return cells


def body_rows(table):
    head = table.find("thead")
    header = head.find("tr") if head is not None else None
    body = table.find("tbody")
    rows = body.find_all("tr", recursive=False) if body is not None else table.find_all("tr")
    found = []
    for row in rows:
        if row is header or row.find_parent("thead") is not None:
            continue
        if row.find("td") is None:
            continue
        found.append(row)
    return found


def mapped_rows(table, columns):
    labels = header_labels(table)
    mapping = column_map(labels, columns)
    rows = []
    for row in body_rows(table):
        cells = row_cells(row)
        fields = {}
        extra = []
        for index, cell in enumerate(cells):
            if cell is None:
                continue
            field = mapping.get(index)
            if field is not None:
                fields[field] = cell
                continue
            text = squeezed(cell.get_text(" "), TEXT_LIMIT)
            label = labels[index] if index < len(labels) else ""
            if text and label:
                extra.append({"label": squeezed(label, 80), "value": text})
        rows.append((row, fields, extra))
    return labels, mapping, rows


def cell_text(cell, limit=TEXT_LIMIT):
    return squeezed(cell.get_text(" "), limit) if cell is not None else ""


def cell_moment(cell):
    if cell is None:
        return ""
    for name in SORT_ATTRIBUTES:
        for holder in [cell] + cell.find_all(True):
            value = holder.get(name)
            found = parse_moment(value) if value else ""
            if found:
                return found
    return parse_moment(cell.get_text(" "))


def row_classes(node):
    names = []
    for holder in [node] + node.find_all(True):
        names.extend(str(name).lower() for name in holder.get("class") or [])
    return names


def addresses_in(node):
    found = []
    for anchor in node.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if href.lower().startswith(MAILTO):
            address = href[len(MAILTO):].split("?", 1)[0].strip()
            if ADDRESS.match(address) and address.lower() not in [entry.lower() for entry in found]:
                found.append(address)
    for match in ADDRESS_IN_TEXT.findall(node.get_text(" ")):
        address = match.strip(".")
        if ADDRESS.match(address) and address.lower() not in [entry.lower() for entry in found]:
            found.append(address)
    return found


def form_by(soup, test):
    for form in soup.find_all("form"):
        if test(form):
            return form
    return None


def form_action(form, page_url):
    return urljoin(page_url, form.get("action") or page_url)


def form_action_path(form, page_url):
    return path_of(form_action(form, page_url))


def associated_controls(soup, form):
    controls = list(form.find_all(["input", "select", "textarea", "button"]))
    ident = form.get("id")
    if ident:
        for control in soup.find_all(["input", "select", "textarea", "button"], attrs={"form": ident}):
            if control not in controls:
                controls.append(control)
    return controls


def hidden_pairs(controls):
    return [
        (str(control.get("name")), str(control.get("value") or ""))
        for control in controls
        if control.name == "input" and str(control.get("type") or "").lower() == "hidden" and control.get("name")
    ]


def submit_buttons(controls):
    found = []
    for control in controls:
        kind = str(control.get("type") or ("submit" if control.name == "button" else "text")).lower()
        if kind == "submit" and control.get("name"):
            found.append((str(control.get("name")), str(control.get("value") or "")))
    return found


def control_label(soup, form, control):
    ident = control.get("id")
    if ident:
        label = form.find("label", attrs={"for": ident}) or soup.find("label", attrs={"for": ident})
        if label is not None and squeezed(label.get_text(" "), 160):
            return squeezed(label.get_text(" "), 160)
    parent = control.find_parent("label")
    if parent is not None and squeezed(parent.get_text(" "), 160):
        return squeezed(parent.get_text(" "), 160)
    for attribute in ("aria-label", "placeholder", "title"):
        if control.get(attribute):
            return squeezed(control.get(attribute), 160)
    return ""
