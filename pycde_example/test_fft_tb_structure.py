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


def test_the_reference_of_every_configuration_can_be_built():
    """Every configuration has to get a working reference model.

    The factories are called without pycde - the model side does not need it -
    so a mistake in how a parameter is handed to the model is caught here
    instead of while the RTL is being generated.
    """
    from pycde_example.fft_configs import FFT_CONFIGS
    from pycde_example.fft_tb import mixed_radix_reference

    for config in FFT_CONFIGS:
        params = config["params"]
        reference = mixed_radix_reference(
            params, params["width"], params["points"],
            params["ordering"] == "dit",
            params.get("scaling", "stage") == "stage",
            params["inverse"], params.get("twiddle_mode", "rom"))
        frame = [(0, 0)] * params["points"]
        result = reference(frame)
        assert len(result) == params["points"], config["name"]


def test_every_test_module_uses_the_bench_of_its_topology():
    """A streaming topology needs the streaming bench.

    The delay commutator chains are free running: the first frame only fills them
    and a spectrum leaves one frame late.  The frame based bench sends a frame and
    waits for a spectrum, which against such a chain reads the spectrum of the
    frame before it - a mistake which looks like a datapath bug and is not one.
    The multi path architectures need the bench which expects the delay as well.
    """
    from pycde_example.fft_configs import FFT_CONFIGS

    bench_of = {"sdc": "make_streaming_fft_tests", "mdc": "make_mdc_tests"}
    tree_root = BENCH.parent
    for config in FFT_CONFIGS:
        params = config["params"]
        style = params.get("pipeline_style", "")
        if style not in bench_of:
            continue
        module = config["test_module"].split(".")[-1]
        path = tree_root / f"{module}.py"
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        used = {node.attr if isinstance(node, ast.Attribute) else node.id
                for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)}
        assert bench_of[style] in used, (
            f"{module} builds a {style} but does not use {bench_of[style]}")


def test_every_test_module_unpacks_the_bench_it_calls():
    """The number of tests a bench returns has to match the unpacking.

    `make_streaming_fft_tests` returns three tests, the other benches two, and a
    module which unpacks the wrong number fails while the suite is being collected
    - one CI round away from the edit which introduced it.
    """
    returns = {}
    for node in parse().body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("make_"):
            for child in ast.walk(node):
                if (isinstance(child, ast.Return)
                        and isinstance(child.value, ast.Tuple)):
                    returns[node.name] = len(child.value.elts)

    tree_root = BENCH.parent
    for path in sorted(tree_root.glob("test_fft_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            call = node.value
            if not (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Name)
                    and call.func.id in returns):
                continue
            bench = call.func.id
            for target in node.targets:
                if not isinstance(target, ast.Tuple):
                    continue
                assert len(target.elts) == returns[bench], (
                    f"{path.name} unpacks {len(target.elts)} names from "
                    f"{bench}, which returns {returns[bench]}")
