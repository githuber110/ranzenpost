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
    assert "MessengerService" not in names
    assert "messenger" not in names


def test_the_send_function_exists_only_in_the_messenger_module():
    from app.messenger import MessengerService

    assert hasattr(MessengerService, "send_message")


def test_the_route_module_is_the_only_place_that_wires_the_send_endpoint():
    text = (APP / "messenger_routes.py").read_text(encoding="utf-8")
    assert '"/api/messenger/send"' in text
    for filename in BACKGROUND_FILES:
        path = APP / filename
        if not path.is_file():
            continue
        assert "/api/messenger/send" not in path.read_text(encoding="utf-8")
