import threading

from app.sign_in import SignInService
from app.store import Store
from tests.support import add_school, connection_service


def test_the_connection_and_its_sign_in_share_one_session_lock_and_code_memory(tmp_path):
    store = Store(tmp_path / "data")
    connection = connection_service(store, add_school(store))
    sign_in = connection._sign_in
    assert isinstance(sign_in, SignInService) and sign_in.connection is connection
    assert connection._session_lock is sign_in._session_lock
    assert connection._last_code is sign_in._last_code
    session = object()
    connection._client = session
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
