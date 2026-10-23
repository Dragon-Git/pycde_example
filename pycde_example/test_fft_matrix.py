"""Check every configuration the generator accepts, against NumPy.

`fft_configs.py` holds the shapes which are built into RTL and simulated, and there
are about fifty of them because every one costs a Verilator build.  The parameter
space is far larger - every number of points, every decomposition of it, both
orderings, both scalings, every twiddle generator - and none of that breadth needs
RTL to be worth checking: a mistake in a decomposition lives in the arithmetic.

So this file sweeps the whole accepted space and compares each configuration with
the golden.  The enumeration follows the rules `fft.py` enforces, and it is written
down in `fft_matrix.py` beside the models, so a rule which changes without the
coverage changing shows up as a gap rather than as silence.

The RTL keeps its own matrix, which is a selection: what it verifies is the
datapath, and the datapath of a topology is the same shape whatever the number of
points and the decomposition are - the arithmetic underneath it is what this file
covers whole.
"""

from __future__ import annotations

import pytest

from .fft_matrix import all_configurations, as_text, check, decompositions, is_legal, model_for, summary


def shapes():
    """Every distinct computation in the accepted space.

    A configuration is identified by what it computes - the topology, the number of
    points, the decomposition, the ordering and the twiddle generator - and not by
    the scaling or the width, which only change how much the datapath truncates.
    """
    distinct = {}
    for config in all_configurations():
        key = (config["eval_mode"], config["style"], config["points"],
               config["decomposition"], config["ordering"],
               config["twiddle"])
        distinct.setdefault(key, []).append(config)
    return sorted(distinct)


def name_of(shape) -> str:
    """A readable identifier for a parameterisation."""
    eval_mode, style, points, decomposition, ordering, twiddle = shape
    del eval_mode
    return (f"{style}-N{points}-R{as_text(decomposition)}"
            f"-{ordering}-{twiddle}")


@pytest.mark.parametrize("shape", shapes(), ids=name_of)
def test_every_accepted_configuration_is_right(shape):
    """The whole accepted space, each shape against the golden."""
    eval_mode, style, points, decomposition, ordering, twiddle = shape
    width = 16
    problems = check(eval_mode, style, points, decomposition, width, twiddle,
                     ordering)
    assert not problems, f"{name_of(shape)}: {problems}"


def test_the_space_is_the_size_the_rules_say():
    """A rule which changes has to change this number.

    The count is not the point; the point is that it cannot drift.  A shape which
    starts being accepted, or stops, moves this number and whoever moved it has to
    say why.
    """
    counts = summary()
    assert counts["total"] == 1752, counts
    assert counts["memory"] == 480
    assert counts["total"] == sum(
        value for key, value in counts.items() if key != "total")


def test_every_decomposition_of_a_transform_is_offered():
    """The decompositions of a number of points are all of them.

    `"2"` on sixteen points is one shape and `"4,4"` is another; the enumeration
    has to reach both, and the pure radix 2 one in particular, since it is what
    every existing configuration uses.
    """
    assert [as_text(d) for d in decompositions(4)] == ["2", "4"]
    assert [as_text(d) for d in decompositions(8)] == ["2", "2,4", "4,2", "8"]
    for points in (8, 16, 32, 64):
        texts = {as_text(d) for d in decompositions(points)}
        assert "2" in texts, f"the pure radix 2 shape of {points} points is absent"


def test_a_radix_larger_than_two_is_the_pipelined_architectures_only():
    """The rule `fft.py` enforces, checked where the space is enumerated."""
    assert is_legal("memory_based", "sdf", 16, (4, 4), "dit", "rom", False,
                    16) is not None
    assert is_legal("pipelined", "unrolled", 16, (4, 4), "dit", "rom", False,
                    16) is None


def test_the_multi_path_architectures_need_the_split():
    """Their first stage is the one which splits the frame, and it is a radix 2."""
    assert is_legal("pipelined", "mdf", 16, (4, 4), "dif", "rom", False,
                    16) is not None
    assert is_legal("pipelined", "mdf", 16, (2, 8), "dif", "rom", False,
                    16) is None
    # two points leaves the chains with a single point, which is no transform
    assert is_legal("pipelined", "mdf", 2, (2,), "dif", "rom", False,
                    16) is not None


def test_the_commutator_chain_is_the_decimation_in_frequency_one():
    """Its schedule is fixed, so the ordering is not a choice it has."""
    assert is_legal("pipelined", "sdc", 16, (2, 2, 2, 2), "dit", "rom", False,
                    16) is not None
    assert is_legal("pipelined", "sdc", 16, (2, 2, 2, 2), "dif", "rom", False,
                    16) is None


def test_every_configuration_has_a_model():
    """A shape which is accepted has to be computable, or the rule is wrong."""
    for config in all_configurations():
        build = model_for(config["eval_mode"], config["style"],
                          config["points"], config["decomposition"],
                          config["twiddle"], config["ordering"])
        assert build is not None, config


def test_the_twiddle_generators_are_all_covered():
    """Every generator is part of the space, and each is its own arithmetic."""
    generators = {config["twiddle"] for config in all_configurations()}
    assert generators == {"rom", "cordic", "hybrid", "no_mem_cascade",
                          "no_mem_logic"}
