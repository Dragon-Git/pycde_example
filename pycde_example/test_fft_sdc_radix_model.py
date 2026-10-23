"""Tests of the radix R delay commutator chain.

The chain differs from the feedback one in shape, not in arithmetic: no register
is fed back, the results travel forward through lines of their own.  So the
checks are the same ones - it has to agree with the radix 2 commutator chain when
every radix is 2, and with the mixed radix model when one is not - plus the
storage, which is the same as the feedback chain's.
"""

from __future__ import annotations

import random

import pytest

from .fft_model import to_fixed
from .fft_radix_model import fft_mixed
from .fft_sdc_model import sdc
from .fft_sdc_radix_model import RadixSdcStage, sdc_radix, sdc_radix_storage


def random_frame(points: int, width: int, seed: int = 0,
                 amplitude: float = 0.3) -> list[tuple[int, int]]:
    """A deterministic random frame."""
    rng = random.Random(seed)
    return [(to_fixed(rng.uniform(-amplitude, amplitude), width),
             to_fixed(rng.uniform(-amplitude, amplitude), width))
            for _ in range(points)]


@pytest.mark.parametrize("width,points", [(12, 4), (16, 8), (16, 16)])
@pytest.mark.parametrize("scale", [True, False])
def test_radix_two_is_the_radix_two_chain(width, points, scale):
    """With every radix 2 the chain is the one which already ships."""
    amplitude = 0.3 if scale else 0.01
    frame = random_frame(points, width, seed=width + points,
                         amplitude=amplitude)
    assert (sdc_radix(frame, width, points, "2", scale=scale)
            == sdc(frame, width, points, scale=scale))


@pytest.mark.parametrize("radices,points", [
    ("4", 4), ("4", 16), ("8", 8),
    ("4,2", 8), ("2,4", 8), ("4,4", 16), ("8,2", 16), ("2,8", 16),
])
def test_a_larger_radix_computes_the_transform(radices, points):
    """The chain is bit exact with the mixed radix model."""
    width = 16
    frame = random_frame(points, width, seed=points + len(radices))
    assert (sdc_radix(frame, width, points, radices)
            == fft_mixed(frame, width, points, radices, dit=False, scale=True))


def test_the_chain_has_no_feedback():
    """Every line is a forward one: the stage holds results, not a loop."""
    stage = RadixSdcStage(16, 16, 4, 16)
    # the samples and the results each have R - 1 lines of their own
    assert len(stage.sample_lines) == 3
    assert len(stage.result_lines) == 3
    assert [line.depth for line in stage.sample_lines] == [4, 8, 12]
    assert [line.depth for line in stage.result_lines] == [4, 8, 12]


def test_the_storage_is_twice_the_feedback_stage():
    """The commutator keeps a second set of lines, which is the price of it."""
    feedback = sum(k * 4 for k in range(1, 4))
    commutator = RadixSdcStage(16, 16, 4, 16).storage()
    assert commutator == 2 * feedback


def test_the_storage_grows_with_the_radix():
    """Both topologies pay the same way for a larger butterfly."""
    points = 64
    assert sdc_radix_storage(points, "2") == 126
    assert sdc_radix_storage(points, "4") == 252
    assert sdc_radix_storage(points, "8") == 504


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8)])
def test_the_chain_is_deterministic(radices, points):
    """Two runs of the same frame agree."""
    frame = random_frame(points, 16, seed=5)
    assert (sdc_radix(frame, 16, points, radices)
            == sdc_radix(frame, 16, points, radices))


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8), ("4,2", 8)])
def test_an_impulse_is_flat(radices, points):
    """An impulse in the input is flat in the output."""
    width = 16
    frame = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    got = sdc_radix(frame, width, points, radices)
    expected = to_fixed(0.5 / points, width)
    for k in range(points):
        assert got[k] == (expected, 0), f"bin {k} is {got[k]}"


def test_both_topologies_agree():
    """The two chains compute the same spectrum through different datapaths."""
    from .fft_sdf_radix_model import sdf_radix
    width, points = 16, 16
    frame = random_frame(points, width, seed=11)
    for radices in ("4", "8,2", "4,4"):
        assert (sdf_radix(frame, width, points, radices)
                == sdc_radix(frame, width, points, radices))
