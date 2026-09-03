import pathlib
import re
import tokenize

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
FRONTEND = REPO_ROOT / "frontend"
E2E = REPO_ROOT / "e2e"
URL_LITERAL = re.compile(r"https?://[^\s\"'`;]*")
JS_COMMENT = re.compile(r"(^\s*//)|([^:\"'`]//)")


def collect_comments():
    found = []
    for base in ("app", "tests"):
        for path in sorted((BACKEND / base).rglob("*.py")):
            with open(path, "rb") as handle:
                for token in tokenize.tokenize(handle.readline):
                    if token.type == tokenize.COMMENT:
                        found.append(f"{path.relative_to(BACKEND)}:{token.start[0]} {token.string}")
    return found


def js_targets():
    return sorted(FRONTEND.glob("*.js")) + sorted((FRONTEND / "tests").glob("*.js")) + sorted(E2E.glob("*.js"))


def collect_js_comments():
    found = []
    for path in js_targets():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            checked = URL_LITERAL.sub("", line)
            if JS_COMMENT.search(checked) or "/*" in checked:
                found.append(f"{path.name}:{number} {line.strip()[:60]}")
    return found


def collect_css_comments():
    found = []
    for path in sorted(FRONTEND.glob("*.css")):
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
