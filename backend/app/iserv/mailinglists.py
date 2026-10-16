import hashlib
import re

from bs4 import BeautifulSoup

from .listing_table import (
    addresses_in,
    associated_controls,
    cell_text,
    control_label,
    form_action,
    form_action_path,
    hidden_pairs,
    mapped_rows,
    submit_buttons,
)
from .pages import action_link, path_of, squeezed

LIST_PATH = "/iserv/mailinglist"
LIST_ROOT = LIST_PATH + "/"
TABLE_ID = "crud-table"
TITLE = "title"
COLUMNS = {TITLE: ("titel", "title", "name", "bezeichnung", "liste", "list")}
UPLOAD_SUFFIX = "[upload]"
DELETE_MARK = "[delete]"
CONFIRM_SUFFIX = "/confirm"
NEGATIVE_WORDS = frozenset({"cancel", "abort", "back", "abbrechen", "zurück", "nein", "no"})
POSITIVE_WORDS = frozenset({"delete", "confirm", "remove", "yes", "löschen", "bestätigen", "entfernen", "ja"})
ID_KINDS = ("hidden", "checkbox", "radio", "text")
DIGIT = re.compile(r"\d")
NAME_WORDS = re.compile(r"[^\W\d_]+")
TITLE_LIMIT = 200
ADDRESS_LIMIT = 2000
TEXT_KINDS = ("text", "search", "email", "")
CONTENT_SELECTORS = ("main", "#content", ".content", ".container-fluid", "body")
SKIPPED_PARTS = ("header", "nav", "footer", "aside")


def within_lists(path):
    path = path_of(path or "")
    return path.rstrip("/") == LIST_PATH or path.startswith(LIST_ROOT)


def _row_box(row, soup, form):
    ident = form.get("id") if form is not None else None
    for box in row.find_all("input", attrs={"type": "checkbox"}):
        if not box.get("name") or not box.get("value"):
            continue
        if form is not None and (box.find_parent("form") is form or (ident and box.get("form") == ident)):
            return str(box.get("name")), str(box.get("value"))
        if form is None:
            return str(box.get("name")), str(box.get("value"))
    return None


def _detail_path(row):
    for anchor in row.find_all("a", href=True):
        path = path_of(anchor["href"]).rstrip("/")
        if within_lists(path) and path.rstrip("/") != LIST_PATH and not action_link(path):
            return path
    return ""


def _list_id(box, detail, title):
    if box is not None:
        return box[1]
    if detail:
        return detail
    return "h" + hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def delete_form(soup, page_url):
    for form in soup.find_all("form"):
        if str(form.get("method") or "post").lower() != "post":
            continue
        path = form_action_path(form, page_url)
        if not within_lists(path) or not path.rstrip("/").endswith(CONFIRM_SUFFIX):
            continue
        controls = associated_controls(soup, form)
        button = next((pair for pair in submit_buttons(controls) if DELETE_MARK in pair[0]), None)
        if button is None:
            continue
        return form, {"action": form_action(form, page_url), "hidden": hidden_pairs(controls), "button": button}
    return None, None


def import_form(soup, page_url):
    for form in soup.find_all("form"):
        if str(form.get("method") or "post").lower() != "post":
            continue
        if not within_lists(form_action_path(form, page_url)):
            continue
        controls = associated_controls(soup, form)
        chooser = next(
            (
                control for control in controls
                if control.name == "input" and str(control.get("type") or "").lower() == "file"
                and str(control.get("name") or "").endswith(UPLOAD_SUFFIX)
            ),
            None,
        )
        if chooser is None:
            continue
        texts = []
        for control in controls:
            kind = str(control.get("type") or "").lower()
            if control.name != "input" or kind not in TEXT_KINDS or not control.get("name"):
                continue
            texts.append({
                "name": str(control.get("name")),
                "label": control_label(soup, form, control),
                "required": control.has_attr("required"),
                "value": str(control.get("value") or ""),
                "maxlength": str(control.get("maxlength") or ""),
            })
        submits = submit_buttons(controls)
        return {
            "action": form_action(form, page_url),
            "file_field": str(chooser.get("name")),
            "file_label": control_label(soup, form, chooser),
            "accept": squeezed(chooser.get("accept"), 200),
            "texts": texts,
            "hidden": hidden_pairs(controls),
            "submit": submits[0] if submits else None,
        }
    return None


def parse_overview(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.find("table", id=TABLE_ID)
    form, remover = delete_form(soup, page_url)
    lists = []
    if table is not None:
        labels, _mapping, rows = mapped_rows(table, COLUMNS)
        seen = set()
        for row, fields, extra in rows:
            title = cell_text(fields.get(TITLE), TITLE_LIMIT)
            detail = _detail_path(row)
            if not title and detail:
                anchor = next((item for item in row.find_all("a", href=True) if path_of(item["href"]).rstrip("/") == detail), None)
                title = squeezed(anchor.get_text(" "), TITLE_LIMIT) if anchor is not None else ""
            box = _row_box(row, soup, form)
            if not title:
                continue
            ident = _list_id(box, detail, title)
            if ident in seen:
                continue
            seen.add(ident)
            lists.append({
                "id": ident,
                "title": title,
                "extra": extra[:6],
                "path": detail,
                "box": list(box) if box is not None and form is not None else None,
            })
    else:
        labels = None
    return {
        "framed": table is not None,
        "lists": lists,
        "labels": labels or [],
        "importer": import_form(soup, page_url),
        "remover": remover,
    }


def _negative(pair):
    words = set(NAME_WORDS.findall(pair[0].casefold())) | set(NAME_WORDS.findall(pair[1].casefold()))
    return bool(words & NEGATIVE_WORDS)


def _positive(pair):
    words = set(NAME_WORDS.findall(pair[0].casefold())) | set(NAME_WORDS.findall(pair[1].casefold()))
    return bool(words & POSITIVE_WORDS) and not words & NEGATIVE_WORDS


def _id_values(controls):
    found = set()
    for control in controls:
        if control.name != "input" or str(control.get("type") or "text").lower() not in ID_KINDS:
            continue
        name = str(control.get("name") or "")
        value = str(control.get("value") or "")
        if name and "token" not in name.casefold() and DIGIT.search(value):
            found.add(value)
    return found


def follow_up_form(html, page_url, ident, first_action, known_ids):
    soup = BeautifulSoup(html or "", "html.parser")
    first = path_of(first_action).rstrip("/")
    others = {str(value) for value in known_ids or ()} - {ident}
    for form in soup.find_all("form"):
        if str(form.get("method") or "post").lower() != "post":
            continue
        path = form_action_path(form, page_url).rstrip("/")
        if not within_lists(path) or path == first or path.endswith(CONFIRM_SUFFIX):
            continue
        controls = associated_controls(soup, form)
        if any(control.name == "input" and str(control.get("type") or "").lower() == "file" for control in controls):
            continue
        values = _id_values(controls)
        if not ident or values != {ident} or values & others:
            continue
        buttons = [pair for pair in submit_buttons(controls) if _positive(pair)]
        chosen = [
            (str(control.get("name")), str(control.get("value") or "on"))
            for control in controls
            if control.name == "input" and str(control.get("type") or "").lower() in ("checkbox", "radio")
            and control.get("name") and control.has_attr("checked")
        ]
        pairs = hidden_pairs(controls) + chosen
        if not buttons or not any(value == ident for _name, value in pairs):
            continue
        return {"action": form_action(form, page_url), "pairs": pairs + [buttons[0]]}
    return None


def _content(soup):
    for selector in CONTENT_SELECTORS:
        found = soup.select_one(selector)
        if found is not None:
            return found
    return soup


def parse_detail(html):
    soup = BeautifulSoup(html or "", "html.parser")
    content = _content(soup)
    for part in content.find_all(SKIPPED_PARTS):
        part.decompose()
    for form in content.find_all("form"):
        if "logout" in str(form.get("action") or ""):
            form.decompose()
    heading = content.find("h1") or soup.find("h1")
    return {
        "title": squeezed(heading.get_text(" "), TITLE_LIMIT) if heading is not None else "",
        "addresses": addresses_in(content)[:ADDRESS_LIMIT],
    }
