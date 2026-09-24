import pathlib
import re
import tokenize

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
FRONTEND = REPO_ROOT / "frontend"
E2E = REPO_ROOT / "e2e"
URL_LITERAL = re.compile(r"https?://[^\s\"'`;]*")
JS_COMMENT = re.compile(r"(^\s*//)|([^:\"'`]//)")
PYTHON_ROOTS = ("backend/app", "backend/tests", "custom_components", "tests", "scripts")
JS_ROOTS = ("frontend", "e2e", "custom_components", "tests", "scripts")
JS_SUFFIXES = (".js", ".mjs")
SKIPPED_PARTS = {"vendor", "node_modules", "__pycache__"}


def owned(path):
    return not SKIPPED_PARTS.intersection(path.parts)


def python_targets(root=REPO_ROOT):
    found = set()
    for base in PYTHON_ROOTS:
        found.update(path for path in (root / base).rglob("*.py") if owned(path.relative_to(root)))
    return sorted(found)


def collect_comments(root=REPO_ROOT):
    found = []
    for path in python_targets(root):
        with open(path, "rb") as handle:
            for token in tokenize.tokenize(handle.readline):
                if token.type == tokenize.COMMENT:
                    found.append(f"{path.relative_to(root).as_posix()}:{token.start[0]} {token.string}")
    return found


def js_targets(root=REPO_ROOT):
    found = set()
    for base in JS_ROOTS:
        for path in (root / base).rglob("*"):
            if path.suffix in JS_SUFFIXES and owned(path.relative_to(root)):
                found.add(path)
    return sorted(found)


def collect_js_comments(root=REPO_ROOT):
    found = []
    for path in js_targets(root):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            checked = URL_LITERAL.sub("", line)
            if JS_COMMENT.search(checked) or "/*" in checked:
                found.append(f"{path.name}:{number} {line.strip()[:60]}")
    return found


def collect_css_comments(root=REPO_ROOT):
    found = []
    for path in sorted(path for path in (root / "frontend").rglob("*.css") if owned(path.relative_to(root))):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "/*" in line or "*/" in line:
                found.append(f"{path.name}:{number} {line.strip()[:60]}")
    return found


def collect_html_comments():
    found = []
    for path in sorted(FRONTEND.glob("*.html")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "<!--" in line:
                found.append(f"{path.name}:{number} {line.strip()[:60]}")
    return found


def test_backend_python_has_no_comments():
    assert collect_comments() == []


def test_frontend_js_has_no_comments():
    assert collect_js_comments() == []


def test_frontend_css_has_no_comments():
    assert collect_css_comments() == []


def test_frontend_html_has_no_comments():
    assert collect_html_comments() == []


def test_js_scan_covers_e2e_directory():
    names = {path.name for path in js_targets()}
    e2e_names = {path.name for path in E2E.glob("*.js")}
    assert e2e_names, "e2e directory has no spec files to guard"
    assert e2e_names <= names


def test_js_comment_detector_ignores_urls_but_catches_dense_inline_comments():
    line = 'const url = "https://school.example/api";//leak'
    checked = URL_LITERAL.sub("", line)
    assert JS_COMMENT.search(checked) is not None


def test_js_comment_detector_does_not_flag_a_bare_url_literal():
    line = 'const url = "https://school.example/path";'
    checked = URL_LITERAL.sub("", line)
    assert JS_COMMENT.search(checked) is None
    assert "/*" not in checked


def test_the_sweeps_reach_new_nested_folders_and_skip_vendored_code(tmp_path):
    files = {
        "backend/app/deep/nested/module.py": "VALUE = 1  # note\n",
        "custom_components/ranzenpost/extra/helper.py": "# note\nVALUE = 1\n",
        "custom_components/ranzenpost/frontend/extra/card.js": "const value = 1; // note\n",
        "frontend/extra/module.js": "/* note */\n",
        "frontend/extra/styles.css": "/* note */\n",
        "frontend/vendor/lib/library.js": "/* license */\n",
        "frontend/vendor/lib/library.css": "/* license */\n",
        "backend/app/clean.py": "VALUE = \"https://example.org/#x\"\n",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    python = [entry.split(":")[0] for entry in collect_comments(tmp_path)]
    assert python == ["backend/app/deep/nested/module.py", "custom_components/ranzenpost/extra/helper.py"]
    assert [entry.split(":")[0] for entry in collect_js_comments(tmp_path)] == ["card.js", "module.js"]
    assert [entry.split(":")[0] for entry in collect_css_comments(tmp_path)] == ["styles.css"]
