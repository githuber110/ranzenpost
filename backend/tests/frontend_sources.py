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
