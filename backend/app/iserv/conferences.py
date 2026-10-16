import re
from datetime import date
from urllib.parse import parse_qsl, urljoin, urlsplit

from bs4 import BeautifulSoup, NavigableString, Tag

from .html import is_safe_url
from .pages import WRITE_WORDS, action_link

EMPTY_PHRASE = "keine elternsprechtage"
MODULE_PREFIX = "/iserv/parentconference/"
LIST_PATH = "/iserv/parentconference/attendee/"
ARCHIVE_PATH = "/iserv/parentconference/attendee/archive"
TAB_PATHS = frozenset({"/iserv/parentconference/", "/iserv/parentconference", LIST_PATH, LIST_PATH.rstrip("/"), ARCHIVE_PATH})
CONTENT_SELECTORS = ("#content", "main", "[role=main]", ".content", ".page-content", "#main")
SKIPPED_TAGS = frozenset({
    "script", "style", "noscript", "template", "nav", "header", "footer", "aside", "svg", "iframe", "button",
    "select", "input", "textarea", "label", "img", "picture", "video", "audio", "canvas", "object", "embed",
})
SKIPPED_CLASSES = frozenset({
    "navbar", "breadcrumb", "nav-tabs", "nav-pills", "sr-only", "visually-hidden", "d-none", "hidden", "modal",
    "dropdown-menu", "pagination",
})
HEADING_TAGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
BLOCK_TAGS = frozenset({
    "div", "p", "table", "form", "ul", "ol", "dl", "section", "article", "fieldset", "blockquote", "pre",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "main", "header", "footer", "nav", "aside", "details", "figure",
})
BLOCK_CLASSES = frozenset({"card", "panel", "list-group-item", "media", "well", "box"})
NOTICE_TONES = (
    ("danger", "error"), ("error", "error"), ("warning", "warning"), ("success", "success"), ("info", "info"),
)
NOTICE_CLASSES = frozenset({"alert", "flash", "notice", "callout", "message"})
ERROR_CLASSES = frozenset({
    "invalid-feedback", "form-error", "form-errors", "form-error-message", "error-message", "text-danger",
    "field-error", "errorlist",
})
ERROR_CONTAINERS = frozenset({"has-error", "is-invalid"})
FIELD_GROUP_CLASSES = frozenset({"form-group", "mb-3", "form-row", "field", "form-field", "row"})
DESTRUCTIVE_WORDS = frozenset({
    "delete", "remove", "cancel", "storno", "unbook", "löschen", "loeschen", "entfernen", "absagen", "stornieren",
    "austragen",
})
TEXT_INPUT_KINDS = frozenset({
    "text", "email", "tel", "number", "date", "time", "datetime-local", "month", "week", "url", "search", "color",
    "range",
})
IGNORED_INPUT_KINDS = frozenset({"reset", "button", "image", "submit", "password"})
UNSAFE_PATH = re.compile(r"%2e|%2f|%5c|\\", re.IGNORECASE)
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
SECRET_FIELD_WORDS = ("token", "csrf", "nonce")
CELL_EXCLUDED_TAGS = frozenset({"form", "button", "script", "style", "select", "option", "template", "noscript"})
MAX_TEXT = 2000
MAX_CELL = 400
MAX_BLOCKS = 400
MAX_OPTIONS = 500
SPACE = re.compile(r"\s+")


def _clean(value, limit=MAX_TEXT):
    return SPACE.sub(" ", str(value or "")).strip()[:limit]


def _class_tokens(node):
    tokens = set()
    for value in node.get("class") or []:
        lowered = str(value).lower()
        tokens.add(lowered)
        tokens.update(part for part in re.split(r"[-_]", lowered) if part)
    return tokens


def _classes(node):
    return {str(value).lower() for value in node.get("class") or []}


def module_path(href, base_url):
    if not isinstance(href, str):
        return None
    raw = href.strip()
    if not raw or raw.startswith("#") or UNSAFE_PATH.search(raw):
        return None
    if SCHEME.match(raw) and not raw.lower().startswith(("http://", "https://")):
        return None
    target = urlsplit(urljoin(base_url or "", raw))
    base = urlsplit(base_url or "")
    if target.scheme not in ("http", "https") or (base.netloc and target.netloc.lower() != base.netloc.lower()):
        return None
    path = target.path or "/"
    if not path.startswith(MODULE_PREFIX) or ".." in path.split("/"):
        return None
    return path + ("?" + target.query if target.query else "")


def is_tab_path(path):
    return str(path or "").split("?", 1)[0] in TAB_PATHS


def write_link(path):
    return action_link(str(path or "").split("?", 1)[0])


def content_root(soup):
    for selector in CONTENT_SELECTORS:
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup.body or soup


def _hidden(node):
    if node.has_attr("hidden") or str(node.get("aria-hidden") or "").lower() == "true":
        return True
    style = str(node.get("style") or "").replace(" ", "").lower()
    if "display:none" in style:
        return True
    return bool(_classes(node) & SKIPPED_CLASSES)


def _notice_tone(node):
    tokens = _class_tokens(node)
    if str(node.get("role") or "").lower() == "alert" or tokens & NOTICE_CLASSES:
        for word, tone in NOTICE_TONES:
            if word in tokens:
                return tone
        return "info"
    return ""


def _is_error_node(node):
    return bool(_classes(node) & ERROR_CLASSES) or _notice_tone(node) == "error"


def parse_conferences(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    text = soup.get_text(" ", strip=True).lower()
    if EMPTY_PHRASE in text:
        return {"empty": True, "items": []}
    root = content_root(soup)
    bodies = [table.find("tbody") for table in root.find_all("table")]
    bodies = [body for body in bodies if body is not None]
    if bodies:
        items = []
        for body in bodies:
            headers = _table_headers(body.find_parent("table"))
            for row in body.find_all("tr", recursive=False) or body.find_all("tr"):
                items.append(_list_item(row, [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])], headers, base_url))
        if not items:
            return {"empty": True, "items": []}
        return {"empty": False, "items": items}
    blocks = _list_blocks(root, base_url)
    if blocks:
        return {"empty": False, "items": [_list_item(block, _block_cells(block), [], base_url) for block in blocks]}
    return {"error": "parse_failed", "items": []}


def _list_item(node, cells, headers, base_url):
    anchors = node.find_all("a", href=True)
    links = [urljoin(base_url, anchor["href"]) for anchor in anchors if is_safe_url(anchor["href"])]
    paths = []
    for href in [anchor["href"] for anchor in anchors] + _data_links(node):
        path = module_path(href, base_url)
        if path and not is_tab_path(path) and not write_link(path) and path not in paths:
            paths.append(path)
    return {"cells": cells, "links": links, "headers": headers, "paths": paths}


def _data_links(node):
    found = []
    for name in ("data-href", "data-url", "data-link"):
        value = node.get(name)
        if isinstance(value, str) and value.strip():
            found.append(value)
    return found


def _list_blocks(root, base_url):
    chosen = []
    for node in root.find_all(True):
        if not (_classes(node) & BLOCK_CLASSES or node.name == "article"):
            continue
        if _inside_skipped(node, root) or any(seen in node.parents for seen in chosen):
            continue
        if _block_cells(node):
            chosen.append(node)
    for anchor in root.find_all("a", href=True):
        path = module_path(anchor["href"], base_url)
        if not path or is_tab_path(path) or _inside_skipped(anchor, root):
            continue
        if any(seen in anchor.parents for seen in chosen):
            continue
        block = _enclosing_block(anchor, root)
        if block is None or any(block is seen or seen in block.parents or block in seen.parents for seen in chosen):
            continue
        chosen.append(block)
    order = {id(node): index for index, node in enumerate(root.find_all(True))}
    return sorted(chosen, key=lambda node: order.get(id(node), 0))


def _inside_skipped(node, root):
    for parent in node.parents:
        if parent is root:
            return False
        if isinstance(parent, Tag) and (parent.name in ("nav", "header", "footer", "aside") or _hidden(parent)):
            return True
    return False


def _enclosing_block(anchor, root):
    fallback = None
    for parent in anchor.parents:
        if parent is root or not isinstance(parent, Tag):
            break
        if parent.name in ("li", "article", "tr") or _classes(parent) & BLOCK_CLASSES:
            return parent
        if fallback is None and parent.name in ("div", "section", "p"):
            fallback = parent
    return fallback


def _block_cells(block):
    cells = []
    for text in _visible_strings(block, CELL_EXCLUDED_TAGS, _action_link):
        value = _clean(text, MAX_CELL)
        if value and value not in cells:
            cells.append(value)
    return cells


def _table_headers(table):
    if table is None:
        return []
    head = table.find("thead")
    row = head.find("tr") if head is not None else None
    if row is None:
        first = table.find("tr")
        row = first if first is not None and first.find("th") is not None and not first.find("td") else None
    if row is None:
        return []
    return [_clean(cell.get_text(" "), MAX_CELL) for cell in row.find_all(["th", "td"])]


class PageReader:
    def __init__(self, base_url):
        self.base_url = base_url
        self.own_path = (module_path(base_url, base_url) or "").split("?", 1)[0]
        self.blocks = []
        self.forms = []
        self.notices = []

    def read(self, html):
        soup = BeautifulSoup(html or "", "html.parser")
        title = ""
        root = content_root(soup)
        heading = root.find(["h1", "h2"])
        if heading is not None:
            title = _clean(heading.get_text(" "), MAX_CELL)
        if not title and soup.title is not None:
            title = _clean(soup.title.get_text(" ").split(" - ")[0], MAX_CELL)
        self._walk(root, {heading} if heading is not None else set())
        return {
            "title": title,
            "blocks": self.blocks[:MAX_BLOCKS],
            "forms": self.forms,
            "notices": self.notices,
        }

    def _add(self, block):
        if block.get("kind") == "text":
            text = block["text"]
            if not text or any(existing.get("kind") == "text" and existing.get("text") == text for existing in self.blocks[-3:]):
                return
        if block.get("kind") == "links" and self.blocks and self.blocks[-1].get("kind") == "links":
            self.blocks[-1]["links"].extend(block["links"])
            return
        self.blocks.append(block)

    def _walk(self, node, skip):
        for child in list(node.children):
            if isinstance(child, NavigableString):
                if type(child) is NavigableString:
                    text = _clean(child)
                    if text:
                        self._add({"kind": "text", "text": text})
                continue
            if not isinstance(child, Tag) or child in skip:
                continue
            self._node(child, skip)

    def _node(self, node, skip):
        name = node.name
        if name in SKIPPED_TAGS or _hidden(node):
            return
        tone = _notice_tone(node)
        if tone:
            text = _clean(node.get_text(" "))
            if text:
                notice = {"tone": tone, "text": text}
                self.notices.append(notice)
                self._add(dict(notice, kind="notice"))
            return
        if name == "form":
            index = self._form(node)
            if index is not None:
                self._add({"kind": "form", "form": index})
            return
        if name == "table":
            self._add(self._table(node))
            return
        if name == "dl":
            facts = self._facts(node)
            if facts:
                self._add({"kind": "facts", "facts": facts})
            return
        if name in HEADING_TAGS:
            text = _clean(node.get_text(" "), MAX_CELL)
            if text:
                self._add({"kind": "heading", "text": text})
            return
        if name in ("ul", "ol"):
            self._list(node, skip)
            return
        if name == "a":
            self._anchor(node)
            return
        if name == "br" or name == "hr":
            return
        if not self._has_block_children(node):
            self._inline(node)
            return
        self._walk(node, skip)

    def _has_block_children(self, node):
        return any(isinstance(child, Tag) and (child.name in BLOCK_TAGS or child.name in SKIPPED_TAGS or _notice_tone(child)) for child in node.descendants)

    def _inline(self, node):
        text = _clean(node.get_text(" "))
        links, writes = self._links_in(node)
        own = " ".join(link["label"] for link in links + writes)
        if text and text != own:
            self._add({"kind": "text", "text": text})
        if links:
            self._add({"kind": "links", "links": links})
        self._add_link_forms(writes)

    def _add_link_forms(self, writes):
        for link in writes:
            self._add({"kind": "form", "form": self._link_form(link)})

    def _link_form(self, link, row=None):
        target, _, query = link["path"].partition("?")
        fields = [
            {"key": name, "name": name, "kind": "hidden", "value": value}
            for name, value in parse_qsl(query, keep_blank_values=True)
        ]
        destructive = _has_destructive_word(target) or _has_destructive_word(link["label"])
        form = {
            "action": target,
            "method": "get",
            "title": "",
            "fields": fields,
            "submits": [{"name": "", "value": "", "label": link["label"], "destructive": destructive}],
            "errors": [],
            "unsupported": False,
            "destructive": destructive,
            "writes": True,
            "index": len(self.forms),
        }
        if row is not None:
            form["row"] = list(row)
        self.forms.append(form)
        return form["index"]

    def _anchor(self, node):
        path = module_path(node.get("href"), self.base_url)
        if path and (is_tab_path(path) or self._upward(path)):
            return
        links, writes = self._links_in(node)
        if links or writes:
            if links:
                self._add({"kind": "links", "links": links})
            self._add_link_forms(writes)
            return
        text = _clean(node.get_text(" "))
        if text:
            self._add({"kind": "text", "text": text})

    def _links_in(self, node):
        found = []
        writes = []
        anchors = [node] if node.name == "a" else node.find_all("a", href=True)
        for anchor in anchors:
            path = module_path(anchor.get("href"), self.base_url)
            if not path or is_tab_path(path) or self._upward(path):
                continue
            label = _clean(anchor.get_text(" "), MAX_CELL) or _clean(anchor.get("title") or anchor.get("aria-label"), MAX_CELL)
            (writes if write_link(path) else found).append({"label": label, "path": path})
        return found, writes

    def _upward(self, path):
        target = path.split("?", 1)[0].rstrip("/")
        return bool(target) and self.own_path.startswith(target + "/")

    def _list(self, node, skip):
        for item in node.find_all("li", recursive=False):
            if _hidden(item):
                continue
            if self._has_block_children(item):
                self._walk(item, skip)
            else:
                self._inline(item)

    def _facts(self, node):
        facts = []
        label = ""
        for child in node.find_all(["dt", "dd"]):
            if child.name == "dt":
                label = _clean(child.get_text(" "), MAX_CELL)
            else:
                value = _clean(child.get_text(" "))
                if label or value:
                    facts.append({"label": label, "value": value})
                label = ""
        return facts

    def _table(self, table):
        headers = _table_headers(table)
        body = table.find("tbody") or table
        rows = []
        for row in body.find_all("tr"):
            if row.find_parent("table") is not table or (row.find("th") is not None and row.find("td") is None and not rows and headers):
                continue
            if _hidden(row):
                continue
            cells = []
            for cell in row.find_all(["td", "th"], recursive=False):
                cells.append(_clean(self._cell_text(cell), MAX_CELL))
            forms = []
            for form in row.find_all("form"):
                index = self._form(form)
                if index is not None:
                    forms.append(index)
                    self.forms[index]["row"] = list(cells)
            links, writes = self._links_in(row)
            for href in _data_links(row):
                path = module_path(href, self.base_url)
                if path and not is_tab_path(path) and all(link["path"] != path for link in links + writes):
                    (writes if write_link(path) else links).append({"label": "", "path": path})
            for link in writes:
                forms.append(self._link_form(link, cells))
            if any(cells) or forms or links:
                rows.append({"cells": cells, "links": links, "forms": forms})
        caption = table.find("caption")
        return {
            "kind": "table",
            "caption": _clean(caption.get_text(" "), MAX_CELL) if caption is not None else "",
            "headers": headers,
            "rows": rows,
        }

    def _cell_text(self, cell):
        return " ".join(_visible_strings(cell, CELL_EXCLUDED_TAGS))

    def _form(self, node):
        form = parse_form(node, self.base_url)
        if form is None:
            return None
        form["index"] = len(self.forms)
        self.forms.append(form)
        return form["index"]


def parse_conference_page(html, base_url):
    return PageReader(base_url).read(html)


def parse_form(node, base_url):
    method = str(node.get("method") or "get").strip().lower()
    target = node.get("hx-post") or node.get("action") or ""
    action = module_path(target, base_url) if str(target).strip() else module_path(base_url, base_url)
    if action is None:
        return None
    if method not in ("get", "post"):
        method = "post"
    fields = []
    submits = []
    radios = {}
    unsupported = False
    for control in node.find_all(["input", "select", "textarea", "button"]):
        if _hidden_control(control):
            continue
        name = str(control.get("name") or "").strip()
        kind = _control_kind(control)
        if kind == "submit":
            submits.append(_submit(control, name))
            continue
        if kind in IGNORED_INPUT_KINDS or kind == "button" or not name:
            continue
        if kind == "file":
            unsupported = True
            continue
        if kind == "hidden":
            fields.append({"key": name, "name": name, "kind": "hidden", "value": str(control.get("value") or "")})
            continue
        if kind == "radio":
            group = radios.get(name)
            if group is None:
                group = {
                    "key": name, "name": name, "kind": "radio", "label": _group_label(control, node), "options": [],
                    "required": False, "error": "",
                }
                radios[name] = group
                fields.append(group)
            group["required"] = group["required"] or control.has_attr("required") or _marked_required(control, node)
            if len(group["options"]) < MAX_OPTIONS:
                group["options"].append({
                    "value": str(control.get("value") or "on"),
                    "label": _control_label(control, node),
                    "selected": control.has_attr("checked"),
                    "disabled": control.has_attr("disabled"),
                })
            continue
        field = {
            "key": name,
            "name": name,
            "kind": kind,
            "label": _control_label(control, node),
            "required": control.has_attr("required"),
            "disabled": control.has_attr("disabled"),
            "readonly": control.has_attr("readonly"),
            "error": "",
        }
        if kind == "select":
            field["multiple"] = control.has_attr("multiple")
            field["options"] = _select_options(control)
        elif kind == "checkbox":
            field["value"] = str(control.get("value") or "on")
            field["checked"] = control.has_attr("checked")
            field["key"] = "%s#%d" % (name, sum(1 for other in fields if other.get("name") == name))
        elif kind == "textarea":
            field["value"] = control.get_text()
            field["maxlength"] = _int(control.get("maxlength"))
        else:
            field["value"] = str(control.get("value") or "")
            field["placeholder"] = _clean(control.get("placeholder"), MAX_CELL)
            field["maxlength"] = _int(control.get("maxlength"))
            for limit in ("min", "max", "step"):
                if control.get(limit) is not None:
                    field[limit] = str(control.get(limit))
        fields.append(field)
    errors = _form_errors(node, fields)
    legend = node.find(["legend", "h1", "h2", "h3", "h4", "h5"])
    form = {
        "action": action,
        "method": method,
        "title": _clean(legend.get_text(" "), MAX_CELL) if legend is not None else "",
        "fields": fields,
        "submits": submits or [{"name": "", "value": "", "label": "", "destructive": False}],
        "errors": errors,
        "unsupported": unsupported,
        "destructive": _destructive(action, fields, submits),
    }
    form["writes"] = method == "post" or _get_writes(form)
    return form


def _action_link(node):
    return node.name == "a" and "btn" in _class_tokens(node)


def _visible_strings(node, excluded, dropped=None):
    found = []
    for piece in node.find_all(string=True):
        if type(piece) is not NavigableString:
            continue
        skip = False
        for parent in piece.parents:
            if parent is node:
                break
            if parent.name in excluded or _hidden(parent) or (dropped is not None and dropped(parent)):
                skip = True
                break
        if not skip and piece.strip():
            found.append(str(piece).strip())
    return found


def _hidden_control(control):
    for parent in [control] + list(control.parents):
        if not isinstance(parent, Tag) or parent.name == "form":
            break
        if parent.name == "template":
            return True
    return False


def _control_kind(control):
    if control.name == "button":
        kind = str(control.get("type") or "submit").strip().lower()
        return "submit" if kind == "submit" else "button"
    if control.name in ("select", "textarea"):
        return control.name
    kind = str(control.get("type") or "text").strip().lower()
    if kind in ("submit", "image"):
        return "submit"
    if kind in ("hidden", "radio", "checkbox", "file") or kind in IGNORED_INPUT_KINDS:
        return kind
    return kind if kind in TEXT_INPUT_KINDS else "text"


def _submit(control, name):
    if control.name == "button":
        label = _clean(control.get_text(" "), MAX_CELL) or _clean(control.get("title") or control.get("aria-label"), MAX_CELL)
    else:
        label = _clean(control.get("value") or control.get("alt") or control.get("title"), MAX_CELL)
    value = str(control.get("value") or "")
    return {
        "name": name,
        "value": value,
        "label": label or _clean(control.get("title") or control.get("aria-label"), MAX_CELL),
        "destructive": _has_destructive_word(" ".join([name, value, label, " ".join(control.get("class") or [])])),
    }


def _destructive(action, fields, submits):
    if _has_destructive_word(action):
        return True
    for field in fields:
        if field["kind"] == "hidden" and field["name"].lower() == "_method" and field["value"].strip().upper() == "DELETE":
            return True
    return bool(submits) and all(submit["destructive"] for submit in submits)


def _get_writes(form):
    if form["destructive"] or write_link(form["action"]) or any(submit["destructive"] for submit in form["submits"]):
        return True
    named = [
        (field["name"], field.get("value") or "")
        for field in form["fields"]
        if field["kind"] == "hidden" and not secret_field(field["name"])
    ]
    named += [(submit["name"], submit["value"]) for submit in form["submits"]]
    return any(_has_write_word(name) or _has_write_word(value) for name, value in named)


def _has_write_word(text):
    return bool({word for word in re.split(r"[^a-z]+", str(text or "").lower()) if word} & WRITE_WORDS)


def _has_destructive_word(text):
    words = {word for word in re.split(r"[^a-zäöüß]+", str(text or "").lower()) if word}
    return bool(words & DESTRUCTIVE_WORDS)


def _int(value):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _select_options(control):
    options = []
    for option in control.find_all("option"):
        if len(options) >= MAX_OPTIONS:
            break
        group = option.find_parent("optgroup")
        label = _clean(option.get_text(" "), MAX_CELL)
        value = option.get("value")
        options.append({
            "value": str(value if value is not None else option.get_text(" ").strip()),
            "label": label,
            "group": _clean(group.get("label"), MAX_CELL) if group is not None else "",
            "selected": option.has_attr("selected"),
            "disabled": option.has_attr("disabled") or (group is not None and group.has_attr("disabled")),
        })
    return options


def _control_label(control, form):
    control_id = control.get("id")
    if control_id:
        node = form.find("label", attrs={"for": control_id})
        if node is not None:
            text = _clean(node.get_text(" "), MAX_CELL)
            if text:
                return text
    parent = control.find_parent("label")
    if parent is not None:
        text = _clean(parent.get_text(" "), MAX_CELL)
        if text:
            return text
    for attribute in ("aria-label", "title", "placeholder"):
        text = _clean(control.get(attribute), MAX_CELL)
        if text:
            return text
    row = control.find_parent("tr")
    if row is not None:
        text = _clean(" ".join(_visible_strings(row, CELL_EXCLUDED_TAGS)), MAX_CELL)
        if text:
            return text
    sibling = control.find_next_sibling(string=True)
    text = _clean(sibling, MAX_CELL) if sibling else ""
    return text


def _group_label(control, form):
    fieldset = control.find_parent("fieldset")
    if fieldset is not None and form in fieldset.parents:
        legend = fieldset.find("legend")
        if legend is not None:
            return _clean(legend.get_text(" "), MAX_CELL)
    group = _field_group(control, form)
    if group is None:
        return ""
    for node in group.find_all(["label", "strong", "b", "legend"]):
        if node.find(["input", "select", "textarea"]) is not None:
            continue
        target = form.find(id=node.get("for")) if node.get("for") else None
        if target is not None and str(target.get("type") or "").lower() == "radio":
            continue
        text = _clean(node.get_text(" "), MAX_CELL)
        if text:
            return text
    return ""


def _marked_required(control, form):
    group = _field_group(control, form)
    if group is None:
        return False
    return any("required" in _classes(label) and label.find(["input", "select", "textarea"]) is None for label in group.find_all("label"))


def _field_group(control, form):
    for parent in control.parents:
        if parent is form or not isinstance(parent, Tag):
            return None
        if _classes(parent) & FIELD_GROUP_CLASSES or parent.name == "fieldset":
            return parent
    return None


def _form_errors(form, fields):
    texts = []
    by_name = {field["name"]: field for field in fields}
    for node in form.find_all(True):
        error_node = _is_error_node(node)
        if not error_node:
            continue
        if any(parent is not form and isinstance(parent, Tag) and _is_error_node(parent) for parent in node.parents if form in parent.parents):
            continue
        text = _clean(node.get_text(" "), MAX_CELL)
        if not text:
            continue
        if text not in texts:
            texts.append(text)
        field = _field_for_error(node, form, by_name)
        if field is not None and not field.get("error"):
            field["error"] = text
    for node in form.find_all(class_=lambda value: bool(value) and bool(set(str(value).lower().split()) & ERROR_CONTAINERS)):
        if node.name in ("input", "select", "textarea"):
            continue
        for control in node.find_all(["input", "select", "textarea"]):
            field = by_name.get(str(control.get("name") or ""))
            if field is not None and not field.get("error"):
                message = node.find(class_=lambda value: bool(value) and bool(set(str(value).lower().split()) & {"help-block", "form-text"}))
                field["error"] = _clean(message.get_text(" "), MAX_CELL) if message is not None else ""
                if field["error"] and field["error"] not in texts:
                    texts.append(field["error"])
    return texts


def _field_for_error(node, form, by_name):
    for parent in node.parents:
        if parent is form or not isinstance(parent, Tag):
            break
        for control in parent.find_all(["input", "select", "textarea"]):
            field = by_name.get(str(control.get("name") or ""))
            if field is not None and field["kind"] != "hidden":
                return field
    return None


def page_errors(page):
    found = [notice["text"] for notice in page.get("notices") or [] if notice.get("tone") == "error"]
    for form in page.get("forms") or []:
        for text in form.get("errors") or []:
            if text not in found:
                found.append(text)
    return found


def page_successes(page):
    return [notice["text"] for notice in page.get("notices") or [] if notice.get("tone") == "success"]


def page_fingerprint(page):
    parts = [page.get("title") or ""]
    for block in page.get("blocks") or []:
        kind = block.get("kind")
        if kind in ("text", "heading", "notice"):
            parts.append(block.get("text") or "")
        elif kind == "facts":
            parts.extend("%s=%s" % (fact["label"], fact["value"]) for fact in block["facts"])
        elif kind == "table":
            for row in block["rows"]:
                parts.append("|".join(row["cells"]))
        elif kind == "links":
            parts.extend("%s>%s" % (link["label"], link["path"]) for link in block["links"])
    for form in page.get("forms") or []:
        for field in form["fields"]:
            if field["kind"] == "hidden":
                parts.append(field["name"])
            elif field["kind"] in ("radio", "select"):
                parts.extend("%s:%s:%s:%s" % (field["name"], option["value"], option["selected"], option["disabled"]) for option in field["options"])
            elif field["kind"] == "checkbox":
                parts.append("%s:%s:%s:%s" % (field["name"], field["value"], field["checked"], field["disabled"]))
            else:
                parts.append("%s:%s" % (field["name"], field.get("value") or ""))
    return "\n".join(parts)


def secret_field(name):
    lowered = str(name or "").lower()
    return any(word in lowered for word in SECRET_FIELD_WORDS)


def form_signature(form):
    names = sorted("%s:%s" % (field["kind"], field["name"]) for field in form.get("fields") or [])
    hidden = sorted(
        "%s=%s" % (field["name"], field.get("value") or "")
        for field in form.get("fields") or []
        if field["kind"] == "hidden" and not secret_field(field["name"])
    )
    submits = sorted("%s=%s" % (submit["name"], submit.get("value") or "") for submit in form.get("submits") or [])
    row = "|".join(form.get("row") or [])
    return "\n".join([form.get("method") or "", form.get("action") or "", ",".join(names), ",".join(hidden), ",".join(submits), row])


def page_problems(page):
    found = [notice["text"] for notice in page.get("notices") or [] if notice.get("tone") in ("error", "warning")]
    for text in page_errors(page):
        if text not in found:
            found.append(text)
    return found


def _rows(page):
    return {
        "|".join(row["cells"])
        for block in page.get("blocks") or []
        if block.get("kind") == "table"
        for row in block.get("rows") or []
    }


def _texts(page):
    found = set(_rows(page))
    for block in page.get("blocks") or []:
        if block.get("kind") in ("text", "heading"):
            found.add(block.get("text") or "")
    return found


def _field_options(page, name):
    for form in page.get("forms") or []:
        for field in form.get("fields") or []:
            if field.get("name") == name and field.get("kind") in ("radio", "select"):
                return {option["value"]: option for option in field.get("options") or []}
    return None


def change_matches(form, pairs, before, after):
    row = "|".join(form.get("row") or [])
    if row:
        return row in _rows(before) and row not in _rows(after)
    sent = {}
    for name, value in pairs:
        sent.setdefault(name, []).append(value)
    new_texts = _texts(after) - _texts(before)
    for field in form.get("fields") or []:
        if field["kind"] not in ("radio", "select") or field.get("profile"):
            continue
        for value in sent.get(field["name"], []):
            option = next((candidate for candidate in field["options"] if candidate["value"] == value), None)
            if option is None or not str(value).strip():
                continue
            later = _field_options(after, field["name"])
            if later is not None and (value not in later or later[value]["disabled"]):
                return True
            label = option.get("label") or ""
            if label and any(label in text for text in new_texts):
                return True
    return False


DATE_IN_TEXT = re.compile(r"(?<!\d)(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?!\d)")
COLON_TIME = re.compile(r"(?<![\d.:])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])(?:\s*([ap])\.?m\b)?", re.IGNORECASE)
CLOCK_WORD_TIME = re.compile(r"(?<![\d.:])([01]?\d|2[0-3])(?:\.([0-5]\d))?\s*(?:uhr|h)\b", re.IGNORECASE)
HOUR_MERIDIEM_TIME = re.compile(r"(?<![\d.:])(1[0-2]|0?[1-9])\s*([ap])\.?m\b", re.IGNORECASE)
BOOKING_WINDOW_WORDS = ("buchung", "anmeldung", "booking")
PROFILE_NAME_WORDS = ("child", "student", "pupil", "kind", "schueler", "schüler")
PROFILE_LABEL_WORDS = ("kind", "kinder", "schüler", "schülerin", "schueler", "sohn", "tochter", "child", "student")


def dates_in(text):
    found = []
    for day, month, year in DATE_IN_TEXT.findall(str(text or "")):
        number = int(year)
        if number < 100:
            number += 2000
        try:
            found.append(date(number, int(month), int(day)))
        except ValueError:
            continue
    return found


def _meridiem(hour, mark):
    if not mark:
        return hour
    hour = hour % 12
    return hour + 12 if mark.lower() == "p" else hour


def time_in(text):
    plain = DATE_IN_TEXT.sub(" ", str(text or ""))
    found = []
    for match in COLON_TIME.finditer(plain):
        hour = int(match.group(1))
        if match.group(3) and not 1 <= hour <= 12:
            continue
        found.append((match.start(), _meridiem(hour, match.group(3)), int(match.group(2))))
    for match in CLOCK_WORD_TIME.finditer(plain):
        found.append((match.start(), int(match.group(1)), int(match.group(2) or 0)))
    for match in HOUR_MERIDIEM_TIME.finditer(plain):
        found.append((match.start(), _meridiem(int(match.group(1)), match.group(2)), 0))
    if not found:
        return ""
    _start, hour, minute = min(found)
    return "%02d:%02d" % (hour, minute)


def first_time(texts):
    for text in texts:
        found = time_in(text)
        if found:
            return found
    return ""


def _window_cell(text):
    lowered = str(text or "").lower()
    return any(word in lowered for word in BOOKING_WINDOW_WORDS)


def booking_window(cells):
    for cell in cells:
        if not _window_cell(cell):
            continue
        found = dates_in(cell)
        if found:
            return found[0], (found[1] if len(found) > 1 else None)
    return None


def event_day(cells):
    for cell in cells:
        if _window_cell(cell):
            continue
        found = dates_in(cell)
        if found:
            return found[0]
    return None


def is_profile_name(name):
    lowered = str(name or "").lower()
    return any(word in lowered for word in PROFILE_NAME_WORDS)


def is_profile_field(field):
    if field.get("kind") not in ("select", "radio"):
        return False
    if is_profile_name(field.get("name")):
        return True
    label = set(re.split(r"[^a-zäöüß]+", str(field.get("label") or "").lower()))
    return bool(label & set(PROFILE_LABEL_WORDS))


BOOKING_HEADING_WORDS = ("termin", "buchung", "gebucht", "booking", "booked", "appointment")
LETTER = re.compile(r"[^\W\d_]")


def booking_heading(text):
    lowered = str(text or "").lower()
    return any(word in lowered for word in BOOKING_HEADING_WORDS)


def teacher_of(cells):
    for cell in cells:
        text = str(cell or "").strip()
        if text and LETTER.search(text) and not any(char.isdigit() for char in text):
            return text
    return ""


def booking_key(cells, day=""):
    found = dates_in(" ".join(str(cell or "") for cell in cells))
    shown = found[0].isoformat() if found else str(day or "")
    return "%s|%s|%s" % (shown, first_time(cells), teacher_of(cells).casefold())


def same_booking(one, two):
    first = str(one or "").split("|")
    second = str(two or "").split("|")
    if len(first) != 3 or len(second) != 3 or first[1:] != second[1:]:
        return False
    return not first[0] or not second[0] or first[0] == second[0]
