import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

FOREIGN_TEXT_FIELDS = {
    "letter": ("title", "sender", "subject"),
    "detail": ("title", "sender", "body_html"),
    "tile": ("title", "text", "preview"),
    "post": ("title", "text", "preview"),
    "folder": ("title",),
    "entry": ("comment", "subject", "answer", "question", "label", "target", "reason"),
    "file": ("filename", "name"),
    "attachment": ("filename", "name"),
    "child": ("name", "class_name"),
    "c": ("name", "class_name"),
    "lesson": ("subject_label", "teacher_label", "room"),
    "phone": ("label", "number"),
    "note": ("text", "title"),
    "conference": ("title", "teacher", "slot"),
    "me": ("forename", "lastname", "email", "external_id"),
}
FOREIGN_FIELD = re.compile(
    r"\b(" + "|".join(sorted(FOREIGN_TEXT_FIELDS)) + r")\.(\w+)\b"
)
DIRECTION_ATTRIBUTE = re.compile(r"\bdir\s*:")
FUNCTION_DECLARATION = re.compile(
    r"^\s*(?:async\s+)?function\s+([A-Za-z_\$][\w\$]*)"
    r"|^\s*(?:const|let|var)\s+([A-Za-z_\$][\w\$]*)\s*=\s*(?:async\s+)?"
    r"(?:function\b|\([^;]*\)\s*=>|[\w\$]+\s*=>)"
)
MODULE_SCOPE = "<module>"

DIRECTION_DEBT = {}
FOREIGN_TEXT_FACTORY = "iservText"


def sources():
    return sorted(path for path in FRONTEND.glob("*.js") if path.is_file())


def _skip_string(text, index):
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return index


ELEMENT_CALL = re.compile(r"\b(el|" + FOREIGN_TEXT_FACTORY + r")\(")


def element_calls(text):
    calls = []
    for opener in ELEMENT_CALL.finditer(text):
        index = opener.end()
        depth = 1
        while index < len(text) and depth:
            char = text[index]
            if char in "\"'`":
                index = _skip_string(text, index)
                continue
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
                if depth == 0:
                    break
            index += 1
        calls.append((opener.start(), opener.group(1), text[opener.end():index]))
    return calls


def split_arguments(body):
    arguments = []
    current = []
    depth = 0
    index = 0
    while index < len(body):
        char = body[index]
        if char in "\"'`":
            end = _skip_string(body, index)
            current.append(body[index:end])
            index = end
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            arguments.append("".join(current))
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    arguments.append("".join(current))
    return arguments


def without_nested_elements(text):
    stripped = text
    while True:
        calls = element_calls(stripped)
        if not calls:
            return stripped
        start, name, body = calls[0]
        stripped = stripped[:start] + " " + stripped[start + len(name) + len(body) + 2:]


def own_scope(body):
    arguments = split_arguments(body)
    if len(arguments) < 2:
        return None, None
    attributes = arguments[1]
    children = without_nested_elements(",".join(arguments[2:]))
    return attributes, attributes + " " + children


def enclosing_function(lines, offset_line):
    for cursor in range(offset_line, -1, -1):
        found = FUNCTION_DECLARATION.match(lines[cursor])
        if found:
            return found.group(1) or found.group(2)
    return MODULE_SCOPE


def foreign_fields(scope):
    return sorted(
        {
            f"{receiver}.{field}"
            for receiver, field in FOREIGN_FIELD.findall(scope)
            if field in FOREIGN_TEXT_FIELDS[receiver]
        }
    )


def scan_source(name, text):
    lines = text.split("\n")
    undirected = {}
    directed = {}
    for start, callee, body in element_calls(text):
        attributes, scope = own_scope(body)
        if scope is None:
            continue
        fields = foreign_fields(scope)
        if not fields:
            continue
        function_name = enclosing_function(lines, text.count("\n", 0, start))
        carries_direction = callee == FOREIGN_TEXT_FACTORY or DIRECTION_ATTRIBUTE.search(attributes)
        target = directed if carries_direction else undirected
        for field in fields:
            key = (name, function_name, field)
            target[key] = target.get(key, 0) + 1
    return undirected, directed


def scan():
    undirected = {}
    for path in sources():
        found, _ = scan_source(path.name, path.read_text(encoding="utf-8"))
        for key, count in found.items():
            undirected[key] = undirected.get(key, 0) + count
    return undirected


def test_no_new_foreign_text_node_renders_without_a_direction():
    found = scan()
    offenders = []
    for key in sorted(found):
        allowed = DIRECTION_DEBT.get(key, 0)
        if found[key] > allowed:
            offenders.append(f"{key[0]}:{key[1]} renders {key[2]} without dir (allowed {allowed})")
    assert offenders == [], (
        "text that comes from IServ or from the school settings keeps its own reading "
        f"direction - give the node dir=\"auto\": {offenders}"
    )


def test_the_direction_debt_list_holds_no_entry_that_is_already_paid():
    found = scan()
    stale = []
    for key in sorted(DIRECTION_DEBT):
        actual = found.get(key, 0)
        if actual < DIRECTION_DEBT[key]:
            stale.append(f"{key[0]}:{key[1]} {key[2]} listed {DIRECTION_DEBT[key]}, found {actual}")
    assert stale == [], (
        "delete these lines from DIRECTION_DEBT in "
        f"backend/tests/test_frontend_direction.py: {stale}"
    )


FACTORY_DEFINITION = re.compile(
    r"(?:const|let|var)\s+" + FOREIGN_TEXT_FACTORY + r"\s*=[^;]*?dir:\s*\"auto\"", re.S
)


def test_the_foreign_text_factory_exists_and_forces_a_direction():
    source = (FRONTEND / "app.js").read_text(encoding="utf-8")
    assert FACTORY_DEFINITION.search(source), (
        f"{FOREIGN_TEXT_FACTORY} is the single sanctioned way to render an IServ field - "
        "it has to set dir=\"auto\" itself"
    )


def test_the_scanner_accepts_the_foreign_text_factory():
    source = (
        'function letterRow(letter) {\n'
        '  return iservText("div", { class: "row-title" }, letter.title);\n'
        "}"
    )
    undirected, directed = scan_source("app.js", source)
    assert undirected == {}
    assert directed == {("app.js", "letterRow", "letter.title"): 1}


def test_the_scanner_charges_a_plain_node_that_wraps_the_factory_to_nobody():
    source = (
        'function letterRow(letter) {\n'
        '  return el("div", { class: "row" }, [iservText("div", {}, letter.title)]);\n'
        "}"
    )
    undirected, directed = scan_source("app.js", source)
    assert undirected == {}
    assert directed == {("app.js", "letterRow", "letter.title"): 1}


def test_the_scanner_flags_an_undirected_foreign_text_node():
    source = 'function letterRow(letter) {\n  return el("div", { class: "row-title" }, letter.title);\n}'
    undirected, directed = scan_source("app.js", source)
    assert undirected == {("app.js", "letterRow", "letter.title"): 1}
    assert directed == {}


def test_the_scanner_accepts_a_node_that_carries_a_direction():
    source = (
        'function letterRow(letter) {\n'
        '  return el("div", { class: "row-title", dir: "auto" }, letter.title);\n'
        "}"
    )
    undirected, directed = scan_source("app.js", source)
    assert undirected == {}
    assert directed == {("app.js", "letterRow", "letter.title"): 1}


def test_the_scanner_charges_a_nested_node_to_the_node_that_renders_the_text():
    source = (
        'function letterRow(letter) {\n'
        '  return el("div", { class: "row" }, [el("div", { class: "row-title" }, letter.title)]);\n'
        "}"
    )
    undirected, _ = scan_source("app.js", source)
    assert undirected == {("app.js", "letterRow", "letter.title"): 1}


def test_the_scanner_leaves_translated_text_alone():
    source = 'function tabbar(item) {\n  return el("span", {}, t(item.label));\n}'
    undirected, directed = scan_source("app.js", source)
    assert undirected == {}
    assert directed == {}
