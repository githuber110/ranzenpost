BADGES_PATH = "/iserv/app/navigation/badges"
MAIL_BADGE = "mail"
MAIL_MODULE = "mail"
MAIL_PAGE_PATH = "/iserv/mail"
BADGE_LIMIT = 100000


class BadgeShapeError(ValueError):
    pass


def parse_badges(payload):
    if isinstance(payload, list) and not payload:
        return {}
    if not isinstance(payload, dict):
        raise BadgeShapeError("navigation badges are not an object")
    counts = {}
    for key, value in payload.items():
        readable = not isinstance(value, bool) and isinstance(value, int) and 0 <= value < BADGE_LIMIT
        counts[str(key)] = value if readable else None
    return counts
