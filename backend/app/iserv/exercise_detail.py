import hashlib
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString

from .exercises import COLUMN_LABELS, DONE, DUE, EXERCISE_PATH, SORT_ATTRIBUTES, START, TAGS, parse_moment
from .pages import action_link, path_of, squeezed

DESCRIPTION = "description"
FILES = "files"
SUBMISSION = "submission"
FEEDBACK = "feedback"
SOLUTION = "solution"
SECTION_ORDER = (FEEDBACK, SOLUTION, SUBMISSION, FILES, DESCRIPTION)
SECTION_WORDS = {
    FEEDBACK: ("rückmeldung", "rückmeldungen", "feedback", "bewertung", "bewertungen", "korrektur", "assessment", "grade", "grading", "note"),
    SOLUTION: ("musterlösung", "musterlösungen", "lösung", "lösungen", "solution", "solutions", "model solution", "sample solution"),
    SUBMISSION: (
        "abgabe", "abgaben", "meine abgabe", "ergebnis", "ergebnisse", "einreichung", "bestätigung", "submission",
        "submissions", "hand in", "your submission", "my submission", "result", "results", "confirmation",
    ),
    FILES: ("anhänge", "anhang", "dateien", "material", "materialien", "attachments", "attachment", "files", "materials"),
    DESCRIPTION: ("beschreibung", "aufgabenstellung", "aufgabe", "details", "informationen", "description", "task", "information"),
}
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6", "legend")
HEADING_CLASSES = re.compile(r"^(panel-title|panel-heading|card-title|card-header|box-title|section-title)$", re.IGNORECASE)
DROPPED = ("script", "style", "noscript", "template", "svg", "iframe", "nav", "button", "select", "option", "input")
DROPPED_CLASSES = re.compile(
    r"^(breadcrumb|pagination|navbar|sidebar|toolbar|btn-toolbar|btn-group|dropdown-menu|modal|sr-only|visually-hidden|dropdown)$",
    re.IGNORECASE,
)
CONTENT_IDS = ("content", "main-content", "page-content")
BLOCKS = frozenset({
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt", "figcaption", "figure", "footer", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
    "fieldset", "legend", "label", "tbody", "thead",
})
FILE_PATH = re.compile(r"(^/iserv/(file|fs|storage|download)/)|(/(download|downloads|dl|attachment|attachments|file|files|get)(/|$))|(-dl/)", re.IGNORECASE)
FILE_SUFFIX = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|od[tsgp]|rtf|txt|csv|zip|7z|rar|jpe?g|png|gif|webp|heic|bmp|tiff?|mp3|m4a|wav|ogg|opus|webm|mp4|mov|ggb|sb3)$", re.IGNORECASE)
WEB = ("http", "https")
TOKEN_NAME = re.compile(r"(token|csrf|nonce)", re.IGNORECASE)
EDITOR_MARK = re.compile(r"(editor|tinymce|wysiwyg|ckeditor|quill|summernote|richtext|rich-text|trix)", re.IGNORECASE)
MARKUP = re.compile(r"<\s*(p|br|div|span|b|strong|i|em|ul|ol|li|h\d)\b", re.IGNORECASE)
ERROR_CLASSES = re.compile(r"^(invalid-feedback|form-error|form-errors|form-error-message|alert-danger)$", re.IGNORECASE)
ERROR_HOLDERS = re.compile(r"^(has-error|is-invalid|has-danger)$", re.IGNORECASE)
ERROR_HINTS = re.compile(r"^(help-block|form-text|text-danger|error|errors)$", re.IGNORECASE)
WRITE_ROOT = "/iserv/"
REFUSED_ACTIONS = ("/iserv/auth", "/iserv/login", "/iserv/logout", "/iserv/app/logout")
UNDO_WORDS = (
    "nicht erledigt", "als nicht erledigt", "zurücknehmen", "rückgängig", "widerrufen", "wieder öffnen", "undo", "not done",
    "mark as not done", "reopen", "revoke", "unmark", "unconfirm", "retract",
)
DELETE_WORDS = ("löschen", "entfernen", "delete", "remove", "trash", "discard")
CONFIRM_WORDS = (
    "erledigt", "als erledigt", "bestätigen", "bestätigung", "fertig", "abschließen", "done", "mark as done", "complete",
    "completed", "confirm", "finish", "finished",
)
SAVE_WORDS = ("speichern", "abgeben", "hochladen", "senden", "einreichen", "save", "submit", "upload", "send", "hand in")
WORD = re.compile(r"[^\W\d_]+")
TEXT_LIMIT = 12000
LINE_LIMIT = 4000
LINK_LIMIT = 30
LABEL_LIMIT = 200
FACT_LIMIT = 30
FACT_VALUE_LIMIT = 500
ERROR_LIMIT = 5
FORM_LIMIT = 20
FORM_ID_LENGTH = 16
TAG_LIMIT = 30


def _words(text):
    return WORD.findall(str(text or "").casefold())


def _phrase_in(text, phrase):
    words = _words(text)
    parts = _words(phrase)
    if not parts:
        return False
    size = len(parts)
    if any(words[index:index + size] == parts for index in range(len(words) - size + 1)):
        return True
    return size == 1 and len(parts[0]) >= 5 and any(word != parts[0] and word.endswith(parts[0]) for word in words)


def section_of(text):
    for section in SECTION_ORDER:
        if any(_phrase_in(text, phrase) for phrase in SECTION_WORDS[section]):
            return section
    return None


def _is_heading(node):
    if node.name in HEADINGS:
        return True
    return any(HEADING_CLASSES.match(str(name)) for name in node.get("class") or [])


def _is_noise(node):
    if node.name in DROPPED:
        return True
    if any(DROPPED_CLASSES.match(str(name)) for name in node.get("class") or []):
        return True
    return node.get("hidden") is not None


def detail_root(soup):
    for name in CONTENT_IDS:
        found = soup.find(id=name)
        if found is not None:
            return found
    return soup.find("main") or soup.find(attrs={"role": "main"}) or soup.body or soup


def _target(href, page_path):
    value = str(href or "").strip()
    if not value or value.startswith("#") or value.lower().startswith("javascript:"):
        return ""
    joined = urljoin(page_path, value)
    parts = urlsplit(joined)
    if parts.scheme and parts.scheme not in WEB:
        return ""
    return joined


def _is_file(anchor, target):
    path = path_of(target)
    return anchor.has_attr("download") or bool(FILE_PATH.search(path)) or bool(FILE_SUFFIX.search(path))


def _own_page(target, page_path):
    if path_of(target).startswith(WRITE_ROOT) and action_link(target):
        return True
    if urlsplit(target).netloc:
        return False
    path = path_of(target).rstrip("/")
    return path == page_path.rstrip("/") or path == EXERCISE_PATH or path.startswith(EXERCISE_PATH + "/past")


def _fact_rows(table):
    rows = []
    for row in table.find_all("tr"):
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        if len(cells) != 2:
            return None
        rows.append(cells)
    if not rows:
        return None
    if not all(cells[0].name == "th" or squeezed(cells[0].get_text(" "), LABEL_LIMIT).endswith(":") for cells in rows):
        return None
    return rows


def _fact_label(text):
    return squeezed(text, LABEL_LIMIT).rstrip(":").strip()


class _Section:
    def __init__(self):
        self.raw = [""]
        self.files = []
        self.links = []
        self.images = []
        self.facts = []


class _Reader:
    def __init__(self, page_path, title=""):
        self.page_path = page_path
        self.title = title
        self.current = DESCRIPTION
        self.sections = {name: _Section() for name in SECTION_ORDER}
        self.headings = []

    def section(self):
        return self.sections[self.current]

    def heading(self, node):
        text = squeezed(node.get_text(" "), LABEL_LIMIT)
        if node.name == "h1" or (self.title and text == self.title):
            self.headings.append("title")
            return
        found = section_of(text)
        self.headings.append(found or "other")
        if found is not None:
            self.current = found
        elif text:
            self.section().raw.extend(["", text, ""])

    def add_link(self, anchor, meta=""):
        target = _target(anchor.get("href"), self.page_path)
        if not target or _own_page(target, self.page_path):
            return False
        label = squeezed(anchor.get_text(" ") or anchor.get("title") or anchor.get("download"), LABEL_LIMIT)
        is_file = _is_file(anchor, target)
        holder = self.section().files if is_file else self.section().links
        entry = {"href": target, "label": label}
        if is_file and meta:
            entry["meta"] = meta
        if all(item["href"] != target for item in holder) and len(holder) < LINK_LIMIT:
            holder.append(entry)
        return is_file

    def file_anchors(self, node):
        found = []
        for anchor in node.find_all("a", href=True):
            if any(_is_noise(parent) for parent in anchor.parents if parent is not node and parent.name):
                continue
            target = _target(anchor["href"], self.page_path)
            if target and not _own_page(target, self.page_path) and _is_file(anchor, target):
                found.append(anchor)
        return found

    def file_row(self, row):
        anchors = self.file_anchors(row)
        if len({anchor["href"] for anchor in anchors}) != 1:
            return False
        anchor = anchors[0]
        label = squeezed(anchor.get_text(" "), LABEL_LIMIT)
        parts = []
        for piece in row.find_all(string=True):
            if isinstance(piece, Comment) or piece.find_parent("a") is anchor or any(
                parent.name in ("script", "style", "textarea", "label", "button") or _is_noise(parent) for parent in piece.parents if parent is not row and parent.name
            ):
                continue
            text = squeezed(piece, LABEL_LIMIT)
            if text and text != label and text not in parts:
                parts.append(text)
        self.add_link(anchor, squeezed(" · ".join(parts), LABEL_LIMIT))
        return True

    def walk_file_table(self, table):
        for row in table.find_all("tr"):
            if row.find("td") is None:
                continue
            if not self.file_row(row):
                self.section().raw.append("")
                self.walk(row)
                self.section().raw.append("")

    def add_image(self, image):
        target = _target(image.get("src"), self.page_path)
        if not target or target.startswith("data:"):
            return
        entry = {"href": target, "label": squeezed(image.get("alt") or image.get("title"), LABEL_LIMIT)}
        if entry not in self.section().images and len(self.section().images) < LINK_LIMIT:
            self.section().images.append(entry)

    def add_fact(self, label, value_node):
        label = _fact_label(label)
        value = squeezed(value_node.get_text(" "), FACT_VALUE_LIMIT)
        facts = self.section().facts
        if (label or value) and len(facts) < FACT_LIMIT:
            facts.append({"label": label, "value": value, "node": value_node})
        for anchor in value_node.find_all("a", href=True):
            self.add_link(anchor)

    def walk(self, node):
        for child in list(node.children):
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                self.section().raw[-1] += str(child)
                continue
            if child.name is None or _is_noise(child):
                continue
            if _is_heading(child):
                self.heading(child)
                continue
            if child.name == "br":
                self.section().raw.append("")
                continue
            if child.name == "img":
                self.add_image(child)
                continue
            if child.name == "textarea" or (child.name == "label" and child.find_parent("form") is not None):
                continue
            if child.name == "dl":
                self.walk_dl(child)
                continue
            if child.name == "table":
                rows = _fact_rows(child)
                if rows is not None:
                    for cells in rows:
                        self.add_fact(cells[0].get_text(" "), cells[1])
                    continue
                if self.file_anchors(child):
                    self.walk_file_table(child)
                    continue
            if child.name in ("tr", "li") and self.file_row(child):
                continue
            if child.name == "a" and child.get("href"):
                if self.add_link(child):
                    continue
            if child.name in BLOCKS:
                self.section().raw.append("")
                self.walk(child)
                self.section().raw.append("")
            else:
                self.walk(child)

    def walk_dl(self, node):
        label = ""
        for child in node.find_all(["dt", "dd"]):
            if child.name == "dt":
                label = child.get_text(" ")
            else:
                self.add_fact(label, child)
                label = ""


def _lines(raw, skip=()):
    lines = []
    used = 0
    for line in raw:
        text = squeezed(line, LINE_LIMIT)
        if not text or text in skip or (lines and lines[-1] == text):
            continue
        if used + len(text) > TEXT_LIMIT:
            break
        lines.append(text)
        used += len(text)
    return lines


def _control_label(control):
    if control.name == "button":
        return squeezed(control.get_text(" ") or control.get("value") or control.get("title") or control.get("aria-label"), LABEL_LIMIT)
    return squeezed(control.get("value") or control.get("title") or control.get("aria-label"), LABEL_LIMIT)


def _form_words(form, submits):
    parts = [form.get("name"), form.get("id"), " ".join(form.get("class") or []), path_of(form.get("action") or "")]
    for control in submits:
        parts.extend([_control_label(control), control.get("name"), " ".join(control.get("class") or [])])
    return " ".join(str(part or "") for part in parts).replace("_", " ").replace("-", " ").replace("/", " ").replace("[", " ").replace("]", " ")


def _has_any(text, words):
    return any(_phrase_in(text, word) for word in words)


def _controls(form):
    fields = []
    files = []
    textareas = []
    checkboxes = []
    submits = []
    for control in form.find_all(["input", "textarea", "select", "button"]):
        name = control.get("name") or ""
        kind = (control.get("type") or ("submit" if control.name == "button" else "text")).lower()
        if control.name == "button" or kind in ("submit", "image"):
            if kind in ("submit", "image") and not control.has_attr("disabled"):
                submits.append(control)
            continue
        if not name or control.has_attr("disabled"):
            continue
        if control.name == "textarea":
            textareas.append(control)
            fields.append({"name": name, "type": "textarea", "value": control.get_text() or ""})
        elif control.name == "select":
            chosen = control.find("option", selected=True) or control.find("option")
            fields.append({"name": name, "type": "select", "value": (chosen.get("value") if chosen is not None and chosen.get("value") is not None else (chosen.get_text() if chosen is not None else ""))})
        elif kind == "file":
            files.append(control)
            fields.append({"name": name, "type": "file", "value": ""})
        elif kind in ("checkbox", "radio"):
            if kind == "checkbox":
                checkboxes.append(control)
            fields.append({"name": name, "type": kind, "value": control.get("value") or "on", "checked": control.has_attr("checked")})
        elif kind in ("reset",):
            continue
        else:
            fields.append({"name": name, "type": kind, "value": control.get("value") or ""})
    return fields, files, textareas, checkboxes, submits


def _labelled(control):
    return " ".join([_control_label(control), str(control.get("name") or "")]).replace("_", " ").replace("[", " ").replace("]", " ")


def _submit_with(submits, words):
    for control in submits:
        if _has_any(_labelled(control), words):
            return control
    return None


def _save_submit(submits):
    chosen = _submit_with(submits, SAVE_WORDS)
    if chosen is not None:
        return chosen
    for control in submits:
        if not _has_any(_labelled(control), DELETE_WORDS + UNDO_WORDS + CONFIRM_WORDS):
            return control
    return None


def _submit_entry(control):
    if control is None or not control.get("name"):
        return None
    return {"name": control.get("name"), "value": control.get("value") or ""}


def _operations(form, files, textareas, checkboxes, submits):
    words = _form_words(form, [])
    operations = {}
    if files and (not submits or _save_submit(submits) is not None):
        operations["upload"] = _submit_entry(_save_submit(submits))
    if textareas and (not submits or _save_submit(submits) is not None):
        operations["text"] = _submit_entry(_save_submit(submits))
    undo = _submit_with(submits, UNDO_WORDS)
    delete = _submit_with(submits, DELETE_WORDS)
    confirm = next((control for control in submits if _has_any(_labelled(control), CONFIRM_WORDS) and control is not undo), None)
    plain = not files and not textareas
    if undo is not None or (plain and len(submits) <= 1 and _has_any(words, UNDO_WORDS)):
        operations["undo"] = _submit_entry(undo if undo is not None else (submits[0] if submits else None))
    elif delete is not None or (plain and len(submits) <= 1 and _has_any(words, DELETE_WORDS)):
        operations["delete"] = _submit_entry(delete if delete is not None else (submits[0] if submits else None))
    elif confirm is not None or (plain and len(submits) <= 1 and _has_any(words, CONFIRM_WORDS)):
        operations["confirm"] = _submit_entry(confirm if confirm is not None else (submits[0] if submits else None))
    return operations


def _form_kind(operations):
    for kind in ("upload", "text", "undo", "delete", "confirm"):
        if kind in operations:
            return kind
    return "other"


def _form_id(method, action, fields):
    stable = sorted(
        (field["name"], "" if field["type"] in ("textarea", "file", "text", "checkbox") or TOKEN_NAME.search(field["name"]) else field["value"])
        for field in fields
    )
    raw = "|".join([method, path_of(action)] + ["%s=%s" % pair for pair in stable])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:FORM_ID_LENGTH]


def _row_of(node, stop):
    holder = node
    while holder is not None and holder is not stop:
        if holder.name in ("tr", "li") or any(re.match(r"^(list-group-item|file|file-item)$", str(name)) for name in holder.get("class") or []):
            return holder
        holder = holder.parent
    return None


def _row_label(row, page_path):
    if row is None:
        return ""
    for anchor in row.find_all("a", href=True):
        target = _target(anchor["href"], page_path)
        if target and _is_file(anchor, target):
            return squeezed(anchor.get_text(" ") or anchor.get("title"), LABEL_LIMIT)
    for holder in row.find_all(["a", "label", "td", "span"]):
        text = squeezed(holder.get_text(" "), LABEL_LIMIT)
        if text:
            return text
    return squeezed(row.get_text(" "), LABEL_LIMIT)


def _editor(textarea):
    marks = " ".join([" ".join(textarea.get("class") or []), str(textarea.get("id") or "")] + [str(name) for name in textarea.attrs if str(name).startswith("data-")])
    return bool(EDITOR_MARK.search(marks)) or bool(MARKUP.search(textarea.get_text() or ""))


def _plain_lines(markup):
    soup = BeautifulSoup(markup or "", "html.parser")
    reader = _Reader("/")
    reader.walk(soup)
    return _lines(reader.sections[DESCRIPTION].raw)


def _same_host_write(action, school_host):
    parts = urlsplit(action)
    if parts.scheme and parts.scheme not in WEB:
        return False
    if parts.netloc and school_host and (parts.hostname or "").lower() != school_host.lower():
        return False
    path = path_of(action)
    return path.startswith(WRITE_ROOT) and ".." not in path and not any(path.startswith(refused) for refused in REFUSED_ACTIONS)


def task_forms(soup, page_url, page_path, school_host=""):
    forms = []
    for index, form in enumerate(soup.find_all("form")):
        if len(forms) >= FORM_LIMIT:
            break
        method = (form.get("method") or "get").lower()
        action = urljoin(page_url or page_path, form.get("action") or page_url or page_path)
        fields, files, textareas, checkboxes, submits = _controls(form)
        operations = _operations(form, files, textareas, checkboxes, submits) if method == "post" else {}
        entry = {
            "index": index,
            "kind": _form_kind(operations) if method == "post" else "read",
            "operations": operations,
            "method": method,
            "action": action,
            "enctype": (form.get("enctype") or "").lower(),
            "fields": fields,
            "writable": method == "post" and _same_host_write(action, school_host),
            "id": _form_id(method, action, fields),
            "submits": len(submits),
        }
        if files:
            entry["file_field"] = files[0].get("name")
            entry["multiple"] = files[0].has_attr("multiple")
            entry["accept"] = squeezed(files[0].get("accept"), LABEL_LIMIT)
            entry["required"] = files[0].has_attr("required")
        if textareas:
            area = textareas[0]
            entry["text_field"] = area.get("name")
            entry["editor"] = _editor(area)
            raw = area.get_text() or ""
            entry["text"] = _plain_lines(raw) if entry["editor"] else [line for line in (squeezed(part, LINE_LIMIT) for part in raw.splitlines()) if line]
            entry["max_length"] = int(area.get("maxlength")) if str(area.get("maxlength") or "").isdigit() else 0
        if "delete" in operations:
            entry["targets"] = [
                {"name": box.get("name"), "value": box.get("value") or "on", "label": _row_label(_row_of(box, form), page_path)}
                for box in checkboxes
            ] or [{"name": "", "value": "", "label": _row_label(_row_of(form, None), page_path)}]
        forms.append(entry)
    return forms


def _unique_ids(forms):
    seen = {}
    for form in forms:
        count = seen.get(form["id"], 0)
        seen[form["id"]] = count + 1
        if count:
            form["id"] = "%s-%d" % (form["id"], count + 1)
    return forms


def _node_moment(node):
    for holder in [node] + node.find_all(True):
        for name in SORT_ATTRIBUTES:
            found = parse_moment(holder.get(name)) if holder.get(name) else ""
            if found:
                return found
    return ""


def _facts_known(facts):
    known = {START: "", DUE: "", TAGS: [], DONE: ""}
    texts = {START: "", DUE: ""}
    for fact in facts:
        key = " ".join(_words(fact["label"]))
        for field in (START, DUE, TAGS, DONE):
            if (field == TAGS and known[TAGS]) or (field != TAGS and known[field]):
                continue
            if key in COLUMN_LABELS[field] or any(_phrase_in(key, word) for word in COLUMN_LABELS[field] if len(word) >= 5):
                if field in (START, DUE):
                    moment = _node_moment(fact["node"]) or parse_moment(fact["value"])
                    if moment:
                        known[field] = moment
                        texts[field] = fact["value"]
                elif field == TAGS:
                    marked = fact["node"].find_all(class_=re.compile(r"\b(label|badge|tag)\b"))
                    values = [squeezed(item.get_text(" "), LABEL_LIMIT) for item in marked] or [squeezed(part, LABEL_LIMIT) for part in fact["node"].get_text(",").split(",")]
                    known[TAGS] = [value for index, value in enumerate(values) if value and value not in values[:index]][:TAG_LIMIT]
                else:
                    known[DONE] = fact["value"]
                break
    return known, texts


def _public_facts(facts):
    return [{"label": fact["label"], "value": fact["value"]} for fact in facts if fact["value"]]


def _section_payload(section, skip=()):
    skip = set(skip) | {entry["label"] for entry in section.links if entry["label"]}
    return {
        "text": _lines(section.raw, skip),
        "files": list(section.files),
        "images": list(section.images),
        "links": list(section.links),
        "facts": _public_facts(section.facts),
    }


def parse_task_detail(html, page_path, page_url="", school_host="", title=""):
    soup = BeautifulSoup(html or "", "html.parser")
    root = detail_root(soup)
    forms = _unique_ids(task_forms(root, page_url, page_path, school_host))
    for node in root.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()
    title_text = squeezed(title, LABEL_LIMIT)
    reader = _Reader(page_path, title_text)
    reader.walk(root)
    sections = {name: _section_payload(reader.sections[name], {title_text} if title_text else ()) for name in SECTION_ORDER}
    all_facts = [fact for name in SECTION_ORDER for fact in reader.sections[name].facts]
    known, texts = _facts_known(all_facts)
    description = sections[DESCRIPTION]
    attachments = sections[FILES]
    return {
        "sections": sections,
        "text": description["text"] + attachments["text"],
        "facts": description["facts"] + attachments["facts"],
        "files": description["files"] + attachments["files"],
        "images": description["images"] + attachments["images"],
        "links": description["links"] + attachments["links"],
        "start": known[START],
        "start_text": texts[START],
        "due": known[DUE],
        "due_text": texts[DUE],
        "tags": known[TAGS],
        "state_text": squeezed(known[DONE], LABEL_LIMIT),
        "forms": forms,
        "headings": reader.headings,
    }


def form_errors(html):
    soup = BeautifulSoup(html or "", "html.parser")
    nodes = list(soup.find_all(class_=ERROR_CLASSES))
    for holder in soup.find_all(class_=ERROR_HOLDERS):
        nodes.extend(holder.find_all(class_=ERROR_HINTS))
    texts = []
    for node in nodes:
        text = squeezed(node.get_text(" "), LABEL_LIMIT)
        if text and text not in texts and len(texts) < ERROR_LIMIT:
            texts.append(text)
    return texts


def shape_of(parsed):
    forms = []
    for form in parsed["forms"]:
        forms.append({
            "kind": form["kind"],
            "method": form["method"],
            "multipart": form["enctype"] == "multipart/form-data",
            "writable": form["writable"],
            "fields": [{"name": field["name"], "type": field["type"]} for field in form["fields"]][:FACT_LIMIT],
            "operations": sorted(form["operations"]),
            "submits": form["submits"],
            "targets": len(form.get("targets") or []),
        })
    sections = {}
    for name, payload in parsed["sections"].items():
        sections[name] = {
            "lines": len(payload["text"]),
            "files": len(payload["files"]),
            "images": len(payload["images"]),
            "links": len(payload["links"]),
            "facts": len(payload["facts"]),
        }
    return {
        "headings": list(parsed["headings"])[:FACT_LIMIT],
        "sections": sections,
        "forms": forms,
        "start": bool(parsed["start"]),
        "due": bool(parsed["due"]),
        "tags": len(parsed["tags"]),
        "state": bool(parsed["state_text"]),
    }
