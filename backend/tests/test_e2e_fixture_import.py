import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
PLAYWRIGHT_CONFIG = ROOT / "playwright.config.js"
CAPTURE_SCRIPT = ROOT / "scripts" / "capture_screenshots.js"
TESTS_DIR = BACKEND_DIR / "tests"
FIXTURE_MODULE = TESTS_DIR / "e2e_fixture_app.py"

IMPORT_SCRIPT = "import tests.e2e_fixture_app\n"


def test_importing_the_fixture_module_leaves_an_existing_data_dir_untouched(tmp_path):
    marker = tmp_path / "keep-me.txt"
    marker.write_text("still here", encoding="utf-8")

    run = subprocess.run(
        [sys.executable, "-c", IMPORT_SCRIPT],
        cwd=BACKEND_DIR,
        env=dict(os.environ, ISERV_E2E_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0, run.stderr
    assert marker.exists(), "importing tests.e2e_fixture_app deleted its data directory"
    assert marker.read_text(encoding="utf-8") == "still here"


def test_reset_e2e_data_dir_still_wipes_when_called_explicitly(tmp_path):
    script = (
        "import tests.e2e_fixture_app as fixture\n"
        "fixture.reset_e2e_data_dir()\n"
        "print(fixture.E2E_DATA_DIR.exists())\n"
    )
    marker = tmp_path / "stale.txt"
    marker.write_text("stale", encoding="utf-8")

    run = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env=dict(os.environ, ISERV_E2E_DATA_DIR=str(tmp_path)),
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0, run.stderr
    assert not tmp_path.exists()


def test_create_server_app_resets_the_data_dir_before_building_the_app():
    tree = ast.parse(FIXTURE_MODULE.read_text(encoding="utf-8"))
    factory = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "create_server_app")
    source = ast.unparse(factory)
    assert "reset_e2e_data_dir()" in source
    assert "create_fixture_app()" in source


def fixture_imports(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names if "e2e_fixture_app" in alias.name)
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] + [alias.name for alias in node.names]
            if any("e2e_fixture_app" in name for name in names):
                yield node.module or ""


def test_no_test_imports_the_fixture_module_into_the_test_process():
    offenders = [
        path.name
        for path in sorted(TESTS_DIR.glob("test_*.py"))
        if any(fixture_imports(ast.parse(path.read_text(encoding="utf-8"))))
    ]
    assert offenders == []


def test_the_import_guard_sees_both_import_forms():
    planted = ast.parse("from tests import e2e_fixture_app\nimport tests.e2e_fixture_app as fixture\n")
    assert len(list(fixture_imports(planted))) == 2
    assert list(fixture_imports(ast.parse('SCRIPT = "import tests.e2e_fixture_app"\n'))) == []


def test_the_playwright_webserver_uses_the_explicit_factory_entry():
    text = PLAYWRIGHT_CONFIG.read_text(encoding="utf-8")
    assert "tests.e2e_fixture_app:create_server_app" in text
    assert "--factory" in text


def test_the_screenshot_capture_script_uses_the_explicit_factory_entry():
    text = CAPTURE_SCRIPT.read_text(encoding="utf-8")
    assert "tests.e2e_fixture_app:create_server_app" in text
    assert "--factory" in text
