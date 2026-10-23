"""Structural checks of the test bench module itself.

The test bench cannot be imported without pycde, so the modules which build the
cocotb tests are checked on the syntax tree instead: a factory which forgets to
return its tests hands the caller ``None``, and the failure only shows up as a
``TypeError`` while the suite is being collected - which is a whole CI run away
from the machine the mistake was made on.
"""

from __future__ import annotations

import ast
from pathlib import Path

BENCH = Path(__file__).with_name("fft_tb.py")


def parse() -> ast.Module:
    """The syntax tree of the test bench."""
    return ast.parse(BENCH.read_text(encoding="utf-8"))


def factories() -> list[ast.FunctionDef]:
    """The functions which hand back the cocotb tests of a configuration."""
    return [node for node in parse().body
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("make_") and node.name.endswith("_tests")]


def test_the_bench_defines_factories():
    """The bench is where the cocotb tests come from."""
    names = {node.name for node in factories()}
    assert "make_fft_tests" in names
    assert "make_mdc_tests" in names


def test_every_factory_returns_its_tests():
    """A factory which returns nothing breaks every configuration it serves."""
    missing = []
    for node in factories():
        returns = [child for child in ast.walk(node)
                   if isinstance(child, ast.Return)]
        if not returns:
            missing.append(node.name)
    assert not missing, f"these factories return nothing: {missing}"


def test_every_factory_takes_keyword_parameters():
    """The configurations are passed through as keyword arguments."""
    for node in factories():
        if node.args.args:
            assert node.args.args[0].arg != "self", f"{node.name} is a method"
        assert node.args.kwarg is not None, f"{node.name} takes no **kwargs"


def test_the_shared_helpers_are_module_level():
    """The tests of a factory call the helpers, so they have to be importable."""
    names = {node.name for node in parse().body
             if isinstance(node, ast.AsyncFunctionDef)}
    assert "stream_frames" in names
    assert "collect_spectra" in names
