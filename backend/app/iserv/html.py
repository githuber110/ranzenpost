import re
from html import escape

from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.element import PreformattedString, Script, Stylesheet, TemplateString

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
    "dd", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "s", "small",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
    "thead", "tr", "u", "ul",
}

VOID_TAGS = {"br", "col", "hr", "img"}

ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
    "abbr": {"title"},
}

DROPPED_TAGS = {
    "applet", "base", "embed", "form", "frame", "frameset", "head", "iframe", "link", "math",
    "meta", "noembed", "noframes", "noscript", "object", "script", "style", "svg", "template", "title",
}

NUMBER_ATTRS = {"width", "height", "colspan", "rowspan", "span"}
NUMBER_VALUE = re.compile(r"^\d{1,4}(%|px)?$")
SCOPE_VALUES = {"row", "col", "rowgroup", "colgroup"}
URL_ATTRS = {"href", "src"}
URL_SCHEME = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*):")
URL_BREAKS = re.compile(r"[\t\n\r]")
URL_EDGES = "".join(chr(code) for code in range(0x21))
LINK_SCHEMES = {"http", "https", "mailto", "tel"}
IMAGE_SCHEMES = {"http", "https"}
IMAGE_DATA = re.compile(r"^data:image/(png|jpeg|gif|webp|bmp|avif|svg\+xml)[;,]", re.IGNORECASE)
TEXT_NODES = (Script, Stylesheet, TemplateString, PreformattedString)
LINK_EXTRAS = (("rel", "noopener noreferrer"), ("target", "_blank"))


def clean_html(value):
    if not value:
        return ""
    soup = BeautifulSoup(str(value).replace("\x00", ""), "html.parser")
    parts = []
    stack = [("node", child) for child in reversed(list(soup.children))]
    while stack:
        kind, item = stack.pop()
        if kind == "close":
            parts.append(f"</{item}>")
        elif isinstance(item, Tag):
            _open(item, parts, stack)
        elif isinstance(item, NavigableString) and not isinstance(item, TEXT_NODES):
            parts.append(escape(str(item), quote=False))
    return "".join(parts)


def _open(element, parts, stack):
    name = (element.name or "").lower()
    if name in DROPPED_TAGS or element.prefix:
        return
    children = [("node", child) for child in reversed(list(element.children))]
    if name not in ALLOWED_TAGS:
        stack.extend(children)
        return
    parts.append(f"<{name}{_attributes(name, element.attrs)}>")
    if name in VOID_TAGS:
        stack.extend(children)
        return
    stack.append(("close", name))
    stack.extend(children)


def _attributes(name, attrs):
    allowed = ALLOWED_ATTRS.get(name, set())
    kept = []
    seen = set()
    for raw_key, raw_value in attrs.items():
        key = str(raw_key).lower()
        if key not in allowed or key in seen:
            continue
        value = " ".join(raw_value) if isinstance(raw_value, (list, tuple)) else str(raw_value or "")
        value = _attribute_value(name, key, value.replace("\x00", ""))
        if value is None:
            continue
        seen.add(key)
        kept.append((key, value))
    if name == "a":
        kept.extend(LINK_EXTRAS)
    return "".join(f' {key}="{escape(value, quote=True)}"' for key, value in kept)


def _attribute_value(name, key, value):
    if key in URL_ATTRS:
        return safe_url(value, image=name == "img")
    if key in NUMBER_ATTRS:
        value = value.strip()
        return value if NUMBER_VALUE.match(value) else None
    if key == "scope":
        value = value.strip().lower()
        return value if value in SCOPE_VALUES else None
    return value


def plain_text(value):
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def safe_url(value, image=False):
    if not isinstance(value, str):
        return None
    candidate = URL_BREAKS.sub("", value).strip(URL_EDGES)
    if not candidate:
        return None
    if image and IMAGE_DATA.match(candidate):
        return candidate
    match = URL_SCHEME.match(candidate)
    if match:
        scheme = match.group(1).lower()
        return candidate if scheme in (IMAGE_SCHEMES if image else LINK_SCHEMES) else None
    if candidate.startswith(("/", "#")):
        return candidate
    return None


def is_safe_url(candidate):
    return safe_url(candidate) is not None
