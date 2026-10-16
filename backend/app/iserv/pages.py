import re


def path_of(url):
    text = str(url or "").split("#", 1)[0].split("?", 1)[0]
    if "://" not in text:
        return text
    rest = text.split("://", 1)[1]
    slash = rest.find("/")
    return rest[slash:] if slash >= 0 else "/"


REFUSAL_TEXT_LIMIT = 120
WRITE_WORDS = frozenset(
    "copy delete remove move share rename edit update upload unlink trash duplicate create new add save submit confirm "
    "unconfirm mark markread markunread toggle logout cancel unbook storno hide unhide restore send "
    "reserve withdraw subscribe unsubscribe accept decline".split()
)
FORM_PAGE_WORDS = frozenset("add new create".split())
FILE_NAME = re.compile(r"\.[A-Za-z0-9]{1,5}$")
SEGMENT_WORD = re.compile(r"[^\W_]+")


def action_link(path):
    segments = [segment for segment in path_of(path).split("/") if segment]
    if segments and FILE_NAME.search(segments[-1]):
        segments = segments[:-1]
    return any(word.casefold() in WRITE_WORDS for segment in segments for word in SEGMENT_WORD.findall(segment))


def squeezed(text, limit):
    return " ".join(str(text or "").split())[:limit]


def status_of(response):
    return int(getattr(response, "status_code", 0) or 0)


def refusal_wording(response, soup):
    if int(getattr(response, "status_code", 0) or 0) < 400:
        return ""
    parts = []
    for tag in ("title", "h1", "h2"):
        node = soup.find(tag)
        text = " ".join((node.get_text() if node else "").split())
        if text and text not in parts:
            parts.append(text)
    return " | ".join(parts)[:REFUSAL_TEXT_LIMIT]


def refusal_of(response):
    from bs4 import BeautifulSoup

    return refusal_wording(response, BeautifulSoup(getattr(response, "text", "") or "", "html.parser"))


def base_shape(response):
    text = getattr(response, "text", "") or ""
    headers = getattr(response, "headers", None) or {}
    return {
        "status": int(getattr(response, "status_code", 0) or 0),
        "final_path": path_of(getattr(response, "url", "")),
        "content_type": str(headers.get("content-type") or "").split(";")[0].strip(),
        "length": len(text),
    }
