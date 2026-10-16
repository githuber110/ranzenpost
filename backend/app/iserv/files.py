import re

from bs4 import BeautifulSoup

from .listing_table import (
    associated_controls,
    cell_moment,
    cell_text,
    form_action,
    form_action_path,
    form_by,
    hidden_pairs,
    mapped_rows,
    row_classes,
    submit_buttons,
)
from .pages import action_link, path_of, squeezed

FILE_ROOT = "/iserv/file/"
DOWNLOAD_ROOT = "/iserv/files/"
LISTING_ROOT = "/iserv/file/-/"
OWN_PATH = "/iserv/file/-/Files"
GROUPS_PATH = "/iserv/file/-/Groups"
UPLOAD_PATH = "/iserv/file/upload"
SEARCH_PATH = "/iserv/file/search"
TABLE_ID = "files"
UPLOAD_FORM_ID = "file-upload"
SEARCH_FORM_ID = "file-search"
NAME = "name"
SIZE = "size"
TYPE = "type"
MODIFIED = "modified"
COLUMNS = {
    NAME: ("name", "dateiname", "datei", "file", "filename"),
    SIZE: ("größe", "groesse", "size", "dateigröße"),
    TYPE: ("typ", "type", "art", "dateityp", "kind"),
    MODIFIED: ("letzte änderung", "änderung", "geändert", "zuletzt geändert", "last modified", "modified", "changed", "datum", "date"),
}
FOLDER_WORDS = ("ordner", "folder", "verzeichnis", "directory", "dir")
FOLDER_CLASS = re.compile(r"folder|directory")
EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,5}$")
PARENT_NAMES = ("..", ".")
NAME_LIMIT = 200
KIND_FOLDER = "folder"
KIND_FILE = "file"
ENTRY_LIMIT = 2000
CRUMB_SELECTORS = (".breadcrumb", "nav[aria-label*=readcrumb]", ".file-breadcrumb", ".path")


def within_files(path):
    path = path_of(path or "")
    return path.startswith(FILE_ROOT) or path.startswith(DOWNLOAD_ROOT) or path.rstrip("/") == FILE_ROOT.rstrip("/")


def listing_path(path):
    path = path_of(path or "")
    return within_files(path) and ".." not in path.split("/")


def own_path(path):
    path = path_of(path or "").rstrip("/")
    return path == OWN_PATH or path.startswith(OWN_PATH + "/")


def _entry_link(row, name_cell):
    holders = [(name_cell, False)] if name_cell is not None else []
    holders.append((row, True))
    for holder, strict in holders:
        for anchor in holder.find_all("a", href=True):
            path = path_of(anchor["href"])
            if not within_files(path) or (strict and action_link(path)):
                continue
            text = squeezed(anchor.get_text(" "), NAME_LIMIT) or squeezed(anchor.get("title"), NAME_LIMIT)
            return anchor, path, text
    return None, "", ""


def _is_folder(row, path, type_text):
    lowered = type_text.casefold()
    if lowered and any(word == lowered or word in lowered.split() for word in FOLDER_WORDS):
        return True
    if any(FOLDER_CLASS.search(name) for name in row_classes(row)):
        return True
    if lowered:
        return False
    leaf = path.rstrip("/").rsplit("/", 1)[-1]
    return path.startswith(LISTING_ROOT) and not EXTENSION.search(leaf)


def parse_entries(soup):
    table = soup.find("table", id=TABLE_ID)
    if table is None:
        return None, []
    labels, _mapping, rows = mapped_rows(table, COLUMNS)
    entries = []
    seen = set()
    for row, fields, extra in rows:
        anchor, path, text = _entry_link(row, fields.get(NAME))
        name = cell_text(fields.get(NAME), NAME_LIMIT) or text
        if anchor is None or not path or path in seen or not name or name in PARENT_NAMES:
            continue
        seen.add(path)
        type_text = cell_text(fields.get(TYPE), 80)
        folder = _is_folder(row, path, type_text)
        entries.append({
            "name": name,
            "kind": KIND_FOLDER if folder else KIND_FILE,
            "path": path,
            "size_text": cell_text(fields.get(SIZE), 40),
            "type_text": type_text,
            "modified": cell_moment(fields.get(MODIFIED)),
            "modified_text": cell_text(fields.get(MODIFIED), 80),
        })
        if len(entries) >= ENTRY_LIMIT:
            break
    entries.sort(key=lambda entry: (entry["kind"] != KIND_FOLDER, entry["name"].casefold()))
    return labels, entries


def _file_input(controls):
    return next((control for control in controls if control.name == "input" and str(control.get("type") or "").lower() == "file" and control.get("name")), None)


def upload_form(soup, page_url):
    form = soup.find("form", id=UPLOAD_FORM_ID) or form_by(soup, lambda node: form_action_path(node, page_url).rstrip("/") == UPLOAD_PATH)
    if form is None or str(form.get("method") or "post").lower() != "post":
        return None
    if form_action_path(form, page_url).rstrip("/") != UPLOAD_PATH:
        return None
    controls = associated_controls(soup, form)
    chooser = _file_input(controls)
    if chooser is None:
        return None
    submits = submit_buttons(controls)
    name = str(chooser.get("name"))
    return {
        "action": form_action(form, page_url),
        "file_field": name,
        "multiple": chooser.has_attr("multiple") or name.endswith("[]"),
        "accept": squeezed(chooser.get("accept"), 200),
        "hidden": hidden_pairs(controls),
        "submit": submits[0] if submits else None,
    }


def search_form(soup, page_url):
    form = soup.find("form", id=SEARCH_FORM_ID) or form_by(soup, lambda node: form_action_path(node, page_url).rstrip("/") == SEARCH_PATH)
    if form is None or form_action_path(form, page_url).rstrip("/") != SEARCH_PATH:
        return None
    controls = associated_controls(soup, form)
    field = next(
        (
            control for control in controls
            if control.name == "input" and control.get("name")
            and (str(control.get("type") or "").lower() == "search" or str(control.get("name")).endswith("[search]"))
        ),
        None,
    )
    if field is None:
        return None
    submits = [pair for pair in submit_buttons(controls) if "[actions]" not in pair[0]]
    return {
        "action": form_action(form, page_url),
        "method": str(form.get("method") or "post").lower(),
        "field": str(field.get("name")),
        "hidden": hidden_pairs(controls),
        "submit": submits[0] if submits else None,
    }


def crumbs(soup):
    found = []
    for selector in CRUMB_SELECTORS:
        for holder in soup.select(selector):
            for anchor in holder.find_all("a", href=True):
                path = path_of(anchor["href"]).rstrip("/")
                name = squeezed(anchor.get_text(" "), NAME_LIMIT)
                if name and listing_path(path) and path not in [entry["path"] for entry in found]:
                    found.append({"name": name, "path": path})
        if found:
            return found
    return found


def location(soup):
    for name in ("upload[path]", "form[path]", "search[path]"):
        holder = soup.find("input", attrs={"name": name})
        if holder is not None and holder.get("value"):
            return squeezed(holder.get("value"), 400)
    return ""


def parse_listing(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    labels, entries = parse_entries(soup)
    upload = upload_form(soup, page_url)
    search = search_form(soup, page_url)
    return {
        "framed": labels is not None or upload is not None,
        "entries": entries,
        "labels": labels or [],
        "upload": upload,
        "search": search,
        "crumbs": crumbs(soup),
        "location": location(soup),
    }
