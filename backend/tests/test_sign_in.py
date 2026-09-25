import ast
import threading
from pathlib import Path

import pytest

from app.sign_in import SignInService
from app.store import Store
from tests.support import add_school, connection_service

APP = Path(__file__).resolve().parents[1] / "app"
CLIENT_OWNERS = {"__init__", "_login_now", "drop_session"}


def test_the_connection_and_its_sign_in_share_one_session_lock_and_code_memory(tmp_path):
    store = Store(tmp_path / "data")
    connection = connection_service(store, add_school(store))
    sign_in = connection._sign_in
    assert isinstance(sign_in, SignInService) and sign_in.connection is connection
    assert connection._session_lock is sign_in._session_lock
    assert connection._last_code is sign_in._last_code
    session = object()
    sign_in._client = session
    assert connection._client is session
    with pytest.raises(AttributeError):
        connection._client = None
    assert sign_in._client is session
    replacement = threading.RLock()
    connection._session_lock = replacement
    assert sign_in._session_lock is replacement
    connection._expiry_window = 40 * 60
    assert sign_in._expiry_window == 40 * 60
    sign_in._client = None
    assert connection._client is None


def test_sign_in_state_never_lives_on_the_connection_itself(tmp_path):
    store = Store(tmp_path / "data")
    connection = connection_service(store, add_school(store))
    owned = ("_client", "_last_code", "_session_lock", "_expiry_window", "_signed_in_at", "_forced_relogin_at", "_fresh_refusal_logged")
    assert [name for name in owned if name in vars(connection)] == []
    for name in owned:
        assert hasattr(connection._sign_in, name), name
    memory = {"code": "123456"}
    connection._last_code = memory
    assert connection._sign_in._last_code is memory
    assert [name for name in owned if name in vars(connection)] == []


def _client_writes(tree):
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    owner = {}
    for function in functions:
        for node in ast.walk(function):
            owner.setdefault(node, function.name)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = node.targets
        for target in targets:
            for part in ast.walk(target):
                attribute = isinstance(part, ast.Attribute) and part.attr == "_client"
                key = isinstance(part, ast.Subscript) and isinstance(part.slice, ast.Constant) and part.slice.value == "_client"
                if attribute or key:
                    yield node.lineno, owner.get(node)
        if isinstance(node, ast.Call) and any(isinstance(arg, ast.Constant) and arg.value == "_client" for arg in node.args):
            function = node.func
            name = function.id if isinstance(function, ast.Name) else getattr(function, "attr", "")
            if name in ("setattr", "delattr", "__setattr__", "__delattr__"):
                yield node.lineno, owner.get(node)


def test_only_the_sign_in_service_sets_or_drops_the_session_client():
    stray = []
    for path in sorted(APP.rglob("*.py")):
        writes = list(_client_writes(ast.parse(path.read_text(encoding="utf-8"))))
        if path.name == "sign_in.py" and path.parent == APP:
            stray += [f"{path.name}:{line} in {owner}" for line, owner in writes if owner not in CLIENT_OWNERS]
        else:
            stray += [f"{path.relative_to(APP)}:{line}" for line, _ in writes]
    assert stray == []


def test_dropping_the_session_waits_for_the_session_lock(tmp_path):
    store = Store(tmp_path / "data")
    connection = connection_service(store, add_school(store))
    sign_in = connection._sign_in
    sign_in._client = object()
    holding = threading.Event()
    release = threading.Event()

    def hold():
        with sign_in._session_lock:
            holding.set()
            assert release.wait(timeout=30)

    holder = threading.Thread(target=hold)
    holder.start()
    assert holding.wait(timeout=30)
    dropper = threading.Thread(target=sign_in.drop_session)
    dropper.start()
    dropper.join(timeout=0.2)
    assert dropper.is_alive() and sign_in._client is not None
    release.set()
    holder.join(timeout=30)
    dropper.join(timeout=30)
    assert not dropper.is_alive() and sign_in._client is None
    assert connection.signed_in_session() is None
