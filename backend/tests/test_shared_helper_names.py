import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _private(name):
    return name.startswith("_") and not name.startswith("__")


def _private_reaches(tree):
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                modules.add(alias.asname or alias.name)
                if _private(alias.name):
                    yield node.lineno, alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                modules.add((alias.asname or alias.name).split(".")[0])
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in modules
            and _private(node.attr)
        ):
            yield node.lineno, f"{node.value.id}.{node.attr}"


def test_modules_share_helpers_only_under_public_names():
    found = []
    for path in sorted(APP.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found += [f"{path.relative_to(APP)}:{line} {name}" for line, name in _private_reaches(tree)]
    assert found == []
