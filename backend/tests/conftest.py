import os
from pathlib import Path

import pytest

from tests.netguard import sitecustomize as netguard

FIXTURES = Path(__file__).parent / "fixtures"
NETGUARD_DIR = Path(__file__).parent / "netguard"
NetworkBlocked = netguard.NetworkBlocked
PYTHONPATH_BEFORE = pytest.StashKey()
UNSET = object()


def pytest_configure(config):
    netguard.install()
    existing = os.environ.get("PYTHONPATH")
    config.stash[PYTHONPATH_BEFORE] = existing
    if str(NETGUARD_DIR) not in (existing or "").split(os.pathsep):
        os.environ["PYTHONPATH"] = os.pathsep.join([str(NETGUARD_DIR)] + ([existing] if existing else []))


def pytest_unconfigure(config):
    netguard.uninstall()
    before = config.stash.get(PYTHONPATH_BEFORE, UNSET)
    if before is UNSET:
        return
    if before is None:
        os.environ.pop("PYTHONPATH", None)
    else:
        os.environ["PYTHONPATH"] = before


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture():
    return load_fixture
