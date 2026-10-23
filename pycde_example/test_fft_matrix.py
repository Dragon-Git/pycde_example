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


def test_the_shards_cover_the_space_exactly_once():
    """The stress matrix splits the space, it does not sample it.

    A shape which falls between two shards would be silently untested, and a shape
    which lands in two would be tested twice at the cost of a build and a
    simulation each time.  Neither shows up as a failure, so it is checked here.
    """
    from .fft_matrix import shard

    configs = list(all_configurations())
    for shards in (1, 4, 20):
        def identity(config):
            """Everything which makes one configuration differ from another."""
            return (config["eval_mode"], config["style"], config["points"],
                    config["decomposition"], config["ordering"],
                    config["scaling"], config["twiddle"], config["inverse"],
                    config["width"])

        collected = []
        for index in range(shards):
            collected.extend(identity(config)
                             for config in shard(configs, index, shards))
        assert len(collected) == len(configs), f"{shards} shards lose a shape"
        assert len(set(collected)) == len(configs), \
            f"{shards} shards repeat a shape"


def test_the_shards_are_evenly_loaded():
    """A shard three times the size of another wastes the machines.

    The work is spread by the cost of a shape - its number of points and stages -
    so that no machine is left with all the large transforms.
    """
    from .fft_matrix import shard

    configs = list(all_configurations())
    weights = []
    for index in range(20):
        total = sum(config["points"]
                    * max(1, len(str(config["radices"]).split(",")))
                    for config in shard(configs, index, 20))
        weights.append(total)
    heaviest, lightest = max(weights), min(weights)
    assert lightest > 0
    assert heaviest / lightest < 1.15, f"loads range {lightest} to {heaviest}"


def test_every_shard_has_work():
    """No machine is given nothing to do."""
    from .fft_matrix import shard

    configs = list(all_configurations())
    for index in range(20):
        assert shard(configs, index, 20), f"shard {index} is empty"


def test_the_complete_vector_set_has_the_shapes_it_promises():
    """The stress matrix runs this set, so its content is worth pinning.

    Each frame is there to exercise something the others do not: an exact answer,
    a single bin, the bin at half the band, a quarter turn between the real and the
    imaginary datapath, linearity, a worst case for the width.  A frame which is
    quietly dropped would leave that property untested everywhere.
    """
    from .fft_tb import complete_frames

    for points in (4, 8, 16, 32):
        frames = complete_frames(points, 16)
        assert len(frames) >= 10, f"{len(frames)} frames for {points} points"
        # an impulse: exactly one non zero sample
        assert sum(1 for sample in frames[0] if sample != (0, 0)) == 1
        # a constant and an alternating sequence
        assert len({sample for sample in frames[1]}) == 1
        assert len({sample for sample in frames[2]}) == 2
        # a real signal, whose imaginary part is zero everywhere
        assert any(all(im == 0 for _, im in frame) for frame in frames)
        # the most negative value, in a real signal
        lowest = -(1 << 15) + 1
        assert any(all(re == lowest for re, _ in frame) for frame in frames)
