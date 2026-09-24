import posixpath
import re
import shutil
import subprocess

import pytest

from tests.frontend_sources import FRONTEND, script_names

NODE_MISSING = shutil.which("node") is None
SCRIPT_TAG = re.compile(r"<script\b([^>]*)>")
MODULE_TYPE = re.compile(r"\btype=\"module\"")
LOCAL_SOURCE = re.compile(r"\bsrc=\"\./([\w./-]+\.m?js)(?:\?v=\d+)?\"")
STATIC_IMPORT = re.compile(r"\b(?:import|export)\s+(?:[\w$*{}\s,]+?\s+from\s+)?[\"']([^\"'\n]+)[\"']")
CLASSIC_CHECK = "new (require('vm').Script)(require('fs').readFileSync(0, 'utf8'))"


def page_modules(html):
    found = []
    for match in SCRIPT_TAG.finditer(html):
        attributes = match.group(1)
        source = LOCAL_SOURCE.search(attributes)
        if source and MODULE_TYPE.search(attributes):
            found.append(source.group(1))
    return found


def relative_imports(name, text):
    targets = []
    for specifier in STATIC_IMPORT.findall(text):
        if specifier.startswith("./") or specifier.startswith("../"):
            targets.append(posixpath.normpath(posixpath.join(posixpath.dirname(name), specifier)))
    return targets


def module_names(frontend=FRONTEND):
    html = (frontend / "index.html").read_text(encoding="utf-8")
    modules = set()
    queue = page_modules(html)
    while queue:
        name = queue.pop()
        if name in modules or not (frontend / name).is_file():
            continue
        modules.add(name)
        queue.extend(relative_imports(name, (frontend / name).read_text(encoding="utf-8")))
    return modules


def check_syntax(path, as_module):
    command = ["node", "--check", "--input-type=module"] if as_module else ["node", "-e", CLASSIC_CHECK]
    return subprocess.run(
        command,
        input=path.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.mark.skipif(NODE_MISSING, reason="node not available")
@pytest.mark.parametrize("name", script_names())
def test_frontend_js_has_no_syntax_error(name):
    result = check_syntax(FRONTEND / name, name in module_names())
    assert result.returncode == 0, result.stderr


def test_the_page_loads_the_modules_the_syntax_check_treats_as_modules():
    assert {"lib/globals.js", "lib/i18n.js"} <= module_names() <= set(script_names())
    assert "app.js" not in module_names()


def _plant(tmp_path, files, html):
    frontend = tmp_path / "frontend"
    for name, text in files.items():
        (frontend / name).parent.mkdir(parents=True, exist_ok=True)
        (frontend / name).write_text(text, encoding="utf-8")
    (frontend / "index.html").write_text(html, encoding="utf-8")
    return frontend


PLANTED_PAGE = (
    '<script src="./classic.js?v=1" defer></script>\n'
    '<script type="module" src="./lib/entry.js?v=1"></script>\n'
)


def test_the_module_set_follows_the_page_and_its_imports(tmp_path):
    frontend = _plant(
        tmp_path,
        {
            "classic.js": "var a = 1;\n",
            "lib/entry.js": 'import { b } from "./deep/b.js";\nexport const c = b;\n',
            "lib/deep/b.js": "export const b = 1;\n",
            "lib/unused.js": "export const d = 1;\n",
        },
        PLANTED_PAGE,
    )
    assert module_names(frontend) == {"lib/entry.js", "lib/deep/b.js"}


@pytest.mark.skipif(NODE_MISSING, reason="node not available")
def test_a_classic_script_with_an_export_fails_although_node_would_detect_a_module(tmp_path):
    frontend = _plant(tmp_path, {"classic.js": "export function x() {}\n"}, PLANTED_PAGE)
    assert "classic.js" not in module_names(frontend)
    assert check_syntax(frontend / "classic.js", as_module=False).returncode != 0


@pytest.mark.skipif(NODE_MISSING, reason="node not available")
def test_a_module_with_a_syntax_error_fails(tmp_path):
    frontend = _plant(tmp_path, {"lib/entry.js": 'import { a } from "./a.js";\nexport const b = ;\n'}, PLANTED_PAGE)
    assert check_syntax(frontend / "lib/entry.js", as_module=True).returncode != 0


@pytest.mark.skipif(NODE_MISSING, reason="node not available")
def test_a_sound_module_and_a_sound_classic_script_pass(tmp_path):
    frontend = _plant(
        tmp_path,
        {
            "classic.js": "(function () {\n  const a = import(\"./x.mjs\");\n})();\n",
            "lib/entry.js": 'import { a } from "./a.js";\nexport const b = a;\n',
        },
        PLANTED_PAGE,
    )
    assert check_syntax(frontend / "classic.js", as_module=False).returncode == 0
    assert check_syntax(frontend / "lib/entry.js", as_module=True).returncode == 0


@pytest.mark.skipif(NODE_MISSING, reason="node not available")
def test_a_broken_classic_script_fails(tmp_path):
    frontend = _plant(tmp_path, {"classic.js": "(function () {\n  const a = ;\n})();\n"}, PLANTED_PAGE)
    assert check_syntax(frontend / "classic.js", as_module=False).returncode != 0
