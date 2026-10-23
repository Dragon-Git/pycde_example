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

from .fft_model import fft, to_fixed
from .fft_radix_model import expand_radices, fft_mixed
from .fft_sdc_radix_model import sdc_radix
from .fft_sdf_radix_model import sdf_radix

WIDTH = 16


def golden(frame: list[tuple[int, int]], width: int, points: int) -> np.ndarray:
    """The transform of a fixed point frame, computed by NumPy.

    The integer ``re`` stands for ``re / 2**(width - 1)``, so the frame is
    brought to that scale, transformed, brought back, and divided by the number
    of points because the datapath scales by ``1 / points`` in total.
    """
    scale = 1 << (width - 1)
    values = np.array([complex(re, im) for re, im in frame]) / scale
    return np.fft.fft(values) * scale / points


def deviation_bound(radices: list[int]) -> float:
    """The deviation from the golden the datapath is allowed.

    Every stage shifts its operands right, dropping up to a unit of the last bit
    per term, and every rotation truncates a product the same way, so a stage of
    radix ``R`` adds a couple of units per term and the stages add up.

    The constant is generous on purpose.  This bound is here to catch a model
    which is structurally wrong - those are off by thousands of units - and not
    to make a statement about one unit either way; the exact statement about a
    unit is the bit exact comparison against the RTL, which is a different test.
    """
    stages = len(radices)
    widest = max(int(math.log2(radix)) for radix in radices)
    return 8.0 * (stages + 1) * (widest + 1)


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
        want = golden(frame, WIDTH, points)
        for (re, im), value in zip(compute(frame), want):
            worst = max(worst, abs(re - value.real), abs(im - value.imag))
    return worst


@pytest.mark.parametrize("points", [4, 8, 16, 32, 64])
def test_the_radix_two_model_agrees_with_the_golden(points):
    """The radix 2 model is the one all the others generalise."""
    radices = [2] * int(math.log2(points))
    assert worst_deviation(
        lambda f: fft(f, WIDTH, points, dit=False), points) \
        <= deviation_bound(radices)


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
        points) <= deviation_bound(stages)


@pytest.mark.parametrize("radices,points", [
    ("4", 4), ("4", 16), ("8", 8), ("4,2", 8), ("4,4", 16), ("8,2", 16),
])
def test_the_delay_lines_agree_with_the_golden(radices, points):
    """Both delay line topologies compute the transform, not just each other."""
    stages = expand_radices(radices, points)
    for name, compute in (("sdf", lambda f: sdf_radix(f, WIDTH, points, radices)),
                          ("sdc", lambda f: sdc_radix(f, WIDTH, points, radices))):
        deviation = worst_deviation(compute, points)
        assert deviation <= deviation_bound(stages), f"{name} off by {deviation}"


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


def test_the_trivial_twiddle_factors_are_exact():
    """The four trivial factors are wiring, not multiplications.

    This is the check which would have caught `+j` going through the table: the
    golden comparison allows a few units, and a factor one unit short of itself is
    within that allowance.  Compared with the exact value, it is not.
    """
    from .fft_model import apply_twiddle
    for points in (4, 8, 16, 64):
        cases = (
            (0, (1000, 2000), (1000, 2000)),
            (points // 4, (1000, 2000), (2000, -1000)),
            (points // 2, (1000, 2000), (-1000, -2000)),
            (3 * points // 4, (1000, 2000), (-2000, 1000)),
        )
        for index, value, want in cases:
            got = apply_twiddle(index, value[0], value[1], WIDTH, points)
            assert got == want, f"W**{index} of {points} points gave {got}"
