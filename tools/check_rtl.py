"""Check the generated RTL sources for the mistakes PyCDE reports late.

The elaboration of a PyCDE module fails with "Uninitialized backedges remain"
when a register is declared but never assigned - the message names the module
but not the register, and it only shows up when the design is compiled.  The
check looks for that, and for an instantiation which does not drive every input
port, before the build runs.
"""

from __future__ import annotations

import ast
import glob
import sys

#: the registers which are elements of a list, they are assigned one by one at
#: the end of the helper which builds the list
LIST_ELEMENTS = {"reg_re", "reg_im"}


def parse(path: str) -> ast.Module:
    """The syntax tree of a source file."""
    with open(path) as handle:
        return ast.parse(handle.read())


def registers_without_assignment(path: str) -> list[str]:
    """The names of the registers which are declared but never assigned."""
    tree = parse(path)
    missing = []
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
            missing.append(f"{path}: {name} in {func.name} is never assigned")
    return missing


def input_ports(path: str, module: str) -> list[str]:
    """The input ports of a module, read from its class body."""
    tree = parse(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == module:
            return [target.id for stmt in node.body
                    if isinstance(stmt, ast.Assign)
                    and isinstance(stmt.value, ast.Call)
                    and getattr(stmt.value.func, "id", "") == "Input"
                    for target in stmt.targets if isinstance(target, ast.Name)]
    return []


def instantiations_missing_ports(path: str, module: str,
                                 ports: list[str]) -> list[str]:
    """The instantiations of a module which do not drive every input."""
    tree = parse(path)
    missing = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Call)):
            continue
        inner = node.func
        name = getattr(inner.func, "id", None) or getattr(inner.func, "attr", None)
        if name != module:
            continue
        # an instantiation passes the ports as keywords, a parameterization
        # passes the parameters
        if "width" not in {k.arg for k in inner.keywords}:
            continue
        driven = {k.arg for k in node.keywords}
        absent = [p for p in ports if p not in driven]
        if absent:
            missing.append(f"{path}:{node.lineno}: {module} without {absent}")
    return missing


def main() -> int:
    sources = sorted(glob.glob("pycde_example/*.py"))
    problems = []
    for path in sources:
        problems += registers_without_assignment(path)
    ports = input_ports("pycde_example/fft_butterfly.py", "Butterfly")
    for path in sources:
        problems += instantiations_missing_ports(path, "Butterfly", ports)
    for problem in problems:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
