import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Comment, NavigableString

from .news import CATEGORY_PATH, NEWS_PATH
from .pages import action_link, path_of, squeezed

DROPPED = ("script", "style", "noscript", "template", "svg", "iframe", "nav", "form", "button", "select", "input", "textarea")
DROPPED_CLASSES = re.compile(r"\b(breadcrumb|pagination|navbar|sidebar|toolbar|btn-toolbar|btn-group|dropdown-menu|modal|sr-only|visually-hidden)\b", re.IGNORECASE)
CONTENT_CLASSES = re.compile(r"news|content|article|entry|post|panel-body|card-body", re.IGNORECASE)
BLOCKS = frozenset({
    "address", "article", "aside", "blockquote", "dd", "div", "dl", "dt", "figcaption", "figure", "footer", "h1", "h2",
    "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul",
})
FILE_PATH = re.compile(r"(^/iserv/(file|fs|storage|download)/)|(/(download|attachment|attachments|file|files)(/|$))", re.IGNORECASE)
FILE_SUFFIX = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|od[tsp]|rtf|txt|csv|zip|7z|rar|jpe?g|png|gif|webp|heic|mp3|m4a|wav|mp4|mov)$", re.IGNORECASE)
WEB = ("http", "https")
TEXT_LIMIT = 12000
LINE_LIMIT = 4000
LINK_LIMIT = 30
LABEL_LIMIT = 200


def _drop_noise(root):
    for node in root.find_all(DROPPED):
        node.decompose()
    for node in root.find_all(class_=DROPPED_CLASSES):
        if not node.decomposed:
            node.decompose()
    for node in root.find_all(string=lambda value: isinstance(value, Comment)):
        node.extract()


def _text_size(node):
    return sum(len(squeezed(paragraph.get_text(" "), LINE_LIMIT)) for paragraph in node.find_all(["p", "li", "dd", "td"])) or len(
        squeezed(node.get_text(" "), TEXT_LIMIT)
    )


def detail_root(soup):
    for tag in ("article",):
        found = soup.find(tag)
        if found is not None:
            return found
    marked = [node for node in soup.find_all(["div", "section"]) if any(CONTENT_CLASSES.search(str(name)) for name in node.get("class") or [])]
    if marked:
        return max(marked, key=_text_size)
    return soup.find("main") or soup.find(attrs={"role": "main"}) or soup.find(id="content") or soup.body or soup


def _lines(node, out):
    for child in node.children:
        if isinstance(child, NavigableString):
            out[-1] += str(child)
        elif child.name == "br":
            out.append("")
        elif child.name in BLOCKS:
            out.append("")
            _lines(child, out)
            out.append("")
        elif child.name is not None:
            _lines(child, out)


def text_lines(root, title=""):
    raw = [""]
    _lines(root, raw)
    lines = []
    used = 0
    for line in raw:
        text = squeezed(line, LINE_LIMIT)
        if not text or (not lines and text == title) or (lines and lines[-1] == text):
            continue
        if used + len(text) > TEXT_LIMIT:
            break
        lines.append(text)
        used += len(text)
    return lines


def _target(href, item_path):
    value = str(href or "").strip()
    if not value or value.startswith("#"):
        return ""
    joined = urljoin(item_path, value)
    parts = urlsplit(joined)
    if parts.scheme and parts.scheme not in WEB:
        return ""
    return joined


def _is_file(anchor, target):
    path = path_of(target)
    return anchor.has_attr("download") or bool(FILE_PATH.search(path)) or bool(FILE_SUFFIX.search(path))


def _own_page(target, item_path):
    if path_of(target).startswith("/iserv/") and action_link(target):
        return True
    path = path_of(target).rstrip("/")
    if urlsplit(target).netloc:
        return False
    return path == item_path.rstrip("/") or path == NEWS_PATH or bool(CATEGORY_PATH.match(path))


def _append(found, entry):
    if entry["href"] and entry not in found and len(found) < LINK_LIMIT:
        found.append(entry)


def parse_news_detail(html, item_path, title=""):
    soup = BeautifulSoup(html or "", "html.parser")
    root = detail_root(soup)
    _drop_noise(root)
    images = []
    files = []
    links = []
    for image in root.find_all("img"):
        target = _target(image.get("src"), item_path)
        if target and not target.startswith("data:"):
            _append(images, {"href": target, "label": squeezed(image.get("alt") or image.get("title"), LABEL_LIMIT)})
    for anchor in root.find_all("a", href=True):
        target = _target(anchor["href"], item_path)
        if not target or _own_page(target, item_path):
            continue
        label = squeezed(anchor.get_text(" ") or anchor.get("title"), LABEL_LIMIT)
        _append(files if _is_file(anchor, target) else links, {"href": target, "label": label})
    return {"lines": text_lines(root, squeezed(title, LABEL_LIMIT)), "images": images, "files": files, "links": links}


def detail_shape(html, item_path):
    soup = BeautifulSoup(html or "", "html.parser")
    root = detail_root(soup)
    _drop_noise(root)
    counted = {}
    for child in root.find_all(True):
        counted[child.name] = counted.get(child.name, 0) + 1
    parsed = parse_news_detail(str(soup), item_path)
    return {
        "tag": root.name or "document",
        "classes": [str(name) for name in root.get("class") or []][:2] if hasattr(root, "get") else [],
        "children": counted,
        "lines": len(parsed["lines"]),
        "images": len(parsed["images"]),
        "files": len(parsed["files"]),
        "links": len(parsed["links"]),
        "time_tag": root.find("time") is not None,
        "definition_list": root.find("dl") is not None,
    }
