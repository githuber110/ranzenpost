from html import escape as escape_html
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .forms import affirmative_submit, parse_forms
from .html import clean_html

LIST_TABLE_ID = "crud-table"
MULTI_FIELD = "iserv_crud_multi_select[multi][]"
UNREAD_CLASS = "parent-index-table-unread"
TOKEN_FIELD = "iserv_crud_multi_select[_token]"
ACTION_FIELD_MARKER = "[actions]["
ARCHIVE_ACTION = "iserv_crud_multi_select[actions][parent-archive-letter]"
RESTORE_ACTION = "iserv_crud_multi_select[actions][parent-restore-letter]"
SHOW_LINK_RE = re.compile(r"/parentletter/parent/show/([^/?#]+)/([^/?#]+)")
MORE_SENDERS_RE = re.compile(r"^\+\s*\d+\s*weitere\b", re.IGNORECASE)
ATTACHMENT_RE = re.compile(r"/parentletter/attachment/([^/?#]+)")
ARCHIVE_RE = re.compile(r"/parentletter/parent/parent_hide/")
CONTENT_SELECTORS = ("div.letter-content", "div.panel-body", "main", "div#content")
CHROME_SELECTORS = ("nav", "header", "footer", ".navbar", ".breadcrumb", ".sidebar")


def parse_letter_list(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=LIST_TABLE_ID)
    letters = []
    if table is None:
        return letters
    body = table.find("tbody") or table
    for row in body.find_all("tr"):
        anchor = None
        match = None
        for candidate in row.find_all("a"):
            match = SHOW_LINK_RE.search(candidate.get("href") or "")
            if match:
                anchor = candidate
                break
        if anchor is None:
            continue
        cells = row.find_all("td")
        checkbox = row.find("input", attrs={"name": MULTI_FIELD})
        multi_value = ""
        if checkbox is not None:
            multi_value = (checkbox.get("value") or "").strip()
        letters.append(
            {
                "letter_id": match.group(1),
                "recipient_id": match.group(2),
                "title": anchor.get_text(strip=True),
                "child": _cell_text(cells, 2),
                "sender": _cell_text(cells, 3),
                "additional_senders": _additional_senders_text(cells),
                "recipients": _cell_text(cells, 5),
                "published": _cell_text(cells, 6),
                "show_url": urljoin(base_url, anchor.get("href")),
                "multi_value": multi_value,
                "unread": _is_unread(row),
            }
        )
    return letters


def _is_unread(row):
    if _has_unread_class(row):
        return True
    for element in row.find_all(True):
        if _has_unread_class(element):
            return True
    return False


def _has_unread_class(element):
    classes = element.get("class") or []
    if isinstance(classes, str):
        classes = classes.split()
    return any(UNREAD_CLASS in str(name) for name in classes)


def parse_letter_detail(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.find_all(["script", "style"]):
        element.decompose()
    for selector in CHROME_SELECTORS:
        for element in soup.select(selector):
            element.decompose()
    title = ""
    heading = soup.find("h1")
    if heading is not None:
        title = heading.get_text(strip=True)
    elif soup.title is not None:
        title = soup.title.get_text(strip=True)
    attachments = []
    for anchor in soup.find_all("a"):
        href = anchor.get("href") or ""
        match = ATTACHMENT_RE.search(href)
        if match:
            attachments.append(
                {
                    "url": urljoin(base_url, href),
                    "attachment_id": match.group(1),
                    "filename": anchor.get_text(strip=True),
                }
            )
    archive_url = ""
    archive_anchor = soup.find("a", href=ARCHIVE_RE)
    if archive_anchor is not None:
        archive_url = urljoin(base_url, archive_anchor.get("href"))
    container = _find_content(soup)
    _drop_attachment_links(container)
    return {
        "title": title,
        "body_html": clean_html(container.decode_contents()),
        "attachments": _unique_attachments(attachments),
        "archive_url": archive_url,
    }


def _drop_attachment_links(container):
    for anchor in container.find_all("a"):
        if not ATTACHMENT_RE.search(anchor.get("href") or ""):
            continue
        holder = anchor
        for _ in range(3):
            parent = holder.parent
            if parent is None or parent is container:
                break
            if len(parent.find_all("a")) > 1 or parent.get_text(strip=True) != holder.get_text(strip=True):
                break
            holder = parent
        holder.decompose()


def _unique_attachments(attachments):
    seen = set()
    result = []
    for entry in attachments:
        key = entry.get("attachment_id")
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def parse_archive_form(html, base_url, action=None):
    for form in parse_forms(html, base_url):
        token = form.fields.get(TOKEN_FIELD)
        if token is None:
            continue
        submits = dict(getattr(form, "submits", None) or {})
        action_field = _select_action(form, submits, action)
        if action_field is None:
            continue
        return {
            "action": form.action,
            "token": token,
            "action_field": action_field,
            "submits": submits,
        }
    return None


def build_archive_payload(form, multi_values, action=None):
    selected = action or form["action_field"]
    return {
        MULTI_FIELD: list(multi_values),
        selected: _action_value(form, action),
        TOKEN_FIELD: form["token"],
    }


def _select_action(form, submits, action):
    if action is None:
        return next((name for name in form.fields if ACTION_FIELD_MARKER in name), None)
    if action in form.fields or action in submits:
        return action
    return None


def _action_value(form, action):
    if action is None:
        return ""
    submits = form.get("submits") or {}
    if action not in submits:
        return ""
    return affirmative_submit({action: submits[action]}).get(action, "")


def _cell_text(cells, index):
    if index >= len(cells):
        return ""
    return cells[index].get_text(strip=True)


def _additional_senders_text(cells):
    if 4 >= len(cells):
        return ""
    cell = cells[4]
    children = cell.find_all(True, recursive=False)
    if not children:
        return cell.get_text(strip=True)
    names = []
    for child in children:
        text = child.get_text(strip=True)
        if not text or MORE_SENDERS_RE.match(text):
            continue
        title = (child.get("title") or child.get("data-original-title") or "").strip()
        for name in (title.split(",") if title else [text]):
            name = name.strip()
            if name and name not in names:
                names.append(name)
    if not names:
        return cell.get_text(strip=True)
    return ", ".join(names)


def _find_content(soup):
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            return node
    best = None
    best_length = -1
    for div in soup.find_all("div"):
        length = len(div.get_text(strip=True))
        if length > best_length:
            best = div
            best_length = length
    if best is not None:
        return best
    return soup.body or soup


HIDE_TOKEN = "hide_confirm[_token]"


def parse_hide_confirm(html, base_url):
    for form in parse_forms(html, base_url):
        if HIDE_TOKEN in form.fields:
            return form
    return None


def build_hide_payload(form):
    payload = dict(form.fields)
    payload.update(affirmative_submit(getattr(form, "submits", {}) or {}))
    return payload


CONFIRMATION_ATTR = "confirmation-type"
CONFIRMATION_NONE = "none"
CONFIRMATION_SEEN = "seen"
CONFIRMATION_CHOICE = "confirmation"
SENDABLE_CONFIRMATIONS = (CONFIRMATION_SEEN,)


EDITOR_TAG = "iserv-editor"
EDITOR_MODES = ("rich", "plain")
EMPTY_EDITOR_HTML = "<p></p>"


def _form_custom_fields(form):
    prefix = f"{form.get('name') or 'form'}["
    found = []
    for control in form.find_all(True):
        if "-" not in control.name:
            continue
        name = control.get("name") or ""
        if name.startswith(prefix):
            found.append((control, name))
    return found


def _editor_mode(control):
    chosen = (control.get("initial-mode") or "").strip()
    if chosen:
        return chosen
    raw = control.get("config") or ""
    try:
        config = json.loads(raw) if raw else {}
    except ValueError:
        config = {}
    if isinstance(config, dict):
        for mode in EDITOR_MODES:
            if config.get(mode):
                return mode
    return EDITOR_MODES[0]


def _plain_to_html(text):
    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    body = "".join(f"<p>{escape_html(line)}</p>" for line in lines if line != "")
    return body or EMPTY_EDITOR_HTML


def _editor_fields(control, name):
    mode = _editor_mode(control)
    initial = control.get("initial-content") or ""
    if mode == "rich" and initial.strip():
        html_value = initial
        plain_value = BeautifulSoup(initial, "html.parser").get_text("\n").strip()
    else:
        plain_value = initial if mode == "plain" else ""
        html_value = _plain_to_html(plain_value)
    return {f"{name}[html]": html_value, f"{name}[plain]": plain_value, f"{name}[mode]": mode}


def parse_confirmation(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    button = soup.find(attrs={CONFIRMATION_ATTR: True})
    if button is None:
        return None
    kind = (button.get(CONFIRMATION_ATTR) or "").strip().lower()
    if not kind or kind == CONFIRMATION_NONE:
        return None
    form = button.find_parent("form")
    if form is None:
        return None
    fields = {}
    submits = {}
    text_field = ""
    for control in form.find_all(["input", "textarea", "select"]):
        name = control.get("name")
        if not name:
            continue
        if control.name == "textarea":
            text_field = name
            fields[name] = control.get_text() or ""
            continue
        if control.name == "input" and (control.get("type") or "text").lower() == "submit":
            submits[name] = control.get("value") or ""
            continue
        fields[name] = control.get("value") or ""
    for control in form.find_all("button"):
        name = control.get("name")
        if not name or (control.get("type") or "submit").lower() != "submit":
            continue
        submits[name] = control.get("value") or ""
    editor = ""
    for control, name in _form_custom_fields(form):
        if control.name == EDITOR_TAG:
            editor = editor or name
            fields.update(_editor_fields(control, name))
    return {
        "editor": editor,
        "type": kind,
        "action": urljoin(base_url, button.get("formaction") or form.get("action") or base_url),
        "fields": fields,
        "submits": submits,
        "text_field": text_field,
        "text": fields.get(text_field, "") if text_field else "",
        "sendable": kind in SENDABLE_CONFIRMATIONS and len(submits) == 1,
    }


def build_confirmation_payload(confirmation, text=None):
    payload = dict(confirmation.get("fields") or {})
    field = confirmation.get("text_field") or ""
    if field and text is not None:
        payload[field] = text
    editor = confirmation.get("editor") or ""
    if editor and not field and text is not None:
        payload[f"{editor}[plain]"] = text
        payload[f"{editor}[html]"] = _plain_to_html(text)
    submits = dict(confirmation.get("submits") or {})
    name = next(iter(submits), "")
    if name:
        payload[name] = submits[name]
    return payload


NOTICE_SELECTORS = (".alert", ".form-error-message", ".invalid-feedback", ".help-block", ".error")
NOTICE_LIMIT = 3
NOTICE_LENGTH = 80
BUTTON_TEXT_LENGTH = 40
LETTER_BODY_CLASS = "parent-letter-body"


def _short(text, limit):
    return " ".join(str(text or "").split())[:limit]


def page_notices(html):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for selector in NOTICE_SELECTORS:
        for node in soup.select(selector):
            if node.find_parent(class_=LETTER_BODY_CLASS) is not None:
                continue
            text = _short(node.get_text(" "), NOTICE_LENGTH)
            if text and text not in found:
                found.append(text)
            if len(found) >= NOTICE_LIMIT:
                return found
    return found


def _field_label(control):
    marks = []
    if control.name in ("textarea", "select"):
        marks.append(control.name)
    else:
        kind = (control.get("type") or "text").lower()
        if kind not in ("hidden", "text"):
            marks.append(kind)
    for flag in ("required", "disabled"):
        if control.has_attr(flag):
            marks.append(flag)
    name = control.get("name") or ""
    return f"{name} ({', '.join(marks)})" if marks else name


def _is_named_submit(control):
    if not control.get("name"):
        return False
    if control.name == "button":
        return (control.get("type") or "submit").lower() == "submit"
    return control.name == "input" and (control.get("type") or "text").lower() == "submit"


OUTLINE_VALUE_ATTRIBUTES = (
    "type",
    "name",
    "id",
    "role",
    "method",
    "action",
    "enctype",
    "formaction",
    "formmethod",
    "formenctype",
    "target",
    "class",
    CONFIRMATION_ATTR,
)
OUTLINE_LENGTH = 1200
OUTLINE_VALUE_LENGTH = 60
OUTLINE_PATH_LENGTH = 160
SCRIPT_LIMIT = 12


def _path_only(value):
    parsed = urlparse(str(value or ""))
    if parsed.scheme or parsed.netloc or parsed.query:
        return parsed.path
    return str(value or "")


def _outline_node(node):
    parts = []
    for name, value in node.attrs.items():
        if name == "value":
            continue
        text = " ".join(value) if isinstance(value, list) else str(value or "")
        if name in OUTLINE_VALUE_ATTRIBUTES or name.startswith("data-"):
            if "/" in text or "?" in text:
                text = _short(_path_only(text), OUTLINE_PATH_LENGTH)
            else:
                text = _short(text, OUTLINE_VALUE_LENGTH)
            parts.append(f"{name}={text}" if text else name)
        else:
            parts.append(name)
    label = node.name + (f"[{', '.join(parts)}]" if parts else "")
    if node.name == "button":
        label += f" '{_short(node.get_text(' '), BUTTON_TEXT_LENGTH)}'"
    return label


def _form_outline(form):
    nodes = [form] + list(form.find_all(True))
    return " | ".join(_outline_node(node) for node in nodes)[:OUTLINE_LENGTH]


def _script_sources(soup):
    found = []
    for node in soup.find_all("script", src=True):
        path = urlparse(node.get("src") or "").path
        if path and path not in found:
            found.append(path)
        if len(found) >= SCRIPT_LIMIT:
            break
    return found


def confirmation_evidence(html):
    soup = BeautifulSoup(html or "", "html.parser")
    marked = soup.find_all(attrs={CONFIRMATION_ATTR: True})
    if not marked:
        return None
    first = marked[0]
    form = first.find_parent("form")
    fields = []
    submits = 0
    controls = form.find_all(["input", "textarea", "select", "button"]) if form is not None else []
    for control in controls:
        if _is_named_submit(control):
            submits += 1
        elif control.name != "button" and control.get("name"):
            fields.append(_field_label(control))
    if form is not None:
        for control, name in _form_custom_fields(form):
            fields.append(f"{name} ({control.name})")
    classes = first.get("class") or []
    return {
        "confirmation_marks": [str(node.get(CONFIRMATION_ATTR) or "").strip() for node in marked],
        "confirmation_disabled": first.has_attr("disabled") or "disabled" in classes,
        "confirmation_button": _short(first.get_text(" "), BUTTON_TEXT_LENGTH),
        "confirmation_fields": fields,
        "confirmation_submits": submits,
        "page_notices": page_notices(html),
        "confirmation_target": _path_only(first.get("formaction") or (form.get("action") if form is not None else "")),
        "confirmation_button_attributes": sorted(first.attrs.keys()),
        "confirmation_form": _form_outline(form) if form is not None else "",
        "script_sources": _script_sources(soup),
    }


CONFIRM_FIELD = "iserv_crud_multi_select[confirm]"


def parse_batch_confirm(html, base_url):
    for form in parse_forms(html, base_url):
        if MULTI_FIELD in form.fields or CONFIRM_FIELD in form.fields:
            names = set(form.fields) | set(getattr(form, "submits", None) or {})
            if any(ACTION_FIELD_MARKER in name for name in names):
                return form
    return None


def build_batch_confirm_payload(form, action):
    payload = {name: value for name, value in form.fields.items() if ACTION_FIELD_MARKER not in name}
    payload.setdefault(CONFIRM_FIELD, "1")
    submits = dict(getattr(form, "submits", None) or {})
    if action in submits or action in form.fields:
        payload[action] = submits.get(action, form.fields.get(action, ""))
    else:
        payload.update(affirmative_submit(submits))
    return payload
