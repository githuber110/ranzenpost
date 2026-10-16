import hashlib
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup

from .exercises import note_once, parse_moment
from .pages import path_of, squeezed

TEXTS_PATH = "/iserv/etherpad"
TEXTS_ROOT = TEXTS_PATH + "/"
TEXT_PATH = re.compile(r"^/iserv/etherpad/([^/?#]+)/?$")
RESERVED = frozenset({"add", "new", "create", "confirm", "export", "import", "settings", "help", "batch", "multi"})
JSON_TYPES = ("application/json", "application/ld+json")
FILTER_FIELD = "filter[Default]"
FILTER_FIELD_MARK = re.compile(r"^filter\[default\]$", re.IGNORECASE)
STAMP = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?$")
TITLE_LIMIT = 200
TEXT_LIMIT = 120
TAG_LIMIT = 30
LABEL_LIMIT = 80
CHANGED_KEY = re.compile(r"^last.*at$|^(changed|updated|modified)(at)?$", re.IGNORECASE)
CREATED_KEY = re.compile(r"^created(at)?$", re.IGNORECASE)
OWNER_KEY = re.compile(r"^(owner|author|creator)$", re.IGNORECASE)


class TextShapeError(ValueError):
    pass


def _json_scripts(soup):
    for tag in soup.find_all("script"):
        kind = str(tag.get("type") or "").split(";", 1)[0].strip().lower()
        if kind not in JSON_TYPES:
            continue
        try:
            yield json.loads(tag.get_text() or "")
        except ValueError:
            continue


def _rows_of(soup):
    for data in _json_scripts(soup):
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return [row for row in data["data"] if isinstance(row, dict)]
    return None


def _value(entry):
    return entry.get("value") if isinstance(entry, dict) else entry


def _shown(entry):
    if not isinstance(entry, dict):
        return ""
    for name, value in entry.items():
        if name in ("value", "type") or not isinstance(value, str):
            continue
        text = squeezed(BeautifulSoup(value, "html.parser").get_text(" "), TEXT_LIMIT)
        if text:
            return text
    return ""


def _links(entry):
    if not isinstance(entry, dict):
        return []
    found = []
    for name, value in entry.items():
        if name == "type" or not isinstance(value, str) or "<" not in value:
            continue
        for anchor in BeautifulSoup(value, "html.parser").find_all("a", href=True):
            found.append(path_of(anchor["href"]))
    return found


def _stamp(value):
    text = str(value or "").strip()
    match = STAMP.match(text)
    if match:
        year, month, day, hour, minute, _second = match.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute)).strftime("%Y-%m-%dT%H:%M")
        except ValueError:
            return ""
    return parse_moment(text)


def _tags(entry):
    raw = _value(entry)
    values = raw if isinstance(raw, list) else ([raw] if raw else [])
    tags = []
    for item in values:
        if isinstance(item, dict):
            item = item.get("name") or item.get("title") or item.get("value") or item.get("label") or ""
        text = squeezed(BeautifulSoup(str(item), "html.parser").get_text(" "), LABEL_LIMIT)
        if text and text not in tags:
            tags.append(text)
    return tags[:TAG_LIMIT]


def text_key(path):
    match = TEXT_PATH.match(path_of(path or "").rstrip("/"))
    if not match or match.group(1).lower() in RESERVED:
        return ""
    return match.group(1)


def _selected_value(row):
    raw = row.get("_multi_select")
    if not isinstance(raw, str) or "<" not in raw:
        return ""
    box = BeautifulSoup(raw, "html.parser").find("input")
    return str(box.get("value") or "") if box is not None else ""


def _field(row, pattern):
    for name, entry in row.items():
        if pattern.match(str(name)):
            return entry
    return None


def _text_entry(row):
    title_entry = row.get("title")
    title = squeezed(_value(title_entry), TITLE_LIMIT) if isinstance(_value(title_entry), str) else ""
    title = title or squeezed(_shown(title_entry), TITLE_LIMIT)
    paths = [path for path in _links(title_entry) if text_key(path)]
    path = paths[0].rstrip("/") if paths else ""
    owner_entry = _field(row, OWNER_KEY)
    owner = _value(owner_entry)
    owner = squeezed(owner if isinstance(owner, str) else _shown(owner_entry), LABEL_LIMIT)
    changed_entry = _field(row, CHANGED_KEY)
    created_entry = _field(row, CREATED_KEY)
    key = text_key(path) or _selected_value(row)
    if not key:
        created = str(_value(created_entry) or "")
        parts = (owner, created) if created else (owner, created, title)
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        key = "h" + digest[:16]
    return {
        "id": key,
        "title": title,
        "owner": owner,
        "changed": _stamp(_value(changed_entry)),
        "changed_text": _shown(changed_entry),
        "created": _stamp(_value(created_entry)),
        "created_text": _shown(created_entry),
        "tags": _tags(row.get("tags")),
        "path": path,
    }


def filter_choices(soup):
    for select in soup.find_all("select"):
        if not FILTER_FIELD_MARK.match(str(select.get("name") or "")):
            continue
        choices = []
        for option in select.find_all("option"):
            value = str(option.get("value") if option.get("value") is not None else option.get_text(" ")).strip()
            if not value or any(choice["value"] == value for choice in choices):
                continue
            choices.append({
                "value": value,
                "label": squeezed(option.get_text(" "), LABEL_LIMIT) or value,
                "selected": option.has_attr("selected"),
            })
        if choices and not any(choice["selected"] for choice in choices):
            choices[0]["selected"] = True
        return str(select.get("name")), choices
    return FILTER_FIELD, []


def parse_texts(html, list_path=TEXTS_PATH):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = _rows_of(soup)
    field, choices = filter_choices(soup)
    if rows is None:
        note_once("etherpad", list_path, "no embedded text data")
        raise TextShapeError("text list carries no embedded data")
    texts = []
    seen = set()
    skipped = 0
    for row in rows:
        entry = _text_entry(row)
        if not entry["title"] and not entry["path"]:
            skipped += 1
            continue
        if entry["id"] in seen:
            continue
        seen.add(entry["id"])
        texts.append(entry)
    if skipped and not texts:
        note_once("etherpad", list_path, "%d data rows unreadable, no title or link found" % skipped)
        raise TextShapeError("text data rows carry no readable text")
    if skipped:
        note_once("etherpad", list_path, "skipped %d unreadable data rows" % skipped)
    return {"texts": texts, "filter_field": field, "filters": choices}


def is_text_page(path):
    path = path_of(path or "")
    return path.rstrip("/") == TEXTS_PATH or path.startswith(TEXTS_ROOT)
