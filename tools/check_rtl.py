"""Look for the mistakes which only fail when the design is generated.

The RTL of this project can only be built where ``pycde`` is installed, which is
not everywhere, so a mistake such as using an imported function as if it were a
table is only found on the machine which builds it.  This script looks for the
cheap ones without importing anything:

* an imported function which is never called - used as a value, iterated, or
  subscripted - because the name was meant as the result of the call;
* a register of a PyCDE module which is declared but never assigned.
"""

from __future__ import annotations

import ast
import glob
import sys

REPO = "pycde_example"
#: the registers which are elements of a list and are assigned one by one
LIST_ELEMENTS = {"reg_re", "reg_im"}


def parse(path: str) -> ast.Module:
    """The syntax tree of a source file."""
    with open(path) as handle:
        return ast.parse(handle.read())


def functions_of(sources: list[str]) -> dict[str, set[str]]:
    """The name of every top level function, per module."""
    result: dict[str, set[str]] = {}
    for path in sources:
        module = path.split("/")[-1][:-3]
        for node in parse(path).body:
            if isinstance(node, ast.FunctionDef):
                result.setdefault(module, set()).add(node.name)
    return result


def uncalled_imported_functions(sources: list[str],
                                functions: dict[str, set[str]]) -> list[str]:
    """Imported functions which are used somewhere without being called."""
    problems = []
    for path in sources:
        tree = parse(path)
        origin = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[-1]
                for alias in node.names:
                    origin[alias.asname or alias.name] = (module, alias.name)
        if not origin:
            continue
        # every place a name is used as a plain value, which is any Name that is
        # not the function of a call
        called = {node.func.id for node in ast.walk(tree)
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Name):
                continue
            local = origin.get(node.id)
            if not local:
                continue
            module, original = local
            if original not in functions.get(module, set()):
                continue
            if node.id in called:
                continue
            problems.append(f"{path}:{node.lineno}: '{node.id}' is a function of "
                            f"{module} but is never called")
    return problems


def registers_without_assignment(sources: list[str]) -> list[str]:
    """The registers of a module which are declared but never assigned."""
    problems = []
    for path in sources:
        tree = parse(path)
        for func in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
            declared, assigned = set(), set()
            for node in ast.walk(func):
                is_reg = (isinstance(node, ast.Assign)
                          and isinstance(node.value, ast.Call)
                          and getattr(node.value.func, "id", None) == "Reg")
                if is_reg and isinstance(node.targets[0], ast.Name):
                    declared.add(node.targets[0].id)
                if (isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "assign"
                        and isinstance(node.func.value, ast.Name)):
                    assigned.add(node.func.value.id)
            for name in sorted(declared - assigned - LIST_ELEMENTS):
                problems.append(f"{path}: {name} in {func.name} is never assigned")
    return problems


def main() -> int:
    sources = sorted(glob.glob(f"{REPO}/*.py"))
    functions = functions_of(sources)
    problems = uncalled_imported_functions(sources, functions)
    problems += registers_without_assignment(sources)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
