def path_of(url):
    text = str(url or "").split("#", 1)[0].split("?", 1)[0]
    if "://" not in text:
        return text
    rest = text.split("://", 1)[1]
    slash = rest.find("/")
    return rest[slash:] if slash >= 0 else "/"


REFUSAL_TEXT_LIMIT = 120


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
