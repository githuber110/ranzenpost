import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from . import valueshape
from .pageshape import code_text, json_script, unique
from .pathpattern import path_only, placeholders
from .valueshape import table_cell
from .vocabulary import CHANGE_TYPE_WORDS, known_word

MAX_SCRIPT_ENDPOINTS = 400
MIN_SEGMENTS = 2
SCRIPT_PREFIXES = ("/iserv/", "/_matrix/", "/api/")
SCRIPT_ROOT = "/iserv/"
EXPR = "<expr>"
HASH_MARK = "<hash>"
KEY_WINDOW = 300
HEAD_WINDOW = 160
OPTIONS_WINDOW = 400
NO_METHOD = "-"
SCRIPT_TABLE_HEAD = "| Method | Path | Script | Keys nearby |"
SCRIPT_TABLE_RULE = "|---|---|---|---|"
STRING_LITERAL = re.compile(r"\"([^\"\\]*(?:\\.[^\"\\]*)*)\"|'([^'\\]*(?:\\.[^'\\]*)*)'|`([^`\\]*(?:\\.[^`\\]*)*)`")
PATH_START = re.compile(r"[\"'`]/")
TEMPLATE_HOLE = re.compile(r"\$\{[^{}]*\}")
PATH_LITERAL = re.compile(r"^(?:<expr>)?/(?:[A-Za-z0-9_.$/-]|<expr>)*(?:\?.*)?$")
PATH_TAIL = re.compile(r"^(?:[A-Za-z0-9_.$/?=&%-]|<expr>)*$")
HAS_LETTER = re.compile(r"[A-Za-z]")
PLUS_NEXT = re.compile(r"\s*\+\s*")
EXPR_TOKEN = re.compile(r"[\w$.]+(?:\([^()]*\))?(?:\[[^\[\]]*\])?")
PREFIX_EXPR = re.compile(r"[\w$.\]\)]+\s*\+\s*$")
XHR_OPEN = re.compile(r"\.open\(\s*[\"']([A-Za-z]+)[\"']\s*,\s*$")
VERB_CALL = re.compile(r"\.(get|post|put|patch|delete|head|options)\s*\(\s*$", re.IGNORECASE)
FETCH_CALL = re.compile(r"(?<![\w$.])(?:fetch|axios(?:\.request)?)\s*\(\s*(?:\{[^{}]*?\burl\s*:\s*)?$")
METHOD_OPTION = re.compile(r"\bmethod\s*:\s*[\"']([A-Za-z]+)[\"']")
CREDENTIAL_KEY = re.compile(
    r"(?<![\w$])(access_?token|refresh_?token|login_?token|user_?id|device_?id|home_?server|matrix[a-z_]{0,30}|[a-z_]{1,24}_?token|password)(?![\w$])",
    re.IGNORECASE,
)
HASH_SEGMENT = re.compile(r"(?<=[-._~])(?=[A-Za-z0-9_]*\d)[A-Za-z0-9_]{6,}(?=\.(?:[a-z]+\.)*m?js$)")
SCRIPT_NAME_PART = re.compile(r"(<[a-z]+>|[-_.~])")
TYPE_KEY_ANCHOR = re.compile(r"change_?types?|chgtypes?", re.IGNORECASE)
TYPE_WORD_ANCHOR = re.compile("|".join(CHANGE_TYPE_WORDS), re.IGNORECASE)
TYPE_WINDOW = 1500
TYPE_LABEL = r"(?:[\w$.]+\(\s*)?[\"'`]([^\"'`\\\n]{1,60})[\"'`]"
TYPE_PAIRS = (
    re.compile(r"(?<![\w$.])[\"']?(\d{1,2})[\"']?\s*:\s*" + TYPE_LABEL),
    re.compile(r"\bcase\s+[\"']?(\d{1,2})[\"']?\s*:\s*(?:return\s+)?" + TYPE_LABEL),
    re.compile(r"\[\s*[\"']?(\d{1,2})[\"']?\s*\]\s*=\s*" + TYPE_LABEL),
)
LABEL_WORD = re.compile(r"[^\W\d_]+")
LABEL_DIGITS = re.compile(r"\d+")
MAX_TYPE_LABELS = 40


def script_sources(html, page_url, root=SCRIPT_ROOT):
    host = urlsplit(page_url or "").netloc.lower()
    found = []
    if not host:
        return found
    for tag in BeautifulSoup(html or "", "html.parser").find_all("script", src=True):
        parts = urlsplit(urljoin(page_url, str(tag.get("src") or "").strip()))
        if parts.netloc.lower() != host or not parts.path.startswith(root):
            continue
        path = parts.path + ("?" + parts.query if parts.query else "")
        if path not in found:
            found.append(path)
    return found


def _script_name_part(part, last):
    if not part or SCRIPT_NAME_PART.fullmatch(part):
        return part
    if part.isdigit():
        return "<n>"
    if last and part.lower() in valueshape.FILE_EXTENSIONS:
        return part
    return part if part.isalpha() and known_word(part) else valueshape.WORD_MARK


def script_label(path):
    name = placeholders(HASH_SEGMENT.sub(HASH_MARK, path_only(path).rsplit("/", 1)[-1]))
    parts = SCRIPT_NAME_PART.split(name)
    return "".join(_script_name_part(part, index == len(parts) - 1) for index, part in enumerate(parts))


def script_line(path, link_shape=None):
    folder = path_only(path).rsplit("/", 1)[0]
    return (link_shape or valueshape.link_shape)(folder) + "/" + script_label(path)


def _literal_value(match):
    if match.group(3) is not None:
        return TEMPLATE_HOLE.sub(EXPR, match.group(3))
    return match.group(1) if match.group(1) is not None else match.group(2)


def _chain(text, start_value, position):
    parts = [start_value]
    while True:
        plus = PLUS_NEXT.match(text, position)
        if not plus:
            break
        literal = STRING_LITERAL.match(text, plus.end())
        if literal:
            value = _literal_value(literal)
            if not PATH_TAIL.match(value):
                break
            parts.append(value)
            position = literal.end()
            continue
        token = EXPR_TOKEN.match(text, plus.end())
        if not token:
            break
        parts.append(EXPR)
        position = token.end()
    return "".join(parts), position


def _call_span(text, position):
    depth = 0
    end = min(len(text), position + OPTIONS_WINDOW)
    for index in range(position, end):
        char = text[index]
        if char in "({[":
            depth += 1
        elif char in ")}]":
            depth -= 1
            if depth < 0:
                return text[position:index]
    return text[position:end]


def _method_of(text, start, end):
    head = text[max(0, start - HEAD_WINDOW):start]
    prefix = PREFIX_EXPR.search(head)
    if prefix:
        head = head[:prefix.start()]
    opened = XHR_OPEN.search(head)
    if opened:
        return opened.group(1).upper()
    verb = VERB_CALL.search(head)
    if verb:
        return verb.group(1).upper()
    call = FETCH_CALL.search(head)
    if not call:
        return ""
    options = METHOD_OPTION.search(head[call.start():]) or METHOD_OPTION.search(_call_span(text, end))
    return options.group(1).upper() if options else "GET"


def _keys_near(text, start, end):
    window = text[max(0, start - KEY_WINDOW):min(len(text), end + KEY_WINDOW)]
    return {match.group(1) for match in CREDENTIAL_KEY.finditer(window)}


def _accept(pattern):
    if not PATH_LITERAL.match(pattern) or not HAS_LETTER.search(pattern):
        return False
    if EXPR in pattern or any(prefix in pattern for prefix in SCRIPT_PREFIXES):
        return True
    segments = [segment for segment in path_only(pattern).split("/") if segment]
    return len(segments) >= MIN_SEGMENTS


def script_endpoints(text, label):
    found = {}
    position = 0
    while len(found) < MAX_SCRIPT_ENDPOINTS:
        hit = PATH_START.search(text, position)
        if not hit:
            break
        match = STRING_LITERAL.match(text, hit.start())
        if not match:
            position = hit.start() + 1
            continue
        position = match.end()
        value = _literal_value(match)
        pattern, position = _chain(text, value, match.end())
        if PREFIX_EXPR.search(text[max(0, match.start() - HEAD_WINDOW):match.start()]):
            pattern = EXPR + pattern
        if not _accept(pattern):
            continue
        method = _method_of(text, match.start(), position)
        pattern = placeholders(path_only(pattern))
        keys = _keys_near(text, match.start(), position) if method else set()
        found.setdefault((method or NO_METHOD, pattern, label), set()).update(keys)
    return found


def _endpoint_row(key, keys, link_shape=None):
    method, pattern, label = key
    shown = (link_shape or valueshape.link_shape)(pattern)
    return "| %s | %s | %s | %s |" % (table_cell(method), table_cell(shown), table_cell(label), table_cell(", ".join(sorted({code_text(key) for key in keys})) or "-"))


def _sort_key(item):
    method, pattern, label = item[0]
    bare = pattern[len(EXPR):] if pattern.startswith(EXPR) else pattern
    return bare, method, label


def inline_endpoints(html):
    found = {}
    for tag in BeautifulSoup(html or "", "html.parser").find_all("script"):
        if tag.get("src") or json_script(tag):
            continue
        for key, keys in script_endpoints(tag.get_text() or "", "inline").items():
            found.setdefault(key, set()).update(keys)
    return found


def endpoint_rows(found, link_shape=None):
    rows = unique((_endpoint_row(key, keys, link_shape) for key, keys in sorted(found.items(), key=_sort_key)), MAX_SCRIPT_ENDPOINTS)
    return [SCRIPT_TABLE_HEAD, SCRIPT_TABLE_RULE] + rows


def _label_shape(label):
    words = LABEL_WORD.sub(lambda match: match.group(0) if known_word(match.group(0)) else valueshape.WORD_MARK, label.strip())
    return LABEL_DIGITS.sub("<n>", words)


def _type_windows(text):
    found = sorted(
        (max(0, match.start() - TYPE_WINDOW), min(len(text), match.end() + TYPE_WINDOW))
        for pattern in (TYPE_KEY_ANCHOR, TYPE_WORD_ANCHOR)
        for match in pattern.finditer(text)
    )
    spans = []
    for start, end in found:
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return [text[start:end] for start, end in spans]


def change_type_labels(texts):
    anchors = 0
    found = {}
    for text in texts:
        anchors += len(TYPE_KEY_ANCHOR.findall(text))
        for window in _type_windows(text):
            for pattern in TYPE_PAIRS:
                for match in pattern.finditer(window):
                    code = int(match.group(1))
                    found.setdefault(code, [])
                    shaped = _label_shape(match.group(2))
                    if shaped and shaped not in found[code]:
                        found[code].append(shaped)
    pairs = [(code, labels) for code, labels in sorted(found.items()) if labels][:MAX_TYPE_LABELS]
    return anchors, pairs


def change_type_label_line(pairs):
    if not pairs:
        return "none found"
    return " | ".join("%d -> %s" % (code, " / ".join(labels)) for code, labels in pairs)
