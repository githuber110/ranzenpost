import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def repeated_definitions(source):
    seen = set()
    repeated = []
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in seen:
                repeated.append(node.name)
            seen.add(node.name)
    return repeated


def test_no_backend_module_defines_a_function_or_class_twice():
    found = {
        path.relative_to(APP).as_posix(): repeated_definitions(path.read_text(encoding="utf-8"))
        for path in sorted(APP.rglob("*.py"))
    }
    assert {name: names for name, names in found.items() if names} == {}


def test_the_scanner_names_a_second_definition():
    assert repeated_definitions("def a():\n    pass\n\n\ndef b():\n    pass\n\n\ndef a():\n    pass\n") == ["a"]
    assert repeated_definitions("def a():\n    pass\n\n\nclass B:\n    def a(self):\n        pass\n") == []
