from .subscriptions import child_first_name


def _folder_order(title):
    text = (title or "").strip().lower()
    for umlaut, plain in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        text = text.replace(umlaut, plain)
    return text


def child_sort_key(child):
    name = " ".join(str(child.get("name") or "").split())
    return (child_first_name(name).casefold(), name.casefold())


def _folder_sort_key(last_post_id, title):
    if last_post_id is None:
        return (1, _folder_order(title))
    return (0, -last_post_id)


def _published_sort_key(value):
    text = (value or "").strip()
    parts = text.split(" ")[0].split(".")
    if len(parts) == 3:
        try:
            day, month, year = (int(part) for part in parts)
            time_part = text.split(" ")[1] if " " in text else "00:00"
            hour, _, minute = time_part.partition(":")
            return (1, year, month, day, int(hour or 0), int(minute or 0))
        except ValueError:
            pass
    return (0, 0, 0, 0, 0, 0)
