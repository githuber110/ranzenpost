from bs4 import BeautifulSoup

from .listing_table import ADDRESS, addresses_in, cell_text, form_action_path, mapped_rows
from .pages import action_link, path_of, squeezed

ROOT = "/iserv/addressbook"
ROOT_SLASH = ROOT + "/"
PUBLIC_PATH = "/iserv/addressbook/public"
SKIPPED_BOOKS = frozenset({"mailinglist", "help", "export", "import"})
SEARCH_FIELD = "filter[search]"
TABLE_ID = "crud-table"
NAME = "name"
FIRST = "first"
ADDRESS_FIELD = "address"
CLASS = "class_name"
COLUMNS = {
    FIRST: ("vorname", "first name", "firstname", "given name"),
    NAME: ("name", "nachname", "last name", "lastname", "anzeigename", "display name"),
    ADDRESS_FIELD: ("e mail", "email", "mail", "e mail adresse", "adresse", "address"),
    CLASS: ("klasse", "class", "klassen", "classes", "gruppe", "group"),
}
NAME_LIMIT = 160
BOOK_LIMIT = 4


def within_addressbook(path):
    path = path_of(path or "")
    return path.rstrip("/") == ROOT or path.startswith(ROOT_SLASH)


def book_links(html, page_path):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    current = path_of(page_path).rstrip("/")
    if current == ROOT or (current.startswith(ROOT_SLASH) and len(current[len(ROOT_SLASH):].split("/")) == 1):
        found.append({"path": current, "label": squeezed((soup.find("h1") or soup.find("title") or soup).get_text(" "), NAME_LIMIT)})
    for anchor in soup.find_all("a", href=True):
        path = path_of(anchor["href"]).rstrip("/")
        if not path.startswith(ROOT_SLASH):
            continue
        rest = path[len(ROOT_SLASH):]
        if not rest or "/" in rest or rest in SKIPPED_BOOKS or action_link(path):
            continue
        if path not in [entry["path"] for entry in found]:
            found.append({"path": path, "label": squeezed(anchor.get_text(" "), NAME_LIMIT)})
    return found[:BOOK_LIMIT]


def searchable(html, page_url):
    soup = BeautifulSoup(html or "", "html.parser")
    for form in soup.find_all("form"):
        if str(form.get("method") or "get").lower() != "get":
            continue
        if form.find("input", attrs={"name": SEARCH_FIELD}) is None:
            continue
        path = form_action_path(form, page_url)
        return path if within_addressbook(path) else path_of(page_url)
    return ""


def parse_people(html):
    soup = BeautifulSoup(html or "", "html.parser")
    table = soup.find("table", id=TABLE_ID)
    if table is None:
        return None
    _labels, _mapping, rows = mapped_rows(table, COLUMNS)
    people = []
    for row, fields, extra in rows:
        holder = fields.get(ADDRESS_FIELD)
        found = addresses_in(holder) if holder is not None else []
        if not found:
            found = addresses_in(row)
        address = found[0] if found and ADDRESS.match(found[0]) else ""
        last = cell_text(fields.get(NAME), NAME_LIMIT)
        first = cell_text(fields.get(FIRST), NAME_LIMIT)
        name = squeezed(" ".join(part for part in (first, last) if part), NAME_LIMIT)
        if not name and not address:
            continue
        detail = ""
        for anchor in row.find_all("a", href=True):
            path = path_of(anchor["href"])
            if within_addressbook(path) and path.count("/") >= 4 and not action_link(path):
                detail = path
                break
        people.append({
            "name": name or address,
            "address": address,
            "class_name": cell_text(fields.get(CLASS), NAME_LIMIT),
            "extra": [entry for entry in extra if entry["value"] not in (name, address)][:6],
            "path": detail,
        })
    return people
