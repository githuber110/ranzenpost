import shutil
import subprocess

import pytest

from tests.frontend_sources import FRONTEND, script_names


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("name", script_names())
def test_frontend_js_has_no_syntax_error(name):
    result = subprocess.run(
        ["node", "--check", str(FRONTEND / name)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
