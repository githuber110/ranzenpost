import ast
import pathlib
import re

import pytest

from app.iserv.messenger import ForbiddenMatrixCallError, MatrixClient

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
GUARD_FILE = APP / "iserv" / "messenger.py"

FORBIDDEN_PATTERNS = (
    re.compile(r"read_markers"),
    re.compile(r"/receipt/"),
    re.compile(r"setRoomReadMarkers"),
    re.compile(r"sendReceipt"),
    re.compile(r"m\.fully_read"),
)

SANCTION_FLAG = "sanctioned=True"
SANCTIONED_FUNCTION = "send_read_marker"
SERVICE_METHOD = "mark_room_read"
READ_ROUTE = '"/api/messenger/read"'

BACKGROUND_FILES = (
    "poller.py",
    "scheduler.py",
    "calendar_listener.py",
    "mqtt_bridge.py",
    "mqtt_publisher.py",
    "hanotify.py",
)


def test_no_module_other_than_the_matrix_guard_mentions_read_markers_or_receipts():
    offenders = []
    for path in sorted(APP.rglob("*.py")):
        if path == GUARD_FILE:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                offenders.append(f"{path.relative_to(APP)}:{line_no} {pattern.pattern}")
    assert offenders == []


def test_the_matrix_client_blocks_read_marker_and_receipt_paths_at_runtime():
    client = MatrixClient("https://school.example", "tok", session=object())
    with pytest.raises(ForbiddenMatrixCallError):
        client._get("/_matrix/client/v3/rooms/!x:y/read_markers")
    with pytest.raises(ForbiddenMatrixCallError):
        client._put("/_matrix/client/v3/rooms/!x:y/receipt/m.read/$evt", {})
    with pytest.raises(ForbiddenMatrixCallError):
        client._put("/_matrix/client/v3/rooms/!x:y/read_markers", {})


def test_the_one_sanction_covers_the_read_marker_route_and_nothing_else():
    client = MatrixClient("https://school.example", "tok", session=object())
    with pytest.raises(ForbiddenMatrixCallError):
        client._put("/_matrix/client/v3/rooms/!x:y/receipt/m.read/$evt", {}, sanctioned=True)
    with pytest.raises(ForbiddenMatrixCallError):
        client._put("/_matrix/client/v3/rooms/!x:y/read_markers/extra", {}, sanctioned=True)
    client._guard("/_matrix/client/v3/rooms/!x:y/read_markers", sanctioned=True)


def _functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            found.setdefault(node.name, []).append(node)
    return found


def _sanction_lines(text):
    return [
        text.count("\n", 0, match.start()) + 1
        for match in re.finditer(re.escape(SANCTION_FLAG), text)
    ]


def test_exactly_one_function_in_the_whole_app_may_build_a_receipt_call():
    carriers = []
    for path in sorted(APP.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if SANCTION_FLAG in text:
            carriers.append((path, text))
    assert [path.relative_to(APP) for path, _text in carriers] == [
        pathlib.Path("iserv") / "messenger.py"
    ]
    path, text = carriers[0]
    lines = _sanction_lines(text)
    assert len(lines) == 1, f"the sanction appears {len(lines)} times: {lines}"
    node = _functions(path)[SANCTIONED_FUNCTION][0]
    assert node.lineno < lines[0] <= node.end_lineno


def _owners(path):
    text = path.read_text(encoding="utf-8")
    owners = []
    for node in ast.parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owners.append((node.name, node))
        elif isinstance(node, ast.ClassDef):
            owners.extend(
                (child.name, child)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return text, owners


def _owners_mentioning(needle, skip=()):
    found = []
    for path in sorted(APP.rglob("*.py")):
        if path in skip:
            continue
        text, owners = _owners(path)
        if needle not in text:
            continue
        for name, node in owners:
            if name == needle:
                continue
            if needle in (ast.get_source_segment(text, node) or ""):
                found.append(f"{path.relative_to(APP)}:{name}")
    return found


def test_the_sanctioned_function_is_reachable_only_from_the_click_route():
    assert _owners_mentioning(SANCTIONED_FUNCTION, skip=(GUARD_FILE,)) == [
        f"messenger.py:{SERVICE_METHOD}"
    ]
    assert _owners_mentioning(SERVICE_METHOD) == ["service.py:messenger_mark_read"]
    assert _owners_mentioning("messenger_mark_read") == ["messenger_routes.py:register_routes"]


def test_the_route_module_is_the_only_place_that_wires_the_read_endpoint():
    routes = APP / "messenger_routes.py"
    text = routes.read_text(encoding="utf-8")
    assert text.count(READ_ROUTE) == 1
    assert text.count("service.messenger_mark_read") == 1
    handler = next(
        node
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef) and node.name == "messenger_read"
    )
    wiring = text.index("service.messenger_mark_read")
    line = text.count("\n", 0, wiring) + 1
    assert handler.lineno < line <= handler.end_lineno
    for path in sorted(APP.rglob("*.py")):
        if path == routes:
            continue
        assert "/api/messenger/read" not in path.read_text(encoding="utf-8")


def _imported_names(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("filename", BACKGROUND_FILES)
def test_no_background_module_imports_the_messenger_send_path(filename):
    path = APP / filename
    if not path.is_file():
        pytest.skip(f"{filename} does not exist in this checkout")
    names = _imported_names(path)
    assert "send_message" not in names
    assert SANCTIONED_FUNCTION not in names
    assert "MessengerService" not in names
    assert "messenger" not in names


def test_the_send_function_exists_only_in_the_messenger_module():
    from app.messenger import MessengerService

    assert hasattr(MessengerService, "send_message")
    assert hasattr(MessengerService, SERVICE_METHOD)


def test_the_route_module_is_the_only_place_that_wires_the_send_endpoint():
    text = (APP / "messenger_routes.py").read_text(encoding="utf-8")
    assert '"/api/messenger/send"' in text
    for filename in BACKGROUND_FILES:
        path = APP / filename
        if not path.is_file():
            continue
        assert "/api/messenger/send" not in path.read_text(encoding="utf-8")
