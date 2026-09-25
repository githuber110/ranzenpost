import re
from urllib.parse import urlsplit

MATRIX_ROOM = re.compile(r"(?:!|%21)[A-Za-z0-9._=~+-]{4,}(?::|%3[Aa])(?:<[a-z]+>|[A-Za-z0-9.-]+)(?::\d+)?")
UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
ISO_DATE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)")
GERMAN_DATE = re.compile(r"(?<!\d)\d{2}\.\d{2}\.\d{4}(?!\d)")
NUMBER_RUN = re.compile(r"(?<!\d)\d{4,}(?!\d)")
HEX_TOKEN = re.compile(r"(?<![\w-])[0-9a-f]{24,}(?![\w-])")
UUID_MARK = "<uuid>"
DATE_MARK = "<date>"
NUMBER_MARK = "<n>"
TOKEN_MARK = "<hex>"
ROOM_MARK = "<room>"


def placeholders(text):
    text = MATRIX_ROOM.sub(ROOM_MARK, str(text or ""))
    text = UUID.sub(UUID_MARK, text)
    text = ISO_DATE.sub(DATE_MARK, text)
    text = GERMAN_DATE.sub(DATE_MARK, text)
    text = HEX_TOKEN.sub(TOKEN_MARK, text)
    return NUMBER_RUN.sub(NUMBER_MARK, text)


def path_only(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" in text:
        return urlsplit(text).path
    return text.split("?", 1)[0].split("#", 1)[0]


def path_pattern(value):
    return placeholders(path_only(value))
