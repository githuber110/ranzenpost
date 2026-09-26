import os
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest
import requests

from tests import conftest
from tests.conftest import NetworkBlocked

CHILD_CHECK = (
    "import socket\n"
    "names = [socket.getaddrinfo.__name__, socket.gethostbyname.__name__, socket.gethostbyname_ex.__name__, socket.socket.connect.__name__]\n"
    "print(','.join(names))\n"
)


@pytest.fixture(scope="module")
def module_lookup():
    try:
        socket.getaddrinfo("example.com", 443)
    except OSError as error:
        return error
    return None


def test_a_real_connect_to_the_internet_is_blocked():
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(NetworkBlocked):
            client.connect(("93.184.216.34", 443))
        with pytest.raises(NetworkBlocked):
            client.connect_ex(("93.184.216.34", 443))
    finally:
        client.close()


def test_every_real_name_lookup_is_blocked():
    with pytest.raises(NetworkBlocked):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(NetworkBlocked):
        socket.gethostbyname("example.com")
    with pytest.raises(NetworkBlocked):
        socket.gethostbyname_ex("example.com")


def test_a_module_scoped_fixture_is_blocked_too(module_lookup):
    assert isinstance(module_lookup, NetworkBlocked)


def test_a_real_http_request_is_blocked():
    with pytest.raises(requests.ConnectionError):
        requests.get("https://example.com/", timeout=2)


def test_a_child_python_process_is_guarded_as_well():
    run = subprocess.run([sys.executable, "-c", CHILD_CHECK], env=dict(os.environ), capture_output=True, text=True)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip() == "guarded_getaddrinfo,guarded_gethostbyname,guarded_gethostbyname_ex,guarded_connect"


def test_localhost_stays_reachable():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(server.getsockname())
        accepted, _address = server.accept()
        accepted.close()
    finally:
        client.close()
        server.close()


@pytest.mark.parametrize("before", ["kept", None])
def test_the_python_path_is_restored_after_the_run(monkeypatch, before):
    if before is None:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    else:
        monkeypatch.setenv("PYTHONPATH", before)
    config = SimpleNamespace(stash=pytest.Stash())
    try:
        conftest.pytest_configure(config)
        assert os.environ["PYTHONPATH"].split(os.pathsep)[0] == str(conftest.NETGUARD_DIR)
        conftest.pytest_unconfigure(config)
        assert os.environ.get("PYTHONPATH") == before
    finally:
        conftest.netguard.install()
