import hashlib
import json

from bs4 import BeautifulSoup

from .exercises import header_labels, note_once
from .listing_table import body_rows, cell_moment, cell_text, column_map, row_cells
from .pages import action_link, path_of, squeezed

WHITEBOARDS_PATH = "/iserv/excalidraw/"
WHITEBOARDS_ROOT = "/iserv/excalidraw"
TITLE = "title"
OWNER = "owner"
CREATED = "created"
CHANGED = "changed"
COLUMNS = {
    TITLE: ("titel", "title", "name", "bezeichnung", "tafel", "whiteboard"),
    OWNER: ("besitzer", "eigentümer", "owner", "ersteller", "erstellt von", "autor", "author", "creator", "created by"),
    CREATED: ("erstellt", "angelegt", "created"),
    CHANGED: ("geändert", "letzte änderung", "aktualisiert", "bearbeitet", "changed", "modified", "updated", "last change"),
}
RESERVED = frozenset({"add", "new", "create", "delete", "index", "list", "show", "edit", "open", "view", "api", "id"})
TITLE_LIMIT = 200
LABEL_LIMIT = 80
TEXT_LIMIT = 120


class WhiteboardShapeError(ValueError):
    pass


def is_whiteboard_page(path):
    path = path_of(path or "")
    return path.rstrip("/") == WHITEBOARDS_ROOT or path.startswith(WHITEBOARDS_ROOT + "/")


def whiteboard_key(path):
    path = path_of(path or "").rstrip("/")
    if not path.startswith(WHITEBOARDS_ROOT + "/"):
        return ""
    for segment in path[len(WHITEBOARDS_ROOT) + 1:].split("/"):
        if segment and segment.lower() not in RESERVED:
            return segment
    return ""


def _board_table(soup):
    for table in soup.find_all("table"):
        if TITLE in column_map(header_labels(table), COLUMNS).values():
            return table
    return None


def _board_path(row):
    for anchor in row.find_all("a", href=True):
        path = path_of(anchor["href"]).rstrip("/")
        if whiteboard_key(path) and not action_link(path):
            return path
    return ""


def _embedded_list(soup):
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        try:
            value = json.loads(script.string or "")
        except ValueError:
            continue
        if isinstance(value, list) or (isinstance(value, dict) and isinstance(value.get("data"), list)):
            return True
    return False


def _box_value(row):
    for box in row.find_all("input", attrs={"type": "checkbox"}):
        if box.get("name") and box.get("value"):
            return str(box.get("value"))
    return ""


def _board(row, fields):
    path = _board_path(row)
    title = cell_text(fields.get(TITLE), TITLE_LIMIT)
    if not title and path:
        anchor = next((item for item in row.find_all("a", href=True) if path_of(item["href"]).rstrip("/") == path), None)
        title = squeezed(anchor.get_text(" "), TITLE_LIMIT) if anchor is not None else ""
    if not title and not path:
        return None
    owner = cell_text(fields.get(OWNER), LABEL_LIMIT)
    created_text = cell_text(fields.get(CREATED), TEXT_LIMIT)
    key = _box_value(row) or whiteboard_key(path)
    if not key:
        digest = hashlib.sha256("\n".join((title, owner, created_text)).encode("utf-8")).hexdigest()
        key = "h" + digest[:16]
    return {
        "id": key,
        "title": title,
        "owner": owner,
        "created": cell_moment(fields.get(CREATED)),
        "created_text": created_text,
        "changed": cell_moment(fields.get(CHANGED)),
        "changed_text": cell_text(fields.get(CHANGED), TEXT_LIMIT),
        "path": path,
    }


def parse_whiteboards(html, list_path=WHITEBOARDS_PATH):
    soup = BeautifulSoup(html or "", "html.parser")
    table = _board_table(soup)
    if table is None:
        note_once("excalidraw", list_path, "no whiteboard table")
        raise WhiteboardShapeError("whiteboard page carries no whiteboard table")
    mapping = column_map(header_labels(table), COLUMNS)
    boards = []
    seen = set()
    messages = 0
    skipped = 0
    duplicates = 0
    for row in body_rows(table):
        if len(row.find_all(["td", "th"], recursive=False)) == 1:
            messages += 1
            continue
        cells = row_cells(row)
        fields = {mapping[index]: cell for index, cell in enumerate(cells) if cell is not None and index in mapping}
        board = _board(row, fields)
        if board is None:
            skipped += 1
            continue
        if board["id"] in seen:
            duplicates += 1
            continue
        seen.add(board["id"])
        boards.append(board)
    if not boards and _embedded_list(soup):
        note_once("excalidraw", list_path, "notice row beside embedded list data")
        raise WhiteboardShapeError("whiteboard page carries list data outside the table")
    if duplicates:
        note_once("excalidraw", list_path, "dropped %d whiteboard rows with a repeated id" % duplicates)
    if not boards and (skipped or not messages):
        note_once("excalidraw", list_path, "%d whiteboard rows unreadable" % skipped if skipped else "no rows and no empty notice")
        raise WhiteboardShapeError("whiteboard table carries no readable row")
    if skipped:
        note_once("excalidraw", list_path, "skipped %d unreadable whiteboard rows" % skipped)
    return {"whiteboards": boards}
