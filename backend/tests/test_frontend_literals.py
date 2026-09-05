import json
import re
from pathlib import Path

from tests.frontend_sources import (
    VENDOR_EXEMPT_PATHS,
    is_vendor_exempt,
    script_names,
)
from tests.test_frontend_direction import (
    FRONTEND,
    element_calls,
    enclosing_function,
    split_arguments,
    without_nested_elements,
)

BUNDLE = json.loads((FRONTEND / "i18n" / "de.json").read_text(encoding="utf-8"))
SOURCES = script_names

TEXT_LITERAL = re.compile(r"\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'")
TEMPLATE_WITH_HOLE = re.compile(r"`(?:[^`\\]|\\.)*\$\{", re.S)
CARRIES_MEANING = re.compile(r"[0-9A-Za-zÀ-ɏЀ-ӿ؀-ۿ]")
NUMBER_CAST = re.compile(r"\bString\s*\(")
BARE_LENGTH = re.compile(r"[\w$.]+\.length")

ALLOWED_TEXT_CHILD = {
    '"?"': "the placeholder initial of an avatar when IServ gives no name",
}

COUNT_INDEPENDENT_KEYS = {
    "absence.history.title": "the number stands in brackets behind the heading, no noun is inflected",
    "letters.toast.marked": "the sentence names no counted noun, only the bare number",
    "letters.unread": "the sentence names no counted noun, only the bare number",
    "pinboard.unread": "the sentence names no counted noun, only the bare number",
    "settings.notify.summary.more": "the count is a plus suffix behind a service name",
    "settings.phones.count": "the sentence names no counted noun, only the bare number",
    "settings.subjects.count": "the sentence names no counted noun, only the bare number",
    "settings.teachers.count": "the sentence names no counted noun, only the bare number",
    "common.badge.overflow": "the badge cap is always the same nine, the plus sign carries the rest",
    "nav.unread": "a spoken tab label that names the area and the bare number, no counted noun is inflected",
    "post.segment.unread": "a spoken segment label that names the area and the bare number, no counted noun is inflected",
}

PLURAL_CATEGORIES = ("zero", "one", "two", "few", "many", "other")


def sources():
    return [
        FRONTEND / name
        for name in SOURCES()
        if (FRONTEND / name).is_file() and not is_vendor_exempt(FRONTEND / name)
    ]


def plural_families():
    families = set()
    for key in BUNDLE:
        head, _, tail = key.rpartition(".")
        if head and tail in PLURAL_CATEGORIES:
            families.add(head)
    return families


def child_slot(body):
    arguments = split_arguments(body)
    if len(arguments) < 3:
        return ""
    return without_nested_elements(",".join(arguments[2:]))


def split_top(text, separators):
    parts = []
    segment = []
    depth = 0
    for char in text:
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        if depth == 0 and char in separators:
            parts.append("".join(segment))
            segment = []
            continue
        segment.append(char)
    parts.append("".join(segment))
    return parts


def branches(expression):
    parts = [part.strip() for part in split_top(expression, "?:")]
    if len(parts) == 1:
        return [parts[0]]
    return [part for part in parts[1:] if part]


def direct_children(slot):
    text = slot.strip()
    while text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    shown = []
    for part in split_top(text, ","):
        if not part.strip():
            continue
        shown.extend(branch for branch in branches(part) if branch)
    return shown


def rendered(body):
    slot = child_slot(body)
    return direct_children(slot) if slot else []


def literal_children(name, text):
    lines = text.split("\n")
    offenders = []
    for start, _callee, body in element_calls(text):
        found = []
        for shown in rendered(body):
            if TEMPLATE_WITH_HOLE.match(shown):
                found.append("`${...}`")
                continue
            literal = TEXT_LITERAL.fullmatch(shown)
            if not literal or literal.group(0) in ALLOWED_TEXT_CHILD:
                continue
            if CARRIES_MEANING.search(literal.group(0)[1:-1]):
                found.append(literal.group(0))
        if not found:
            continue
        line = text.count("\n", 0, start) + 1
        function_name = enclosing_function(lines, line - 1)
        offenders.append(f"{name}:{line} {function_name} -> {sorted(set(found))[:3]}")
    return offenders


def number_children(name, text):
    lines = text.split("\n")
    offenders = []
    for start, _callee, body in element_calls(text):
        found = [
            shown
            for shown in rendered(body)
            if NUMBER_CAST.match(shown) or BARE_LENGTH.fullmatch(shown)
        ]
        if not found:
            continue
        line = text.count("\n", 0, start) + 1
        function_name = enclosing_function(lines, line - 1)
        offenders.append(f"{name}:{line} {function_name} -> {sorted(set(found))[:2]}")
    return offenders


def counted_key_calls(text):
    return re.findall(r"\b(t|label)\(\s*\"([a-z][\w.]*)\"", text)


def test_no_user_visible_literal_is_handed_to_an_element_as_a_text_child():
    offenders = []
    for path in sources():
        offenders.extend(literal_children(path.name, path.read_text(encoding="utf-8")))
    assert offenders == [], (
        "every user visible text comes from t()/tCount() - a literal or a template "
        f"literal as an element child cannot be translated: {offenders}"
    )


def test_no_number_reaches_the_screen_without_formatnumber():
    offenders = []
    for path in sources():
        offenders.extend(number_children(path.name, path.read_text(encoding="utf-8")))
    assert offenders == [], (
        "numbers reach the screen through formatNumber(), so they carry the digits of "
        f"the active language: {offenders}"
    )


def test_every_counted_key_is_called_through_tcount():
    families = plural_families()
    offenders = []
    for path in sources():
        text = path.read_text(encoding="utf-8")
        for _caller, key in counted_key_calls(text):
            value = BUNDLE.get(key)
            if value is None or "{count}" not in value:
                continue
            if key in COUNT_INDEPENDENT_KEYS:
                continue
            offenders.append(f"{path.name}: {key}")
            assert key not in families
    assert offenders == [], (
        "a key that carries {count} needs a plural family and tCount(), otherwise the "
        f"singular form is wrong in at least one language: {offenders}"
    )


def test_every_count_independent_key_exists_and_carries_a_reason():
    for key, reason in COUNT_INDEPENDENT_KEYS.items():
        assert key in BUNDLE, f"{key} is no longer part of the base bundle"
        assert "{count}" in BUNDLE[key], f"{key} no longer carries a count - drop the line"
        assert len(reason.split()) >= 6, f"{key} needs a reason a reader can weigh"


def test_every_allowed_text_child_carries_a_reason():
    for literal, reason in ALLOWED_TEXT_CHILD.items():
        assert literal.strip()
        assert len(reason.split()) >= 6, f"{literal} needs a reason a reader can weigh"


def test_the_literal_scanner_flags_a_planted_string_child():
    assert literal_children("app.js", 'el("span", {}, "9+")')
    assert literal_children("app.js", 'el("span", {}, `${a} x ${b} px`)')
    assert literal_children("app.js", 'el("span", {}, t("common.retry"))') == []
    assert literal_children("app.js", 'el("span", { class: "badge" }, value)') == []


def test_the_number_scanner_flags_a_planted_cast():
    assert number_children("app.js", 'el("span", {}, String(count))')
    assert number_children("app.js", 'el("span", {}, items.length)')
    assert number_children("app.js", 'el("span", {}, formatNumber(count))') == []
    assert number_children("app.js", 'el("span", { "aria-pressed": String(active) }, label)') == []


def test_the_vendor_exemption_covers_only_the_vendor_directory():
    assert VENDOR_EXEMPT_PATHS == ("frontend/vendor",)
    assert is_vendor_exempt(FRONTEND / "vendor" / "pdfjs" / "pdf.mjs")
    assert is_vendor_exempt(FRONTEND / "vendor" / "readme.md")
    assert not is_vendor_exempt(FRONTEND / "app.js")
    assert not is_vendor_exempt(FRONTEND / "vendored.js")
    assert not is_vendor_exempt(FRONTEND.parent / "backend" / "vendor" / "pdf.mjs")
