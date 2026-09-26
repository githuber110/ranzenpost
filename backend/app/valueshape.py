import re

from .pathpattern import path_only, placeholders
from .vocabulary import known_identifier, known_word

MAX_LINES = 600
MAX_DEPTH = 12
ROOT_LABEL = "(root)"
KEY_MARK = "<key>"
WORD_MARK = "<word>"
SEGMENT_MARK = "<seg>"
FILE_MARK = "<file>"
DIGITS = re.compile(r"^\d+$")
LETTERS = re.compile(r"^[^\W\d_]+$")
ALNUM = re.compile(r"^[^\W_]+$")
DECIMAL = re.compile(r"^[+-]?\d+[.,]\d+$")
GERMAN_DAY = re.compile(r"^\d{1,2}\.\d{1,2}\.$")
GERMAN_DATE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_MOMENT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$")
CLOCK = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
PATH = re.compile(r"^/\S*$")
HEX = re.compile(r"^[0-9a-fA-F]{8,}$")
COLOUR = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
TOKEN = re.compile(r"^[A-Za-z0-9+/_=.-]{24,}$")
BOOLEAN_TEXT = ("true", "false")
KEY_PART = re.compile(r"^[A-Za-z_$@][A-Za-z0-9_$-]{0,47}$")
VERSION_SEGMENT = re.compile(r"^v?\d{1,2}(?:\.\d{1,2}){1,2}$")
FILE_SEGMENT = re.compile(r"^.+\.([a-z0-9]{1,5})$")
PLACEHOLDER = re.compile(r"<[a-z]+>")
SHORT_VERSION = re.compile(r"^v\d{1,2}$")
ROUTE_PART = re.compile(r"[-_~]|<[a-z]+>")
ROUTE_LETTERS = re.compile(r"^[^\W\d_]+$")
FILE_EXTENSIONS = frozenset(
    {"js", "mjs", "css", "map", "json", "html", "htm", "php", "xml", "txt", "pdf", "png", "jpg", "jpeg", "gif", "svg", "ico",
     "webp", "woff", "woff2", "ttf", "zip", "csv", "ics", "doc", "docx", "xls", "xlsx", "odt", "ods", "mp3", "mp4"}
)
IDENTIFIER_PART = re.compile(r"(<[a-z]+>|[^\W\d_]+|\d+)")
SHORT_PARTS = frozenset({"id", "is", "at", "to", "of", "on", "in", "by", "no", "js", "ui", "x", "y"})
LOGIN_LIKE = re.compile(r"@[\w.:-]+|[^\W\d_][\w-]*(?:[.:][\w-]+)+")


def _starts_part(run, index):
    if index == 0 or not run[index].isupper():
        return False
    after_lower = run[index - 1].islower()
    ends_capitals = run[index - 1].isupper() and index + 1 < len(run) and run[index + 1].islower()
    return after_lower or ends_capitals


def _camel_parts(run):
    parts = []
    current = ""
    for index, char in enumerate(run):
        if current and _starts_part(run, index):
            parts.append(current)
            current = ""
        current += char
    return parts + ([current] if current else [])


def _identifier_part(part):
    if len(part) <= 2:
        return part.lower() in SHORT_PARTS and not (len(part) == 2 and part.isupper())
    return known_identifier(part)


def _identifier_run(run, mark):
    if run.startswith("<") or run.isdigit():
        return run
    return "".join(part if _identifier_part(part) else mark for part in _camel_parts(run))


def _masked_run(run, mark):
    return run if run.startswith("<") or run.isdigit() else mark


def _shaped_pieces(text, mark, shape):
    return "".join(shape(piece, mark) if index % 2 else piece for index, piece in enumerate(IDENTIFIER_PART.split(text)))


def identifier_shape(value, mark=WORD_MARK):
    text = placeholders(str(value or ""))
    shaped = []
    position = 0
    for match in LOGIN_LIKE.finditer(text):
        shaped.append(_shaped_pieces(text[position:match.start()], mark, _identifier_run))
        shaped.append(_shaped_pieces(match.group(0), mark, _masked_run))
        position = match.end()
    shaped.append(_shaped_pieces(text[position:], mark, _identifier_run))
    return "".join(shaped)


def safe_key(key):
    text = str(key)
    if DIGITS.match(text):
        return "<n>"
    if UUID.match(text):
        return "<uuid>"
    if ISO_DATE.match(text) or GERMAN_DATE.match(text) or GERMAN_DAY.match(text):
        return "<date>"
    shaped = []
    for part in text.split("."):
        if not KEY_PART.match(part):
            shaped.append(KEY_MARK)
            continue
        shaped.append(identifier_shape(part, KEY_MARK))
    return ".".join(shaped)


def _query_note(text):
    return " +query" if "?" in text else ""


def string_class(text):
    stripped = text.strip()
    if not stripped:
        return "blank"
    if "\n" in stripped:
        return "multi-line text"
    if stripped.lower() in BOOLEAN_TEXT:
        return "boolean text"
    if DIGITS.match(stripped):
        return "digits"
    if DECIMAL.match(stripped):
        return "decimal"
    if GERMAN_DAY.match(stripped):
        return "date DD.MM."
    if GERMAN_DATE.match(stripped):
        return "date DD.MM.YYYY"
    if ISO_DATE.match(stripped):
        return "iso date"
    if ISO_MOMENT.match(stripped):
        return "iso datetime"
    if CLOCK.match(stripped):
        return "time HH:MM"
    if UUID.match(stripped):
        return "uuid"
    if EMAIL.match(stripped):
        return "email"
    if URL.match(stripped):
        return "url, path " + link_shape(stripped) + _query_note(stripped)
    if PATH.match(stripped):
        return "path " + link_shape(stripped) + _query_note(stripped)
    if COLOUR.match(stripped):
        return "colour"
    if HEX.match(stripped):
        return "hex"
    if LETTERS.match(stripped):
        return "letters"
    if ALNUM.match(stripped):
        return "alphanumeric"
    if stripped[:1] in ("{", "[") and stripped[-1:] in ("}", "]"):
        return "json text"
    if TOKEN.match(stripped):
        return "token"
    return "free text"


def _sign(number):
    if number > 0:
        return ">0"
    if number < 0:
        return "<0"
    return "0"


def _kind(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    return "other"


def value_shape(value):
    kind = _kind(value)
    if kind in ("int", "float"):
        return "%s %s" % (kind, _sign(value))
    if kind == "string":
        return "string len %d, %s" % (len(value), string_class(value))
    if kind == "object":
        return "object keys %d" % len(value)
    if kind == "array":
        if not value:
            return "array len 0"
        return "array len %d of %s" % (len(value), _kind(value[0]))
    return kind


def _join(path, key):
    return "%s.%s" % (path, key) if path else key


def _walk(value, path, depth, lines, seen, limit):
    if len(lines) >= limit:
        return
    label = path or ROOT_LABEL
    if label not in seen:
        seen.add(label)
        lines.append("%s: %s" % (label, value_shape(value)))
    if depth >= MAX_DEPTH:
        return
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, _join(path, safe_key(key)), depth + 1, lines, seen, limit)
            if len(lines) >= limit:
                return
    elif isinstance(value, (list, tuple)) and value:
        _walk(value[0], (path or "") + "[]", depth + 1, lines, seen, limit)


def shape_lines(data, limit=MAX_LINES):
    lines = []
    _walk(data, "", 0, lines, set(), limit)
    return lines


def _route_word(segment):
    parts = [part for part in ROUTE_PART.split(segment) if part]
    return bool(parts) and all(ROUTE_LETTERS.match(part) and known_word(part) for part in parts)


def _link_segment(segment):
    if not segment or segment == "-":
        return segment
    if DIGITS.match(segment):
        return "<n>"
    if not PLACEHOLDER.sub("", segment) or VERSION_SEGMENT.match(segment) or SHORT_VERSION.match(segment):
        return segment
    if _route_word(segment):
        return segment
    extension = FILE_SEGMENT.match(segment.lower())
    if extension and extension.group(1) in FILE_EXTENSIONS:
        return FILE_MARK + "." + extension.group(1)
    return SEGMENT_MARK


def link_shape(value):
    path = placeholders(path_only(value))
    return "/".join(_link_segment(segment) for segment in path.split("/"))


def table_cell(value):
    text = str(value if value is not None else "")
    return text.replace("|", "/").replace("\n", " ") or "-"
