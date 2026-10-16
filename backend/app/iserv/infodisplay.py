import re

from bs4 import BeautifulSoup

from .exercises import note_once
from .pages import path_of, squeezed

INFODISPLAY_PATH = "/iserv/infodisplay/index"
INFODISPLAY_ROOT = "/iserv/infodisplay/"
SCREEN_PATH = re.compile(r"^/iserv/infodisplay/(?:([^/?#]+)/)?show/([^/?#]+)/?$")
TITLE_LIMIT = 200
BOUNDARY_TAGS = ("li", "tr", "article")


class ScreenShapeError(ValueError):
    pass


def screen_key(path):
    match = SCREEN_PATH.match(path_of(path or "").rstrip("/"))
    if not match:
        return ""
    return match.group(2)


def _holder_text(anchor):
    node = anchor
    while node is not None and node.name not in BOUNDARY_TAGS:
        node = node.parent
    return squeezed(node.get_text(" "), TITLE_LIMIT) if node is not None else ""


def parse_screens(html, list_path=INFODISPLAY_PATH):
    soup = BeautifulSoup(html or "", "html.parser")
    root = soup.find("main") or soup.find(id="content") or soup.body or soup
    screens = {}
    order = []
    for anchor in root.find_all("a", href=True):
        path = path_of(anchor["href"]).rstrip("/")
        key = screen_key(path)
        if not key:
            continue
        title = squeezed(anchor.get_text(" "), TITLE_LIMIT) or _holder_text(anchor) or squeezed(anchor.get("title") or "", TITLE_LIMIT)
        if key not in screens:
            screens[key] = {"id": key, "title": title, "path": path}
            order.append(key)
            continue
        current = screens[key]
        plain = SCREEN_PATH.match(path).group(1) is None
        if plain and SCREEN_PATH.match(current["path"]).group(1) is not None:
            current["path"] = path
            current["title"] = title or current["title"]
        elif not current["title"] and title:
            current["title"] = title
    if not order:
        note_once("infodisplay", list_path, "no screen links")
        raise ScreenShapeError("info screen page carries no screen link")
    return {"screens": [screens[key] for key in order]}


def is_infodisplay_page(path):
    path = path_of(path or "")
    return path.rstrip("/") == INFODISPLAY_ROOT.rstrip("/") or path.startswith(INFODISPLAY_ROOT)
