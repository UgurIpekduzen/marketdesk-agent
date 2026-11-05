"""The writing rules that the linter has no rule for.

No function and no class is defined inside a function (a method of a class is
not inside a function): a helper that needs something from its surroundings
takes it as an argument, and a function that has to be passed on with some
arguments filled in is wrapped with functools.partial. There is no list of
exceptions: a file that breaks the rule fails here.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ("src", "tests", "eval", "scripts", "data")
SINGLE_FILES = ("app.py", "config.py")
SKIPPED_PARTS = {".venv", "__pycache__", ".git", "node_modules"}
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def python_files() -> list[Path]:
    files = [ROOT / name for name in SINGLE_FILES]
    for folder in FOLDERS:
        files += [
            path
            for path in (ROOT / folder).rglob("*.py")
            if not SKIPPED_PARTS & set(path.parts)
        ]
    return sorted(files)


def collect(node: ast.AST, inside_function: bool, found: list[tuple[int, str]]) -> None:
    for child in ast.iter_child_nodes(node):
        is_function = isinstance(child, FUNCTIONS)
        if inside_function and (is_function or isinstance(child, ast.ClassDef)):
            found.append((child.lineno, child.name))
        collect(child, inside_function or is_function, found)


def definitions_inside_functions(tree: ast.AST) -> list[tuple[int, str]]:
    """The line and name of every def and class that sits inside a function."""
    found: list[tuple[int, str]] = []
    collect(tree, False, found)
    return found


def test_the_check_sees_a_nested_function_and_a_nested_class():
    source = (
        "def outer():\n    def inner():\n        pass\n    class Local:\n        pass\n"
    )

    assert definitions_inside_functions(ast.parse(source)) == [
        (2, "inner"),
        (4, "Local"),
    ]


def test_the_check_leaves_methods_and_module_level_definitions_alone():
    source = (
        "class A:\n    def method(self):\n        pass\n\n\ndef function():\n    pass\n"
    )

    assert definitions_inside_functions(ast.parse(source)) == []


def test_no_function_or_class_is_defined_inside_a_function():
    found = {}
    for path in python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if inside := definitions_inside_functions(tree):
            found[str(path.relative_to(ROOT))] = inside

    assert found == {}
