import json
import re

from bs4 import BeautifulSoup

from . import modules, valueshape
from .pathpattern import path_only, placeholders
from .vocabulary import TOKEN, known_word

LANDMARK_TAGS = ("header", "nav", "main", "section", "article", "aside", "footer", "form", "table", "iframe", "dialog")
FIELD_TAGS = ("input", "select", "textarea", "button")
MAX_LANDMARKS = 80
MAX_LINKS = 200
MAX_ENDPOINTS = 120
MAX_HEADERS = 60
MAX_TABLE_ROWS_LINES = 20
HEADER_CHARS = 40
SCRIPT_PATH = re.compile(r"[\"'](/(?:iserv|_matrix)/[^\"'\s<>]*)[\"']")
JSON_SCRIPT_TYPES = ("application/json", "application/ld+json")
DIGIT_RUN = re.compile(r"\d+")
CARD_CLASS = "card"


def code_text(text):
    return valueshape.identifier_shape(text)


def visible_text(text):
    def keep(match):
        token = match.group(0)
        return token if token.isdigit() or known_word(token) else valueshape.WORD_MARK

    return TOKEN.sub(keep, placeholders(str(text or "")))


def _selector(node):
    label = node.name
    if node.get("id"):
        label += "#" + code_text(placeholders(str(node.get("id"))))
    classes = [code_text(placeholders(cls)) for cls in (node.get("class") or [])[:2]]
    if classes:
        label += "." + ".".join(classes)
    return label


def label_shape(text):
    return DIGIT_RUN.sub("<n>", visible_text(" ".join(str(text or "").split())))[:HEADER_CHARS]


def _field_label(field):
    if field.name == "button" or str(field.get("type") or "").lower() in ("submit", "button"):
        return label_shape(field.get_text(" ") if field.name == "button" else field.get("value"))
    soup = field.find_parent("form") or field
    node = soup.find("label", attrs={"for": field.get("id")}) if field.get("id") else None
    node = node or field.find_parent("label")
    return label_shape(node.get_text(" ")) if node is not None else ""


def _field_line(field):
    name = str(field.get("name") or "").strip()
    if not name:
        return ""
    kind = field.name if field.name != "input" else str(field.get("type") or "text").lower()
    facts = [kind]
    if field.has_attr("required"):
        facts.append("required")
    if field.name == "select":
        facts.append("options %d" % len(field.find_all("option")))
    label = _field_label(field)
    if label:
        facts.append("label '%s'" % label)
    return "  - %s (%s)" % (code_text(placeholders(name)), ", ".join(facts))


def _button_entry(field):
    if field.name == "input" and str(field.get("type") or "").lower() not in ("submit", "button", "image"):
        return ""
    name = code_text(placeholders(str(field.get("name") or "").strip())) or "-"
    return "%s '%s'" % (name, _field_label(field) or "-")


def _cards(soup):
    count = 0
    for node in soup.find_all(True):
        parts = {part.casefold() for value in node.get("class") or [] for part in re.split(r"[-_]", str(value)) if part}
        if CARD_CLASS in parts:
            count += 1
    return count


def page_extras(soup):
    lines = []
    if soup.title is not None:
        lines.append("- Title: %s" % (label_shape(soup.title.get_text(" ")) or "-"))
    buttons = unique((_button_entry(field) for field in soup.find_all(("button", "input"))), MAX_HEADERS)
    if buttons:
        lines.append("- Buttons: " + " | ".join(buttons))
    lists = soup.find_all(("ul", "ol"))
    cards = _cards(soup)
    if lists or cards:
        lines.append("- Lists: %d with %d items, cards: %d" % (len(lists), sum(len(node.find_all("li", recursive=False)) for node in lists), cards))
    return lines


def unique(values, limit):
    seen = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return seen


def html_skeleton(html, link_shape=None):
    link_shape = link_shape or valueshape.link_shape
    soup = BeautifulSoup(html or "", "html.parser")
    lines = []
    lines.extend(page_extras(soup))
    landmarks = unique((_selector(node) for node in soup.find_all(LANDMARK_TAGS)), MAX_LANDMARKS)
    if landmarks:
        lines.append("- Landmarks: " + " | ".join(landmarks))
    for form in soup.find_all("form"):
        head = "- Form: %s (%s)" % (link_shape(form.get("action") or "") or "-", str(form.get("method") or "get").lower())
        if form.get("id"):
            head += " #" + code_text(placeholders(str(form.get("id"))))
        lines.append(head)
        lines.extend(unique((_field_line(field) for field in form.find_all(FIELD_TAGS)), MAX_HEADERS))
    tables = soup.find_all("table")
    for index, table in enumerate(tables):
        heads = unique(
            (visible_text(" ".join(th.get_text(" ").split()))[:HEADER_CHARS] for th in table.find_all("th")),
            MAX_HEADERS,
        )
        if heads:
            lines.append("- Table headers: " + " | ".join(heads))
        if index < MAX_TABLE_ROWS_LINES:
            lines.append(table_rows(table))
    if len(tables) > MAX_TABLE_ROWS_LINES:
        lines.append("- Table rows skipped: %d beyond the limit of %d" % (len(tables) - MAX_TABLE_ROWS_LINES, MAX_TABLE_ROWS_LINES))
    links = unique(
        (link_shape(anchor.get("href")) for anchor in soup.find_all("a", href=True) if path_only(anchor.get("href")).startswith("/")),
        MAX_LINKS,
    )
    if links:
        lines.append("- Links: " + " | ".join(links))
    endpoints = []
    for script in soup.find_all("script"):
        endpoints.extend(link_shape(match) for match in SCRIPT_PATH.findall(script.get_text() or ""))
    endpoints = unique(endpoints, MAX_ENDPOINTS)
    if endpoints:
        lines.append("- Endpoints: " + " | ".join(endpoints))
    lines.extend(embedded_json(soup))
    return lines


def table_rows(table):
    rows = table.find_all("tr")
    shapes = {}
    for row in rows:
        cells = len(row.find_all(("td", "th"), recursive=False))
        shapes[cells] = shapes.get(cells, 0) + 1
    label = "#" + code_text(placeholders(str(table.get("id")))) if table.get("id") else "(no id)"
    parts = ", ".join("%d cells x%d" % (cells, count) for cells, count in sorted(shapes.items()))
    return "- Table rows %s: %d%s" % (label, len(rows), " (" + parts + ")" if parts else "")


def json_script(tag):
    kind = str(tag.get("type") or "").split(";", 1)[0].strip().lower()
    return kind in JSON_SCRIPT_TYPES


def embedded_json(soup):
    lines = []
    for tag in soup.find_all("script"):
        if not json_script(tag):
            continue
        label = "#" + code_text(placeholders(str(tag.get("id")))) if tag.get("id") else "(no id)"
        try:
            data = json.loads(tag.get_text() or "")
        except ValueError:
            lines.append("- Embedded JSON %s: unreadable" % label)
            continue
        lines.append("- Embedded JSON %s:" % label)
        lines.extend(shape_block(data))
    return lines


def shape_block(data):
    shapes = valueshape.shape_lines(data)
    lines = ["  - " + line for line in shapes]
    if len(shapes) >= valueshape.MAX_LINES:
        lines.append("  - cut after %d keys" % valueshape.MAX_LINES)
    return lines


def json_skeleton(payload):
    return ["- JSON value shapes:"] + shape_block(payload)


def json_of(response):
    reader = getattr(response, "json", None)
    if callable(reader):
        return reader()
    return json.loads(getattr(response, "text", "") or "")


def response_skeleton(response, link_shape=None):
    kind = body_kind(response)
    if kind == "json":
        try:
            return json_skeleton(json_of(response))
        except (ValueError, TypeError):
            return ["- JSON: unreadable"]
    if kind == "html":
        return html_skeleton(getattr(response, "text", "") or "", link_shape)
    return ["- Body: %s" % kind]


def body_kind(response):
    content_type = modules.probe_record("", response, "")["content_type"]
    text = getattr(response, "text", "") or ""
    if "json" in content_type or text.lstrip()[:1] in ("{", "["):
        return "json"
    if "html" in content_type or "<" in text[:200]:
        return "html"
    return content_type or "unknown type"


def status_of(response):
    return int(getattr(response, "status_code", 0) or 0)
