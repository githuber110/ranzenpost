import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available")
@pytest.mark.parametrize("name", ["app.js", "wizard.js", "steps.js", "qr.js", "bootdir.js"])
def test_frontend_js_has_no_syntax_error(name):
    result = subprocess.run(
        ["node", "--check", str(FRONTEND / name)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
