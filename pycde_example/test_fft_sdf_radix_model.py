"""Tests of the radix R delay feedback chain.

The strong check is the first one: with every radix 2 the chain has to agree with
the radix 2 chain this project already ships, bit for bit.  The rest say that the
larger butterflies compute the same transform.
"""

from __future__ import annotations

import random

import pytest

from .fft_model import to_fixed
from .fft_radix_model import expand_radices, fft_mixed, mixed_reverse
from .fft_sdf_model import sdf
from .fft_sdf_radix_model import RadixSdfStage, sdf_radix, sdf_radix_storage, sdf_radix_stream


def random_frame(points: int, width: int, seed: int = 0,
                 amplitude: float = 0.3) -> list[tuple[int, int]]:
    """A deterministic random frame."""
    rng = random.Random(seed)
    return [(to_fixed(rng.uniform(-amplitude, amplitude), width),
             to_fixed(rng.uniform(-amplitude, amplitude), width))
            for _ in range(points)]


@pytest.mark.parametrize("width,points", [(12, 4), (16, 8), (16, 16), (16, 32)])
@pytest.mark.parametrize("scale", [True, False])
def test_radix_two_is_the_radix_two_chain(width, points, scale):
    """With every radix 2 the chain is the one which already ships."""
    amplitude = 0.3 if scale else 0.01
    frame = random_frame(points, width, seed=width + points,
                         amplitude=amplitude)
    assert (sdf_radix(frame, width, points, "2", scale=scale)
            == sdf(frame, width, points, dit=False, scale=scale))


@pytest.mark.parametrize("radices,points", [
    ("4", 4), ("4", 16), ("8", 8), ("8", 64),
    ("4,2", 8), ("2,4", 8), ("4,4", 16), ("8,2", 16), ("2,8", 16),
])
def test_a_larger_radix_computes_the_transform(radices, points):
    """The chain is bit exact with the mixed radix model."""
    width = 16
    frame = random_frame(points, width, seed=points + len(radices))
    assert (sdf_radix(frame, width, points, radices)
            == fft_mixed(frame, width, points, radices, dit=False, scale=True))


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 64), ("4,4", 16)])
def test_the_latency_does_not_change_with_the_radix(radices, points):
    """A frame is ready after `points - 1` cycles whatever the radix is."""
    width = 16
    frame = random_frame(points, width, seed=points)
    stream = sdf_radix_stream(frame, width, points, radices,
                              cycles=points - 1 + 6 * points)
    radix_list = expand_radices(radices, points)
    window = stream[points - 1:points - 1 + points]
    natural = [window[mixed_reverse(i, radix_list)] for i in range(points)]
    assert natural == fft_mixed(frame, width, points, radices, dit=False)


def test_the_storage_of_a_two_point_chain():
    """A radix 2 stage on two points holds one register."""
    assert sdf_radix_storage(2, "2") == 1


def test_the_storage_of_a_radix_four_stage():
    """A radix 4 stage on four points holds three arms of depth one."""
    assert sdf_radix_storage(4, "4") == 6


def test_the_storage_grows_with_the_radix():
    """A larger butterfly trades registers for stages."""
    points = 64
    assert sdf_radix_storage(points, "2") == 63
    assert sdf_radix_storage(points, "4") == 126
    assert sdf_radix_storage(points, "8") == 252
    assert (sdf_radix_storage(points, "2")
            < sdf_radix_storage(points, "4")
            < sdf_radix_storage(points, "8"))


def test_a_stage_holds_one_register_per_arm():
    """Register `k` has depth `k * sub`, which is what the timing needs."""
    stage = RadixSdfStage(16, 16, 4, 16)
    assert stage.sub == 4
    assert [line.depth for line in stage.lines[1:]] == [4, 8, 12]
    assert stage.storage() == 24


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8)])
def test_the_chain_is_deterministic(radices, points):
    """Two runs of the same frame agree."""
    frame = random_frame(points, 16, seed=5)
    assert (sdf_radix(frame, 16, points, radices)
            == sdf_radix(frame, 16, points, radices))


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8), ("4,2", 8)])
def test_an_impulse_is_flat(radices, points):
    """An impulse in the input is flat in the output."""
    width = 16
    frame = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    got = sdf_radix(frame, width, points, radices)
    expected = to_fixed(0.5 / points, width)
    for k in range(points):
        assert got[k] == (expected, 0), f"bin {k} is {got[k]}"
