from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture():
    return load_fixture
