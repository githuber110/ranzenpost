from bs4 import BeautifulSoup

ALLOWED_TAGS = {
    "a", "abbr", "b", "blockquote", "br", "caption", "code", "col", "colgroup",
    "dd", "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3",
    "h4", "h5", "h6", "hr", "i", "img", "li", "ol", "p", "pre", "s", "small",
    "span", "strong", "sub", "sup", "table", "tbody", "td", "tfoot", "th",
    "thead", "tr", "u", "ul",
}

ALLOWED_ATTRS = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "col": {"span"},
    "colgroup": {"span"},
}

DROPPED_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta", "form", "svg", "math"}

SAFE_SCHEMES = ("http://", "https://", "mailto:", "tel:", "data:image/")


def clean_html(value):
    if not value:
        return ""
    soup = BeautifulSoup(str(value), "html.parser")
    for element in soup.find_all(list(DROPPED_TAGS)):
        element.decompose()
    for element in soup.find_all(True):
        name = element.name.lower()
        if name not in ALLOWED_TAGS:
            element.unwrap()
            continue
        allowed = ALLOWED_ATTRS.get(name, set())
        for attr in list(element.attrs):
            if attr.lower() not in allowed:
                del element.attrs[attr]
        _clean_url(element, "href")
        _clean_url(element, "src")
    if soup.find("a"):
        for anchor in soup.find_all("a"):
            anchor.attrs["rel"] = "noopener noreferrer"
            anchor.attrs["target"] = "_blank"
    return str(soup)


def plain_text(value):
    if not value:
        return ""
    return BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)


def is_safe_url(candidate):
    if not isinstance(candidate, str):
        return False
    stripped = candidate.strip()
    lowered = stripped.lower()
    return lowered.startswith(SAFE_SCHEMES) or stripped.startswith("/") or stripped.startswith("#")


def _clean_url(element, name):
    value = element.attrs.get(name)
    if not isinstance(value, str):
        if value is not None:
            del element.attrs[name]
        return
    candidate = value.strip()
    if is_safe_url(candidate):
        element.attrs[name] = candidate
        return
    del element.attrs[name]
