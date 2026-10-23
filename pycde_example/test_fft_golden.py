"""Check every model against an independent golden reference.

The models share their arithmetic.  `fft_mixed`, `sdf_radix` and `sdc_radix` all
rotate with `apply_twiddle`, so a mistake there is a mistake in all of them, and
comparing them with each other finds nothing - which is exactly what happened:
`+j` was missing from the twiddle arithmetic and every model agreed on the wrong
answer because every model made the same mistake.

The golden reference here is NumPy's transform.  It shares no code with any model
in this package, so it cannot inherit a mistake from one, and a disagreement with
it is always worth looking at.

Two things are asked of a model:

* it agrees with the golden within a bound derived from the datapath, see
  :func:`deviation_bound`;
* every topology is bit identical with every other one which computes the same
  decomposition, because they differ in the datapath and not in the arithmetic.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from .fft_golden import deviation, golden, truncation_bound
from .fft_model import fft, to_fixed
from .fft_radix_model import expand_radices, fft_mixed
from .fft_sdc_radix_model import sdc_radix
from .fft_sdf_radix_model import sdf_radix

WIDTH = 16


def frames(points: int, width: int = WIDTH):
    """Frames of different shapes: an impulse, a tone and noise."""
    scale = 1 << (width - 1)
    impulse = [(0, 0)] * points
    impulse[0] = (to_fixed(0.5, width), 0)
    yield "impulse", impulse

    tone = []
    for n in range(points):
        angle = 2.0 * math.pi * 3 * n / points
        tone.append((to_fixed(0.4 * math.cos(angle), width),
                     to_fixed(0.4 * math.sin(angle), width)))
    yield "tone", tone

    rng = np.random.default_rng(12345 + points)
    noise = []
    for _ in range(points):
        radius = rng.uniform(0.0, 0.3)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        noise.append((round(scale * radius * math.cos(angle)),
                      round(scale * radius * math.sin(angle))))
    yield "noise", noise


def worst_deviation(compute, points: int) -> float:
    """The largest deviation of a model from the golden over the frames."""
    worst = 0.0
    for _, frame in frames(points):
        worst = max(worst, deviation(compute(frame),
                                     golden(frame, WIDTH, points)))
    return worst


@pytest.mark.parametrize("points", [4, 8, 16, 32, 64])
def test_the_radix_two_model_agrees_with_the_golden(points):
    """The radix 2 model is the one all the others generalise."""
    radices = [2] * int(math.log2(points))
    assert worst_deviation(
        lambda f: fft(f, WIDTH, points, dit=False), points) \
        <= truncation_bound(radices)


@pytest.mark.parametrize("radices,points", [
    ("2", 4), ("2", 8), ("2", 16), ("2", 32), ("2", 64),
    ("4", 4), ("4", 16), ("4", 64), ("8", 8), ("8", 64),
    ("4,2", 8), ("2,4", 8), ("4,4", 16), ("8,2", 16), ("2,8", 16),
])
def test_every_mixed_radix_model_agrees_with_the_golden(radices, points):
    """The mixed radix decomposition computes the transform."""
    stages = expand_radices(radices, points)
    assert worst_deviation(
        lambda f: fft_mixed(f, WIDTH, points, radices, dit=False),
        points) <= truncation_bound(stages)


@pytest.mark.parametrize("radices,points", [
    ("4", 4), ("4", 16), ("8", 8), ("4,2", 8), ("4,4", 16), ("8,2", 16),
])
def test_the_delay_lines_agree_with_the_golden(radices, points):
    """Both delay line topologies compute the transform, not just each other."""
    stages = expand_radices(radices, points)
    for name, compute in (("sdf", lambda f: sdf_radix(f, WIDTH, points, radices)),
                          ("sdc", lambda f: sdc_radix(f, WIDTH, points, radices))):
        deviation = worst_deviation(compute, points)
        assert deviation <= truncation_bound(stages), f"{name} off by {deviation}"


@pytest.mark.parametrize("radices,points", [
    ("4", 16), ("4,4", 16), ("8", 8), ("4,2", 8), ("8,2", 16),
])
def test_the_topologies_are_bit_identical(radices, points):
    """The topologies differ in the datapath, not in the arithmetic.

    This is what makes one model enough for all of them: if they ever disagree,
    one of them has a bug the golden comparison may not catch, because the golden
    only sees a deviation of a couple of units.
    """
    for label, frame in frames(points):
        mixed = fft_mixed(frame, WIDTH, points, radices, dit=False)
        delay = sdf_radix(frame, WIDTH, points, radices)
        commutator = sdc_radix(frame, WIDTH, points, radices)
        assert mixed == delay, f"{radices} [{label}]: the delay line differs"
        assert delay == commutator, f"{radices} [{label}]: the commutator differs"


