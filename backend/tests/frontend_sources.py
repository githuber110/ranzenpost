import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"

VENDOR_EXEMPT_PATHS = ("frontend/vendor",)
VENDOR_EXEMPT_REASON = (
    "third party code shipped byte for byte; the German, comment and logical-property "
    "conventions are ours, not its, and rewriting it would break the upstream update path"
)

TEST_TREE_PATHS = ("frontend/tests",)
TEST_TREE_REASON = (
    "the vitest suite lives next to the code it drives; it is never shipped to a browser "
    "and its fixtures quote German on purpose"
)

SCRIPT_SUFFIXES = (".js", ".mjs")
STYLE_SUFFIXES = (".css",)
MARKUP_SUFFIXES = (".html",)
GUARDED_SUFFIXES = SCRIPT_SUFFIXES + STYLE_SUFFIXES + MARKUP_SUFFIXES

APP_PARTS_DIR = "app"
BODY = re.compile(r"<body>(.*?)</body>", re.S)
CLASSIC_SCRIPT = re.compile(r'<script src="\./([\w./-]+)\?v=\d+" defer></script>')


def _relative(path):
    return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()


def _under(relative, prefixes):
    return any(relative == prefix or relative.startswith(prefix + "/") for prefix in prefixes)


def is_vendor_exempt(path):
    return _under(_relative(path), VENDOR_EXEMPT_PATHS)


def is_test_tree(path):
    return _under(_relative(path), TEST_TREE_PATHS)


def is_shipped(path):
    return not is_vendor_exempt(path) and not is_test_tree(path)


def shipped_paths(suffixes=GUARDED_SUFFIXES):
    return tuple(
        path
        for path in sorted(FRONTEND.rglob("*"))
        if path.is_file() and path.suffix in suffixes and is_shipped(path)
    )


def shipped_names(suffixes=GUARDED_SUFFIXES):
    return tuple(path.relative_to(FRONTEND).as_posix() for path in shipped_paths(suffixes))


def script_names():
    return shipped_names(SCRIPT_SUFFIXES)


def stylesheet_names():
    return shipped_names(STYLE_SUFFIXES)


def markup_names():
    return shipped_names(MARKUP_SUFFIXES)


def app_script_names(frontend=None):
    frontend = FRONTEND if frontend is None else frontend
    body = BODY.search((frontend / "index.html").read_text(encoding="utf-8"))
    names = CLASSIC_SCRIPT.findall(body.group(1) if body else "")
    return tuple(name for name in names if name == "app.js" or name.startswith(APP_PARTS_DIR + "/"))


def app_sources(frontend=None):
    frontend = FRONTEND if frontend is None else frontend
    return tuple((name, (frontend / name).read_text(encoding="utf-8")) for name in app_script_names(frontend))


def app_source_text(frontend=None):
    return "\n".join(text for _name, text in app_sources(frontend))
