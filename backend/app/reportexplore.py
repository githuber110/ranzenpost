import re
from collections import namedtuple
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

from . import valueshape
from .module_catalogue import slug_of
from .pageshape import code_text, label_shape, visible_text
from .pathpattern import path_only, placeholders
from .scriptscan import EXPR
from .vocabulary import known_header_word

ROOT = "/iserv/"
ModuleRule = namedtuple(
    "ModuleRule",
    "routes details depth free_after first_free never max_ids forms scripts apis join rows media frames",
    defaults=(frozenset(), False, 1, frozenset(), False, frozenset(), None, frozenset(), 0, False, False, False, False, False),
)


def _words(text):
    return frozenset(str(text).split())


DETAIL_ROUTES = "show view detail details overview index list"
RULES = {
    "file": ModuleRule(
        routes=_words("- groups files folder cloud index"), depth=2, free_after=_words("groups"),
        never=_words("download zip unzip preview thumbnail export share"), max_ids=1,
    ),
    "addressbook": ModuleRule(
        routes=_words(DETAIL_ROUTES + " public private personal contact contacts add edit mailinglist"), details=True, depth=2,
        never=_words("export download vcard import"), max_ids=1, forms=_words("edit"),
    ),
    "todo": ModuleRule(routes=_words("home lists tasks api"), scripts=16, apis=True),
    "course-selection": ModuleRule(
        routes=_words(DETAIL_ROUTES + " choice choices selection selections election elections result results course courses"),
        details=True, depth=2, never=_words("export download"), max_ids=1, scripts=16, apis=True,
    ),
    "forum": ModuleRule(
        routes=_words("unread settings group overview index forum forums list"), depth=2, free_after=_words("group"),
        never=_words("topic topics thread threads post posts reply replies answer last read markread"), max_ids=1,
    ),
    "poll": ModuleRule(
        routes=_words(DETAIL_ROUTES + " participate participation result results"), details=True, depth=2,
        never=_words("vote export download"), max_ids=1, scripts=16, apis=True,
    ),
    "poll-quick": ModuleRule(
        routes=_words(DETAIL_ROUTES + " participate participation result results"), details=True, depth=2,
        never=_words("vote export download"), max_ids=1, scripts=16, apis=True,
    ),
    "etherpad": ModuleRule(
        routes=_words("show view pad pads add index list"), details=True, first_free=True,
        never=_words("export download timeslider import"), max_ids=1,
    ),
    "excalidraw": ModuleRule(
        routes=_words("show view board boards api add index list"), details=True, first_free=True,
        never=_words("export download"), max_ids=1, scripts=16, apis=True,
    ),
    "mailinglist": ModuleRule(
        routes=_words(DETAIL_ROUTES + " add edit import"), details=True, depth=2, first_free=True,
        never=_words("export download"), max_ids=1, forms=_words("edit"),
    ),
    "print": ModuleRule(
        routes=_words(DETAIL_ROUTES + " job jobs history credit credits redeem printer printers queue"), details=True, depth=2,
        never=_words("download cancel pdf"), max_ids=1, scripts=16, apis=True,
    ),
    "videoconference": ModuleRule(
        routes=_words("room rooms overview index list"), never=_words("join start enter guest invite end leave meeting create bbb"),
        scripts=16, apis=True, join=True, rows=True,
    ),
    "infodisplay": ModuleRule(routes=_words("show view display"), details=True, media=True),
    "methodenguide": ModuleRule(media=True, frames=True),
}
APP_API_WORDS = _words(
    "lists list tasks todos boards rooms polls jobs printers credit balance slides screens displays contacts choices "
    "selections elections courses items entries tags folders settings overview"
)
FRAME_TAGS = ("iframe", "frame")
ID_LIKE = re.compile(r"^(?=[^/]*\d)[A-Za-z0-9_.~$-]{4,64}$")
WORD_SPLIT = re.compile(r"[^a-z]+")
APP_ROOT_IDS = ("app", "root", "application")
APP_ROOT_ENDINGS = ("-app", "_app", "-root")
APP_ROOT_MARKS = ("data-v-app", "data-reactroot")
JOIN_MARKS = ("join", "bigbluebutton", "/bbb")
JOIN_ATTRIBUTES = ("href", "data-href", "data-url", "data-join-url", "data-link", "action", "formaction")
MAX_JOIN_SHAPES = 6
MAX_ROW_TABLES = 3
MAX_ROW_TEXTS = 10
ROW_TEXT_CHARS = 80
SOURCE_TAGS = ("iframe", "frame", "object", "embed", "img", "video", "audio", "source")
MAX_SOURCES = 20
FRAME_SOURCES = ("'self'", "'none'", "*", "https:")
FRAME_OPTIONS = ("DENY", "SAMEORIGIN", "ALLOW-FROM")
NOTICE_CLASSES = frozenset({"alert", "card", "panel", "widget", "notice", "callout", "well", "box", "jumbotron", "toast"})
NOTICE_ROLES = ("alert", "status")
NAVIGATION_MARK = re.compile(r"nav|sidebar|menu", re.IGNORECASE)
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
HEADING_CLASSES = ("panel-heading", "panel-title", "card-header", "card-title", "alert-heading")
MAX_NOTICE_BLOCKS = 20
MAX_NOTICE_LINKS = 8


def as_prefixes(prefix):
    return tuple(prefix) if isinstance(prefix, (tuple, list)) else (prefix,)


def prefix_rest(path, prefix):
    for candidate in sorted(as_prefixes(prefix), key=len, reverse=True):
        if path.startswith(candidate):
            return path[len(candidate):]
    return None


def first_segment(prefix, root=ROOT):
    text = str(prefix or "")
    if not text.startswith(root):
        return ""
    return text[len(root):].split("/", 1)[0].strip().lower()


def rule_for(prefix, root=ROOT):
    for candidate in as_prefixes(prefix):
        segment = first_segment(candidate, root)
        rule = RULES.get(slug_of(segment) or segment)
        if rule is not None:
            return rule
    return None


def part_words(part):
    return frozenset(word for word in WORD_SPLIT.split(unquote(part).casefold()) if word)


def never_hit(rule, part):
    return rule is not None and bool(part_words(part) & rule.never)


def free_part(rule, previous, position, part):
    if rule is None:
        return False
    decoded = unquote(part)
    if "/" in decoded or "\\" in decoded or decoded.strip() in (".", "..") or any(word in decoded.casefold() for word in rule.never):
        return False
    if previous in rule.free_after:
        return True
    return position == 0 and rule.first_free and bool(ID_LIKE.match(decoded))


def free_shape(path, prefix, rule):
    rest = prefix_rest(path, prefix)
    if rule is None or rest is None:
        return None
    shaped = []
    previous = ""
    for position, part in enumerate(part for part in rest.split("/") if part):
        shaped.append("<id>" if free_part(rule, previous, position, part) else part)
        previous = part.casefold()
    return path[:len(path) - len(rest)] + "/".join(shaped)


def _same_host_path(target, page_url, root=ROOT):
    page = urlsplit(page_url or "")
    parts = urlsplit(urljoin(page_url or "", str(target or "").strip()))
    if parts.scheme not in ("http", "https") or parts.netloc.lower() != page.netloc.lower() or not parts.path.startswith(root):
        return ""
    return parts.path


def alias_prefixes(primary, html, page_url, root=ROOT):
    segment = first_segment(primary, root)
    own = slug_of(segment)
    found = [primary]
    if not own:
        return tuple(found)
    for tag in BeautifulSoup(html or "", "html.parser").find_all(("a", "form")):
        path = _same_host_path(tag.get("href") if tag.name == "a" else tag.get("action"), page_url, root)
        other = first_segment(path, root)
        if other and other != segment and slug_of(other) == own:
            candidate = root + other + "/"
            if candidate not in found:
                found.append(candidate)
    return tuple(found)


def app_bases(html, page_url, prefix, root=ROOT):
    bases = []
    tag = BeautifulSoup(html or "", "html.parser").find("base", href=True)
    path = _same_host_path(tag.get("href"), page_url, root) if tag is not None else ""
    if path:
        bases.append(path if path.endswith("/") else path + "/")
    for candidate in as_prefixes(prefix):
        if candidate not in bases:
            bases.append(candidate)
    return bases, bool(path)


def resolved_paths(pattern, bases, root=ROOT):
    text = str(pattern or "")
    relative = text.startswith(EXPR)
    if relative:
        text = text[len(EXPR):]
    if "<" in text or "?" in text or not text.startswith("/"):
        return []
    if text.startswith(root):
        return [text]
    if not relative and not text.startswith("/api/"):
        return []
    return [base.rstrip("/") + text for base in bases]


def app_root_line(html):
    for node in BeautifulSoup(html or "", "html.parser").find_all(True):
        ident = str(node.get("id") or "").strip()
        lowered = ident.casefold()
        marked = any(node.has_attr(mark) for mark in APP_ROOT_MARKS)
        if marked or lowered in APP_ROOT_IDS or (ident and lowered.endswith(APP_ROOT_ENDINGS)):
            label = node.name + ("#" + code_text(placeholders(ident)) if ident else "")
            return "- App root: %s, children %d" % (label, len(node.find_all(True, recursive=False)))
    return ""


def _join_target(node):
    for name in JOIN_ATTRIBUTES:
        value = str(node.get(name) or "").strip()
        if value and any(mark in value.casefold() for mark in JOIN_MARKS):
            return value
    return ""


def join_lines(html, page_url, link_shape):
    page = urlsplit(page_url or "")
    same = []
    other = 0
    for node in BeautifulSoup(html or "", "html.parser").find_all(True):
        value = _join_target(node)
        if not value:
            continue
        target = urlsplit(urljoin(page_url or "", value))
        if target.netloc.lower() != page.netloc.lower():
            other += 1
            continue
        same.append(link_shape(target.path))
    total = len(same) + other
    if not total:
        return ["- Join targets: none in the page"]
    shapes = []
    for shape in same:
        if shape not in shapes:
            shapes.append(shape)
    shown = " | ".join(shapes[:MAX_JOIN_SHAPES]) or "-"
    return ["- Join targets: %d, same host %d (%s), other host %d, never opened" % (total, len(same), shown, other)]


def _cell_text(cell):
    return visible_text(" ".join(cell.get_text(" ").split()), known_header_word)[:ROW_TEXT_CHARS]


def row_text_lines(html):
    lines = []
    for number, table in enumerate(BeautifulSoup(html or "", "html.parser").find_all("table")[:MAX_ROW_TABLES], 1):
        rows = []
        for row in table.find_all("tr")[:MAX_ROW_TEXTS]:
            cells = [_cell_text(cell) for cell in row.find_all(("td", "th"), recursive=False)]
            rows.append(" / ".join(cell or "-" for cell in cells) or "-")
        if rows:
            lines.append("- Table %d row texts: %s" % (number, " ; ".join(rows)))
    return lines


def _source_value(node):
    return str(node.get("src") or node.get("data") or "").strip()


def embedded_sources(html, page_url, link_shape):
    page = urlsplit(page_url or "")
    shown = []
    own = []
    for node in BeautifulSoup(html or "", "html.parser").find_all(SOURCE_TAGS):
        value = _source_value(node)
        if not value or value.startswith(("data:", "blob:", "javascript:")):
            continue
        target = urlsplit(urljoin(page_url or "", value))
        if target.scheme not in ("http", "https"):
            continue
        if target.netloc.lower() == page.netloc.lower():
            entry = "%s %s" % (node.name, link_shape(target.path))
            if node.name in FRAME_TAGS and not target.query and target.path.startswith(ROOT) and target.path not in own:
                own.append(target.path)
        else:
            entry = "%s <other host>%s" % (node.name, valueshape.link_shape(target.path))
        if entry not in shown:
            shown.append(entry)
    if not shown:
        return [], own
    return ["- Embedded sources: " + " | ".join(shown[:MAX_SOURCES])], own


def first_foreign_frame(html, page_url):
    page = urlsplit(page_url or "")
    for node in BeautifulSoup(html or "", "html.parser").find_all(("iframe", "frame")):
        value = _source_value(node)
        target = urlsplit(urljoin(page_url or "", value)) if value else None
        if target is not None and target.scheme == "https" and target.netloc and target.netloc.lower() != page.netloc.lower():
            return target.geturl().split("#", 1)[0]
    return ""


def _frame_option(value):
    word = str(value or "").strip().split()[0].upper() if str(value or "").strip() else ""
    return word.lower() if word in FRAME_OPTIONS else ("other" if word else "not set")


def _frame_ancestors(policy):
    for directive in str(policy or "").split(";"):
        parts = directive.split()
        if parts and parts[0].lower() == "frame-ancestors":
            sources = [part if part.lower() in FRAME_SOURCES else "<host>" for part in parts[1:]]
            return " ".join(sources) or "empty"
    return "not set"


def frame_line(answer):
    headers = getattr(answer, "headers", None) or {}
    options = headers.get("X-Frame-Options") or headers.get("x-frame-options")
    policy = headers.get("Content-Security-Policy") or headers.get("content-security-policy")
    return "- Framing: x-frame-options %s, frame-ancestors %s" % (_frame_option(options), _frame_ancestors(policy))


def _in_navigation(node):
    for parent in node.parents:
        if getattr(parent, "name", None) is None:
            continue
        if parent.name == "nav" or str(parent.get("role") or "").lower() == "navigation":
            return True
        marks = [str(parent.get("id") or "")] + [str(name) for name in parent.get("class") or []]
        if any(NAVIGATION_MARK.search(mark) for mark in marks):
            return True
    return False


def _notice_block(node):
    classes = {str(name).casefold() for name in node.get("class") or []}
    return bool(classes & NOTICE_CLASSES) or str(node.get("role") or "").lower() in NOTICE_ROLES


def _block_label(node):
    label = node.name
    if node.get("id"):
        label += "#" + code_text(placeholders(str(node.get("id"))))
    classes = [code_text(placeholders(name)) for name in (node.get("class") or [])[:2]]
    return label + ("." + ".".join(classes) if classes else "")


def _heading(node):
    found = node.find(HEADING_TAGS) or node.find(class_=lambda value: value in HEADING_CLASSES) or node.find("strong")
    return label_shape(found.get_text(" ")) if found is not None else ""


def notice_blocks(html, page_url, link_shape):
    soup = BeautifulSoup(html or "", "html.parser")
    chosen = []
    for node in soup.find_all(True):
        if not _notice_block(node) or any(parent in chosen for parent in node.parents) or _in_navigation(node):
            continue
        chosen.append(node)
    lines = ["- Blocks: %d" % len(chosen)]
    for number, node in enumerate(chosen[:MAX_NOTICE_BLOCKS], 1):
        links = []
        for anchor in node.find_all("a", href=True):
            path = _same_host_path(anchor.get("href"), page_url)
            shape = link_shape(path) if path else ""
            if shape and shape not in links:
                links.append(shape)
        forms = []
        for form in node.find_all("form"):
            entry = "%s %s" % (str(form.get("method") or "get").upper(), link_shape(path_only(form.get("action") or "")) or "-")
            if entry not in forms:
                forms.append(entry)
        lines.append("- Block %d %s: heading '%s', links %s, forms %s" % (
            number, _block_label(node), _heading(node) or "-", " | ".join(links[:MAX_NOTICE_LINKS]) or "-", " | ".join(forms) or "-",
        ))
    if len(chosen) > MAX_NOTICE_BLOCKS:
        lines.append("- Blocks skipped: %d beyond the limit of %d" % (len(chosen) - MAX_NOTICE_BLOCKS, MAX_NOTICE_BLOCKS))
    return lines
