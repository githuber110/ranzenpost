import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"

EMPTY_CATCH = re.compile(
    r"catch\s*(?:\([^()]*\)\s*)?\{\s*\}"
    r"|\.catch\(\s*(?:\([^()]*\)|[\w\$]+)\s*=>\s*\{\s*\}\s*\)"
)
FUNCTION_DECLARATION = re.compile(
    r"^\s*(?:async\s+)?function\s+([A-Za-z_\$][\w\$]*)"
    r"|^\s*(?:const|let|var)\s+([A-Za-z_\$][\w\$]*)\s*=\s*(?:async\s+)?"
    r"(?:function\b|\([^;]*\)\s*=>|[\w\$]+\s*=>)"
)
MODULE_SCOPE = "<module>"

DELIBERATE_EMPTY_CATCH = {
    ("app.js", "loadBaseLanguage"): (
        1,
        "the base bundle is the only source of every label - without it the app boots "
        "with raw keys and the very next request paints the service error screen, so "
        "there is no second message to show here",
    ),
    ("app.js", "writeCachedForename"): (
        1,
        "localStorage refuses in private mode and over quota; the cached forename is a "
        "cosmetic head start for the greeting and the app reads the real name from the API",
    ),
    ("app.js", "writeStoredText"): (
        1,
        "same localStorage refusal; every caller keeps working from state and only loses "
        "a convenience across restarts",
    ),
    ("app.js", "setTheme"): (
        1,
        "same localStorage refusal; the theme is applied to the document first, only "
        "remembering it across restarts fails",
    ),
}

EMPTY_CATCH_DEBT = {site: allowed for site, (allowed, _reason) in DELIBERATE_EMPTY_CATCH.items()}


def sources():
    return sorted(path for path in FRONTEND.glob("*.js") if path.is_file())


def enclosing_function(lines, index):
    for cursor in range(index, -1, -1):
        found = FUNCTION_DECLARATION.match(lines[cursor])
        if found:
            return found.group(1) or found.group(2)
    return MODULE_SCOPE


def empty_catches_in(text):
    lines = text.split("\n")
    hits = []
    for match in EMPTY_CATCH.finditer(text):
        index = text.count("\n", 0, match.start())
        hits.append((enclosing_function(lines, index), index + 1))
    return hits


def scan():
    found = {}
    for path in sources():
        for function_name, line in empty_catches_in(path.read_text(encoding="utf-8")):
            found.setdefault((path.name, function_name), []).append(line)
    return found


def test_no_new_empty_catch_block_enters_the_frontend():
    found = scan()
    offenders = []
    for site, lines in sorted(found.items()):
        allowed = EMPTY_CATCH_DEBT.get(site, 0)
        if len(lines) > allowed:
            offenders.append(f"{site[0]}:{site[1]} lines {lines} (allowed {allowed})")
    assert offenders == [], (
        "an empty catch swallows the failure - roll back, toast, or ignore it on purpose "
        f"and say so in EMPTY_CATCH_DEBT: {offenders}"
    )


def test_the_empty_catch_debt_list_holds_no_entry_that_is_already_paid():
    found = scan()
    stale = []
    for site, allowed in sorted(EMPTY_CATCH_DEBT.items()):
        actual = len(found.get(site, []))
        if actual < allowed:
            stale.append(f"{site[0]}:{site[1]} listed {allowed}, found {actual}")
    assert stale == [], (
        "delete these lines from EMPTY_CATCH_DEBT in "
        f"backend/tests/test_frontend_error_handling.py: {stale}"
    )


def test_every_deliberate_empty_catch_carries_a_written_reason():
    assert DELIBERATE_EMPTY_CATCH, "an empty allow list needs no reasons - drop the table"
    for site, (allowed, reason) in DELIBERATE_EMPTY_CATCH.items():
        assert allowed >= 1, f"{site} allows nothing - delete the line instead"
        assert len(reason.split()) >= 8, f"{site} needs a reason a reader can weigh, got {reason!r}"


def test_the_scanner_sees_every_shape_of_a_swallowed_error():
    assert empty_catches_in("function a() {\n  try { x(); } catch (error) {}\n}")
    assert empty_catches_in("function a() {\n  try { x(); } catch {}\n}")
    assert empty_catches_in("function a() {\n  send().catch(() => {});\n}")
    assert empty_catches_in("function a() {\n  send().catch((error) => {});\n}")
    assert empty_catches_in("function a() {\n  send().catch(error => {});\n}")


def test_the_scanner_sees_a_catch_whose_empty_body_spans_lines():
    source = "function a() {\n  try {\n    x();\n  } catch (error) {\n\n  }\n}"
    assert empty_catches_in(source) == [("a", 4)]


def test_the_scanner_leaves_a_handled_error_alone():
    assert empty_catches_in("function a() {\n  try { x(); } catch (error) { report(error); }\n}") == []
    assert empty_catches_in("function a() {\n  send().catch((error) => toast(error));\n}") == []


def test_the_scanner_names_the_function_the_swallowed_error_lives_in():
    source = (
        "function outer() {\n"
        "  return 1;\n"
        "}\n"
        "\n"
        "const inner = async () => {\n"
        "  try { await x(); } catch (error) {}\n"
        "};\n"
    )
    assert empty_catches_in(source) == [("inner", 6)]


def test_every_scanned_source_file_is_a_shipped_frontend_script():
    names = {path.name for path in sources()}
    assert names, "the frontend ships at least one script"
    assert all(not name.endswith(".test.js") for name in names)
