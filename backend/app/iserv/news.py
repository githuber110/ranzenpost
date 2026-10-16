import re

from bs4 import BeautifulSoup

from .exercises import page_links, parse_moment
from .pages import path_of, squeezed

NEWS_PATH = "/iserv/news"
NEWS_ROOT = NEWS_PATH + "/"
ITEM_PATH = re.compile(r"^/iserv/news/([^/?#]+)/(\d+)/?$")
CATEGORY_PATH = re.compile(r"^/iserv/news/([^/?#]+)/?$")
HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
TITLE_CLASSES = re.compile(r"\b(title|heading|headline|subject)\b", re.IGNORECASE)
DATE_CLASSES = re.compile(r"\b(date|time|published|meta|info)\b", re.IGNORECASE)
META_CLASSES = re.compile(r"\b(text-muted|muted|byline|subtitle|caption|footer|small)\b", re.IGNORECASE)
META_TAGS = ("small", "footer")
BOUNDARY_TAGS = frozenset({"li", "article", "tr"})
BOUNDARY_CLASSES = re.compile(r"^(panel|card|media|list-group-item|news-item|news-entry|item|entry|post)$", re.IGNORECASE)
PAGE_PARTS = ("form", "nav", "h1")
NEWS_MARK = re.compile(r"news", re.IGNORECASE)
SECTION_WORDS = {
    "archive": ("archiv", "archive", "archived", "archiviert"),
    "packages": ("paketnews", "paket news", "paket-news", "package news", "packages", "pakete"),
}
SECTIONS = tuple(SECTION_WORDS)
TITLE_LIMIT = 300
TEXT_LIMIT = 1000
LABEL_LIMIT = 120


def _item_paths(anchor):
    path = path_of(anchor.get("href") or "")
    return path.rstrip("/") if ITEM_PATH.match(path) else ""


def _item_hrefs(node):
    return {path for path in (_item_paths(anchor) for anchor in node.find_all("a", href=True)) if path}


def _boundary(node):
    return node.name in BOUNDARY_TAGS or any(BOUNDARY_CLASSES.search(str(name)) for name in node.get("class") or [])


def _page_part(node):
    return node.find(PAGE_PARTS) is not None


def _container(anchor, path, stop):
    node = anchor
    while node.parent is not None and node.parent is not stop and not _boundary(node):
        if _item_hrefs(node.parent) - {path} or _page_part(node.parent):
            break
        node = node.parent
    return node


def _title(container, path):
    for holder in container.find_all(list(HEADINGS)) + container.find_all(class_=TITLE_CLASSES):
        text = squeezed(holder.get_text(" "), TITLE_LIMIT)
        if text:
            return text
    texts = [
        squeezed(anchor.get_text(" "), TITLE_LIMIT)
        for anchor in container.find_all("a", href=True)
        if _item_paths(anchor) == path
    ]
    texts = [text for text in texts if text]
    return max(texts, key=len) if texts else ""


def _date(container):
    for holder in container.find_all("time"):
        found = parse_moment(holder.get("datetime")) or parse_moment(holder.get_text(" "))
        if found:
            return found, squeezed(holder.get_text(" "), LABEL_LIMIT)
    for holder in container.find_all(class_=DATE_CLASSES):
        text = squeezed(holder.get_text(" "), LABEL_LIMIT)
        found = parse_moment(text)
        if found:
            return found, text
    for holder in container.find_all(META_TAGS) + container.find_all(class_=META_CLASSES):
        text = squeezed(holder.get_text(" "), LABEL_LIMIT)
        found = parse_moment(text)
        if found:
            return found, text
    return "", ""


def _category(container, slug):
    for anchor in container.find_all("a", href=True):
        match = CATEGORY_PATH.match(path_of(anchor["href"]))
        if match and match.group(1) == slug:
            text = squeezed(anchor.get_text(" "), LABEL_LIMIT)
            if text:
                return text
    return ""


def _summary(container, title):
    parts = []
    for paragraph in container.find_all("p"):
        text = squeezed(paragraph.get_text(" "), TEXT_LIMIT)
        if text and text != title and text not in parts:
            parts.append(text)
    return squeezed(" ".join(parts), TEXT_LIMIT)


def _item_containers(soup):
    stop = soup.find("main") or soup.body or soup
    seen = set()
    for anchor in soup.find_all("a", href=True):
        path = _item_paths(anchor)
        if not path or path in seen:
            continue
        seen.add(path)
        yield path, _container(anchor, path, stop)


def first_item_shape(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for path, container in _item_containers(soup):
        slug = ITEM_PATH.match(path).group(1)
        counted = {}
        for child in container.find_all(True):
            counted[child.name] = counted.get(child.name, 0) + 1
        moment, _text = _date(container)
        return {
            "tag": container.name,
            "classes": [str(name) for name in container.get("class") or []][:2],
            "children": counted,
            "title": bool(_title(container, path)),
            "date": bool(moment),
            "time_tag": container.find("time") is not None,
            "category": bool(_category(container, slug)),
        }
    return None


def _news_marked(node):
    names = [str(name) for name in node.get("class") or []] + [str(node.get("id") or "")]
    return any(NEWS_MARK.search(name) for name in names if name)


def list_frame(soup):
    for anchor in soup.find_all("a", href=True):
        if CATEGORY_PATH.match(path_of(anchor["href"])):
            return True
    for form in soup.find_all("form"):
        if path_of(form.get("action") or "").startswith(NEWS_ROOT) or path_of(form.get("action") or "").rstrip("/") == NEWS_PATH:
            return True
    if soup.find(class_=re.compile(r"\bpagination\b")) is not None:
        return True
    return any(_news_marked(node) for node in soup.find_all(True))


def _section_of(text):
    key = " ".join(str(text or "").casefold().replace("-", " ").replace("_", " ").split())
    for section, words in SECTION_WORDS.items():
        if key in words or any(word in key.split() for word in words if " " not in word):
            return section
    return None


def section_links(html):
    soup = BeautifulSoup(html or "", "html.parser")
    found = {}
    for anchor in soup.find_all("a", href=True):
        path = path_of(anchor["href"]).rstrip("/")
        match = CATEGORY_PATH.match(path)
        if not match:
            continue
        section = _section_of(match.group(1)) or _section_of(anchor.get_text(" "))
        if section is not None and section not in found:
            found[section] = path
    return found


def parse_news(html, list_path=NEWS_PATH):
    soup = BeautifulSoup(html or "", "html.parser")
    items = []
    for path, container in _item_containers(soup):
        match = ITEM_PATH.match(path)
        title = _title(container, path)
        moment, date_text = _date(container)
        slug = match.group(1)
        items.append(
            {
                "id": slug + "/" + match.group(2),
                "title": title,
                "date": moment,
                "date_text": date_text,
                "category": _category(container, slug),
                "category_slug": slug,
                "summary": _summary(container, title),
                "path": path,
            }
        )
    return {"items": items, "pages": page_links(soup, list_path), "framed": bool(items) or list_frame(soup)}


def is_news_page(path):
    path = path_of(path or "")
    return path.rstrip("/") == NEWS_PATH or path.startswith(NEWS_ROOT)
