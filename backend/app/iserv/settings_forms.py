import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .errors import DataError
from .forms import affirmative_submit

VISIBLE_KINDS = ("text", "email", "number", "date", "time", "datetime-local", "url", "tel", "color", "search", "textarea", "select", "checkbox", "radio")
SKIPPED_KINDS = ("hidden", "submit", "button", "reset", "image", "password", "file")
SKIPPED_ACTIONS = ("/auth/logout", "/logout", "/search")
ERROR_SELECTORS = (".invalid-feedback", ".form-error-message", ".help-block.error", ".has-error .help-block", ".alert-danger", "ul.form-errors li", ".form-error")
PROTOTYPE_MARK = "__name__"
TEXT_LIMIT = 300
LABEL_LIMIT = 160
FORM_CHANGED_KEY = "api.mail.settings.changed"
FORM_UNKNOWN_KEY = "api.mail.settings.unknown"
FORM_FIELD_KEY = "api.mail.settings.field"
ID_INDEX = re.compile(r"^\d{1,3}$")


class SettingsFormError(DataError):
    pass


def _text(node, limit=LABEL_LIMIT):
    return " ".join((node.get_text(" ") if node is not None else "").split())[:limit]


def _label(soup, form, control):
    control_id = control.get("id")
    if control_id:
        label = form.find("label", attrs={"for": control_id}) or soup.find("label", attrs={"for": control_id})
        if label is not None and _text(label):
            return _text(label)
    parent = control.find_parent("label")
    if parent is not None and _text(parent):
        return _text(parent)
    for attribute in ("aria-label", "title", "placeholder"):
        if control.get(attribute):
            return " ".join(str(control.get(attribute)).split())[:LABEL_LIMIT]
    group = control.find_parent(class_=re.compile(r"form-group|form-row|mb-3|field"))
    if group is not None:
        marked = group.find(class_=re.compile(r"label"))
        if marked is not None and _text(marked):
            return _text(marked)
    return ""


def _kind(control):
    if control.name in ("textarea", "select"):
        return control.name
    return str(control.get("type") or "text").lower()


def _options(control):
    found = []
    for option in control.find_all("option"):
        value = option.get("value")
        found.append({
            "value": value if value is not None else _text(option),
            "label": _text(option),
            "selected": option.has_attr("selected"),
        })
    return found


def _value(control, kind):
    if kind == "textarea":
        return control.get_text()
    if kind == "select":
        chosen = [option["value"] for option in _options(control) if option["selected"]]
        if control.has_attr("multiple"):
            return chosen
        options = _options(control)
        return chosen[0] if chosen else (options[0]["value"] if options else "")
    return control.get("value") or ""


def _fields(soup, form):
    visible = []
    hidden = []
    by_name = {}
    for control in form.find_all(["input", "textarea", "select"]):
        name = control.get("name")
        if not name:
            continue
        if control.find_parent(attrs={"data-prototype": True}) is not None and PROTOTYPE_MARK in name:
            continue
        kind = _kind(control)
        if kind == "hidden":
            hidden.append({"name": name, "value": control.get("value") or ""})
            continue
        if kind in SKIPPED_KINDS:
            continue
        if kind not in VISIBLE_KINDS:
            kind = "text"
        disabled = control.has_attr("disabled") or control.has_attr("readonly")
        if kind in ("checkbox", "radio"):
            choice = {"value": control.get("value") or "on", "label": _label(soup, form, control), "checked": control.has_attr("checked")}
            existing = by_name.get(name)
            if existing is not None and existing["kind"] == kind:
                existing["choices"].append(choice)
                continue
            field = {"name": name, "kind": kind, "label": "", "choices": [choice], "required": control.has_attr("required"), "disabled": disabled}
            group = control.find_parent("fieldset")
            legend = group.find("legend") if group is not None else None
            if legend is not None:
                field["label"] = _text(legend)
            by_name[name] = field
            visible.append(field)
            continue
        field = {
            "name": name,
            "kind": kind,
            "label": _label(soup, form, control),
            "value": _value(control, kind),
            "required": control.has_attr("required"),
            "disabled": disabled,
        }
        if kind == "select":
            field["options"] = _options(control)
            field["multiple"] = control.has_attr("multiple")
        for attribute in ("maxlength", "min", "max", "step"):
            if control.get(attribute):
                field[attribute] = str(control.get(attribute))
        by_name[name] = field
        visible.append(field)
    return visible, hidden


def _collections(soup, form):
    found = []
    for holder in form.find_all(attrs={"data-prototype": True}):
        prototype = BeautifulSoup(holder.get("data-prototype") or "", "html.parser")
        wrapper = prototype.new_tag("form")
        for child in list(prototype.contents):
            wrapper.append(child.extract())
        fields, _hidden = _fields(prototype, wrapper)
        if not fields:
            continue
        names = [field["name"] for field in fields]
        indexes = set()
        for control in holder.find_all(["input", "select", "textarea"]):
            name = str(control.get("name") or "")
            for pattern in names:
                head, _, tail = pattern.partition(PROTOTYPE_MARK)
                if name.startswith(head) and name.endswith(tail):
                    middle = name[len(head):len(name) - len(tail)] if tail else name[len(head):]
                    if ID_INDEX.match(middle):
                        indexes.add(int(middle))
        found.append({
            "label": _text(holder.find_previous(["legend", "label", "h2", "h3", "h4"])),
            "fields": fields,
            "next_index": max(indexes) + 1 if indexes else 0,
            "entries": sorted(indexes),
        })
    return found


def describe_forms(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    forms = []
    for index, form in enumerate(soup.find_all("form")):
        action = urljoin(base_url, form.get("action") or base_url)
        path = urlsplit(action).path
        if any(mark in path for mark in SKIPPED_ACTIONS):
            continue
        fields, hidden = _fields(soup, form)
        collections = _collections(soup, form)
        if not fields and not collections:
            continue
        submits = {}
        for control in form.find_all(["button", "input"]):
            kind = str(control.get("type") or ("submit" if control.name == "button" else "text")).lower()
            if kind == "submit" and control.get("name"):
                submits[str(control.get("name"))] = control.get("value") or ""
        heading = form.find_previous(["h1", "h2", "h3", "legend"])
        forms.append({
            "index": index,
            "name": str(form.get("name") or ""),
            "title": _text(heading),
            "action": action,
            "method": str(form.get("method") or "post").lower(),
            "fields": fields,
            "hidden": hidden,
            "collections": collections,
            "submits": submits,
        })
    return forms


def public_form(form):
    shown = {key: value for key, value in form.items() if key not in ("hidden", "action", "submits")}
    shown["has_token"] = any("token" in entry["name"].lower() for entry in form["hidden"])
    return shown


def page_title(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in ("h1", "title"):
        node = soup.find(tag)
        if node is not None and _text(node):
            return _text(node)
    return ""


def page_errors(html):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    for selector in ERROR_SELECTORS:
        for node in soup.select(selector):
            text = _text(node, TEXT_LIMIT)
            if text and text not in found:
                found.append(text)
    return found[:10]


def _allowed_name(name, form):
    known = {field["name"] for field in form["fields"]}
    if name in known:
        return True
    for collection in form["collections"]:
        for field in collection["fields"]:
            head, _, tail = field["name"].partition(PROTOTYPE_MARK)
            if name.startswith(head) and name.endswith(tail):
                middle = name[len(head):len(name) - len(tail)] if tail else name[len(head):]
                if ID_INDEX.match(middle):
                    return True
    return False


def _prototype_field(name, form):
    for collection in form["collections"]:
        for field in collection["fields"]:
            head, _, tail = field["name"].partition(PROTOTYPE_MARK)
            if name.startswith(head) and name.endswith(tail):
                return field
    return None


def _as_list(value):
    if isinstance(value, list):
        return [str(entry) for entry in value]
    if value is None or value is False:
        return []
    if value is True:
        return [""]
    return [str(value)]


def payload_for(form, values):
    values = values if isinstance(values, dict) else {}
    for name in values:
        if not _allowed_name(name, form):
            raise SettingsFormError("unknown field", message_key=FORM_FIELD_KEY, detail={"field": str(name)[:80]})
    data = [(entry["name"], entry["value"]) for entry in form["hidden"]]
    handled = set()
    for field in form["fields"]:
        name = field["name"]
        handled.add(name)
        if field.get("disabled") or (name in values and values[name] is None):
            continue
        given = values[name] if name in values else None
        if field["kind"] in ("checkbox", "radio"):
            chosen = _as_list(given) if name in values else [choice["value"] for choice in field["choices"] if choice["checked"]]
            allowed = {choice["value"] for choice in field["choices"]}
            data.extend((name, value) for value in chosen if value in allowed)
            continue
        if field["kind"] == "select":
            chosen = _as_list(given) if name in values else _as_list(field["value"])
            allowed = {option["value"] for option in field.get("options", [])}
            picked = [value for value in chosen if value in allowed]
            data.extend((name, value) for value in (picked if field.get("multiple") else picked[:1]))
            continue
        data.append((name, str(given) if name in values else str(field.get("value") or "")))
    for name, given in values.items():
        if name in handled or given is None:
            continue
        field = _prototype_field(name, form)
        if field is None:
            continue
        if field["kind"] in ("checkbox", "radio"):
            allowed = {choice["value"] for choice in field["choices"]}
            data.extend((name, value) for value in _as_list(given) if value in allowed)
        elif field["kind"] == "select":
            allowed = {option["value"] for option in field.get("options", [])}
            data.extend((name, value) for value in _as_list(given) if value in allowed)
        else:
            data.append((name, str(given)))
    data.extend(affirmative_submit(form["submits"]).items())
    return data


def stored_value(form, name):
    for field in form["fields"]:
        if field["name"] != name:
            continue
        if field["kind"] in ("checkbox", "radio"):
            return sorted(choice["value"] for choice in field["choices"] if choice["checked"])
        if field["kind"] == "select" and field.get("multiple"):
            return sorted(_as_list(field["value"]))
        return " ".join(str(field.get("value") or "").split())
    return None


def wanted_value(field_kind, multiple, given):
    if field_kind in ("checkbox", "radio") or multiple:
        return sorted(_as_list(given))
    return " ".join(str(given if given is not None else "").split())


def _entry_key(name, collection):
    for field in collection["fields"]:
        head, _, tail = field["name"].partition(PROTOTYPE_MARK)
        if name.startswith(head) and name.endswith(tail):
            middle = name[len(head):len(name) - len(tail)] if tail else name[len(head):]
            if ID_INDEX.match(middle):
                return int(middle), head, tail, field
    return None


def _entries_of(form, collection, values=None):
    rows = {}
    for field in form["fields"]:
        found = _entry_key(field["name"], collection)
        if found is None:
            continue
        index, _head, tail, template = found
        value = stored_value(form, field["name"]) if values is None else None
        rows.setdefault(index, {})[tail] = value
    if values is not None:
        for name, given in values.items():
            found = _entry_key(name, collection)
            if found is None:
                continue
            index, _head, tail, template = found
            rows.setdefault(index, {})[tail] = None if given is None else wanted_value(template["kind"], template.get("multiple"), given)
        for field in form["fields"]:
            found = _entry_key(field["name"], collection)
            if found is None or field["name"] in values:
                continue
            index, _head, tail, _template = found
            rows.setdefault(index, {})[tail] = stored_value(form, field["name"])
    kept = []
    for index in sorted(rows):
        row = rows[index]
        if any(value is None for value in row.values()):
            continue
        kept.append(tuple(sorted((tail, repr(value)) for tail, value in row.items())))
    return sorted(kept)


def unconfirmed(before, after, values):
    missing = []
    in_collection = set()
    for position, collection in enumerate(before["collections"]):
        names = [name for name in values if _entry_key(name, collection) is not None]
        names += [field["name"] for field in before["fields"] if _entry_key(field["name"], collection) is not None]
        in_collection.update(names)
        if not any(_entry_key(name, collection) is not None for name in values):
            continue
        later = after["collections"][position] if position < len(after["collections"]) else collection
        if _entries_of(before, collection, values) != _entries_of(after, later):
            missing.append(collection["label"] or "collection")
    for name, given in values.items():
        if name in in_collection or given is None:
            continue
        field = next((entry for entry in before["fields"] if entry["name"] == name), None)
        if field is None:
            continue
        kept = stored_value(after, name)
        if kept is None or kept != wanted_value(field["kind"], field.get("multiple"), given):
            missing.append(name)
    return missing


def same_shape(first, second):
    return sorted(field["name"] for field in first["fields"]) == sorted(field["name"] for field in second["fields"])
