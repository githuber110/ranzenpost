def path_of(url):
    text = str(url or "").split("#", 1)[0].split("?", 1)[0]
    if "://" not in text:
        return text
    rest = text.split("://", 1)[1]
    slash = rest.find("/")
    return rest[slash:] if slash >= 0 else "/"


def base_shape(response):
    text = getattr(response, "text", "") or ""
    headers = getattr(response, "headers", None) or {}
    return {
        "status": int(getattr(response, "status_code", 0) or 0),
        "final_path": path_of(getattr(response, "url", "")),
        "content_type": str(headers.get("content-type") or "").split(";")[0].strip(),
        "length": len(text),
    }
