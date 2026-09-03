import re
from urllib.parse import urljoin

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
    return {
        "type": kind,
        "action": urljoin(base_url, form.get("action") or base_url),
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
    submits = dict(confirmation.get("submits") or {})
    name = next(iter(submits), "")
    if name:
        payload[name] = submits[name]
    return payload


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
