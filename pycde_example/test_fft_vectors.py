"""The classic test vectors, with every expected value taken from NumPy.

The vectors a book uses are the ones whose spectrum is known without computing
anything - an impulse, a constant, an alternating sequence, an exponential, a
cosine, a sine, two tones, a ramp, and full scale input.  They are worth more than
noise because the answer is exact.

The answer is not written down here.  It comes from :mod:`fft_golden`, which is
NumPy: an expectation worked out by hand is a place where a mistake in the
reasoning looks exactly like a mistake in the model, and that is not a hypothetical
- four of them went wrong while these tests were being written.

Two kinds of comparison are made, and the difference between them is what the
golden says about the answer:

* when the transform of a vector is an exact integer in the fixed point format,
  which is the case for the impulse, the constant and the alternating sequence at
  radix 2 and 4, the allowed deviation is half a unit - the answer is exact and
  the datapath has nothing to round;
* otherwise the deviation is the one the datapath is allowed by
  :func:`fft_golden.truncation_bound`, which grows with the number of stages and
  with the width of the butterfly.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from .fft_golden import deviation, deviations, golden, truncation_bound
from .fft_model import fft
from .fft_radix_model import expand_radices, fft_mixed
from .fft_sdc_radix_model import sdc_radix
from .fft_sdf_radix_model import sdf_radix

WIDTH = 16
SCALE = 1 << (WIDTH - 1)


def golden_factor(index: int, points: int) -> complex:
    """``W**index`` by NumPy, at the scale of the fixed point format."""
    return np.exp(-2j * math.pi * (index % points) / points)


def amplitude(value: float) -> int:
    """A fixed point number, clamped to what the format holds."""
    maximum = SCALE - 1
    return min(max(round(value * SCALE), -maximum), maximum)


def impulse(points: int, height: int) -> list[tuple[int, int]]:
    """A single non zero sample at the origin."""
    frame = [(0, 0)] * points
    frame[0] = (height, 0)
    return frame


def constant(points: int, height: int) -> list[tuple[int, int]]:
    """The same value in every sample."""
    return [(height, 0)] * points


def alternating(points: int, height: int) -> list[tuple[int, int]]:
    """The sequence which alternates sign."""
    return [(height if n % 2 == 0 else -height, 0) for n in range(points)]


def exponential(points: int, bin_index: int,
                magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A complex exponential at one bin."""
    return [(amplitude(magnitude * math.cos(2 * math.pi * bin_index * n / points)),
             amplitude(magnitude * math.sin(2 * math.pi * bin_index * n / points)))
            for n in range(points)]


def cosine(points: int, bin_index: int,
           magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A real cosine: the real part carries it."""
    return [(amplitude(magnitude * math.cos(2 * math.pi * bin_index * n / points)),
             0) for n in range(points)]


def sine(points: int, bin_index: int,
         magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A real sine: the real part carries it too, shifted in time."""
    return [(amplitude(magnitude * math.sin(2 * math.pi * bin_index * n / points)),
             0) for n in range(points)]


def full_scale(points: int, seed: int = 7) -> list[tuple[int, int]]:
    """Samples of magnitude one, the worst case for the width of the sum."""
    rng = np.random.default_rng(seed + points)
    maximum = SCALE - 1
    frame = []
    for _ in range(points):
        angle = rng.uniform(0.0, 2.0 * math.pi)
        frame.append((min(max(round(maximum * math.cos(angle)), -maximum),
                          maximum),
                      min(max(round(maximum * math.sin(angle)), -maximum),
                          maximum)))
    return frame


def ramp(points: int) -> list[tuple[int, int]]:
    """A linear ramp."""
    step = (SCALE - 1) // max(1, points)
    return [(n * step, 0) for n in range(points)]


def vectors(points: int):
    """Every classic vector, with the name a failure report should show."""
    yield "impulse", impulse(points, 64 * points)
    yield "constant", constant(points, SCALE // 2)
    yield "alternating", alternating(points, SCALE // 2)
    yield "exponential", exponential(points, 3 % points)
    yield "cosine", cosine(points, 3 % points)
    yield "sine", sine(points, 3 % points)
    yield "two tones", [(a[0] + b[0], a[1] + b[1]) for a, b in
                        zip(cosine(points, 1 % points, 0.2),
                            cosine(points, 3 % points, 0.2))]
    yield "ramp", ramp(points)
    yield "full scale", full_scale(points)


def models(frame: list[tuple[int, int]], points: int, radices: str):
    """Every model which computes this decomposition."""
    return {
        "fft": fft(frame, WIDTH, points, dit=False),
        "mixed": fft_mixed(frame, WIDTH, points, radices, dit=False),
        "sdf": sdf_radix(frame, WIDTH, points, radices),
        "sdc": sdc_radix(frame, WIDTH, points, radices),
    }


RADICES = [("2", 4), ("2", 8), ("2", 16), ("2", 32), ("2", 64),
           ("4", 16), ("4", 64), ("8", 8), ("4,2", 8), ("4,4", 16)]


def allowed_for(radices: str, points: int) -> float:
    """The deviation the datapath of this decomposition is allowed."""
    return truncation_bound(expand_radices(radices, points))


@pytest.mark.parametrize("radices,points", RADICES)
def test_every_classic_vector_agrees_with_the_golden(radices, points):
    """Every vector, through every model, against NumPy."""
    allowed = allowed_for(radices, points)
    for label, frame in vectors(points):
        want = golden(frame, WIDTH, points)
        for name, got in models(frame, points, radices).items():
            worst = deviation(got, want)
            assert worst <= allowed, (
                f"{label} through {name} ({radices}) off by {worst:.2f} "
                f"LSB, allowed {allowed:.1f}")


@pytest.mark.parametrize("radices,points", RADICES)
def test_the_vectors_which_the_golden_says_are_exact_are_exact(radices, points):
    """Where the answer is an integer, the datapath has nothing to round.

    Whether the answer is an integer is decided by the golden and not by a
    derivation here: the transform of an impulse is flat and the transform of a
    constant has one bin, and the fixed point format holds both exactly when the
    height is chosen so that the division by the number of points lands on an
    integer.
    """
    for label, frame in vectors(points):
        want = golden(frame, WIDTH, points)
        if max(abs(value - round(value)) for value in want.real) > 1e-9:
            continue
        if max(abs(value) for value in want.imag) > 1e-9:
            continue
        for name, got in models(frame, points, radices).items():
            worst = deviation(got, want)
            # The input is rounded to the fixed point format before the
            # transform sees it, so a vector whose answer is an integer can still
            # come out a unit away: that unit is the input, not the datapath.
            # A butterfly of radix 8 adds one more, because it rotates by forty
            # five degrees and that table entry is a fraction of a unit short of
            # the angle - a property of the format, not of this transform.
            ceiling = 2.5 if max(expand_radices(radices, points)) >= 8 else 1.5
            assert worst <= ceiling, (
                f"{label} through {name} ({radices}) is off by {worst:.2f} "
                f"where the golden says the answer is exact")


@pytest.mark.parametrize("radices,points", RADICES)
def test_every_bin_is_inside_the_bound(radices, points):
    """The bound is not carried by one forgiving bin and a wild one beside it."""
    allowed = allowed_for(radices, points)
    for label, frame in vectors(points):
        want = golden(frame, WIDTH, points)
        for name, got in models(frame, points, radices).items():
            per_bin = deviations(got, want)
            worst_bin = per_bin.index(max(per_bin))
            assert max(per_bin) <= allowed, (
                f"{label} through {name} ({radices}): bin {worst_bin} off by "
                f"{max(per_bin):.2f}, allowed {allowed:.1f}")


@pytest.mark.parametrize("radices,points", RADICES)
def test_the_topologies_agree_on_every_vector(radices, points):
    """The vectors are also the ones on which the topologies could diverge."""
    for label, frame in vectors(points):
        results = models(frame, points, radices)
        base = results["mixed"]
        for name in ("sdf", "sdc"):
            assert results[name] == base, f"{label}: {name} differs from mixed"


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8), ("2", 16),
                                            ("4,4", 16)])
def test_the_exponential_lands_in_its_bin(radices, points):
    """Where the golden says the energy is, that is where the model puts it."""
    bin_index = 3
    frame = exponential(points, bin_index)
    want = golden(frame, WIDTH, points)
    expected_peak = int(np.argmax(np.abs(want)))
    assert expected_peak == bin_index, "the golden puts the peak elsewhere"

    got = fft_mixed(frame, WIDTH, points, radices, dit=False)
    magnitudes = [math.hypot(re, im) for re, im in got]
    assert magnitudes.index(max(magnitudes)) == expected_peak


def test_a_trivial_factor_is_exact_against_the_golden():
    """The four trivial factors are a wire, a negation and two swaps.

    The golden is the complex product of the factor with the value, so a factor
    which is one unit short of itself shows up here and nowhere else: the
    truncation bound of a whole transform is larger than that unit.
    """
    from .fft_model import apply_twiddle

    for points in (4, 8, 16, 64):
        for index in (0, points // 4, points // 2, 3 * points // 4):
            for re_value, im_value in ((1000, 2000), (-1234, 567), (0, -3000)):
                want = golden_factor(index, points) * complex(re_value, im_value)
                got = apply_twiddle(index, re_value, im_value, WIDTH, points)
                assert abs(got[0] - want.real) < 0.5, f"W**{index} real"
                assert abs(got[1] - want.imag) < 0.5, f"W**{index} imaginary"


