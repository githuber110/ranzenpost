UNKNOWN_CHILD_KEY = "api.child.unknown"


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
