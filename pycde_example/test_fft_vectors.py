"""The classic test vectors of a transform, and their exact answers.

The vectors a book uses to test an FFT are the ones whose spectrum is known
without computing anything.  They are worth more than random noise, because the
answer is exact and the comparison does not need a tolerance:

* an impulse is flat - every bin holds the same value;
* a constant is a single bin, the zeroth;
* the alternating sequence is a single bin as well, the one at half the band;
* a complex exponential is a single bin at its own frequency;
* a real cosine or sine is two bins, halves of the amplitude, and the sine differs
  from the cosine by a factor of -j;
* two of them at once are their sum, which says that the datapath is linear;
* full scale input is the one which stresses the width of the datapath: the sum of
  `N` terms of magnitude one needs `N` times the range, and the scaling of the
  stages is what keeps it inside.

Those which a fixed point format can hold exactly - the impulse, the constant and
the alternating sequence - are checked against exact integers here rather than
against a floating point transform, so the check does not inherit an error from
the arithmetic it is checking.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from .fft_model import fft
from .fft_radix_model import expand_radices, fft_mixed
from .fft_sdc_radix_model import sdc_radix
from .fft_sdf_radix_model import sdf_radix

WIDTH = 16
SCALE = 1 << (WIDTH - 1)


def amplitude(value: float) -> int:
    """A fixed point number, clamped to what the format holds."""
    maximum = SCALE - 1
    return min(max(round(value * SCALE), -maximum), maximum)


def impulse(points: int, height: float = 0.5) -> list[tuple[int, int]]:
    """A single non zero sample at the origin."""
    frame = [(0, 0)] * points
    frame[0] = (amplitude(height), 0)
    return frame


def constant(points: int, height: float = 0.5) -> list[tuple[int, int]]:
    """The same value in every sample: the zeroth bin."""
    return [(amplitude(height), 0)] * points


def alternating(points: int, height: float = 0.5) -> list[tuple[int, int]]:
    """The sequence which alternates sign: the bin at half the band."""
    return [(amplitude(height if n % 2 == 0 else -height), 0)
            for n in range(points)]


def exponential(points: int, bin_index: int,
                magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A complex exponential at one bin."""
    return [(amplitude(magnitude * math.cos(2 * math.pi * bin_index * n / points)),
             amplitude(magnitude * math.sin(2 * math.pi * bin_index * n / points)))
            for n in range(points)]


def cosine(points: int, bin_index: int,
           magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A real cosine: two bins, each half the amplitude."""
    return [(amplitude(magnitude * math.cos(2 * math.pi * bin_index * n / points)),
             0) for n in range(points)]


def sine(points: int, bin_index: int,
         magnitude: float = 0.4) -> list[tuple[int, int]]:
    """A real sine: two bins, and the difference from the cosine is -j."""
    return [(amplitude(
        magnitude * math.sin(2 * math.pi * bin_index * n / points)), 0)
        for n in range(points)]


def full_scale(points: int, seed: int = 7) -> list[tuple[int, int]]:
    """Samples of magnitude one, which is the worst case for the width.

    The sum of `N` of them is `N` times the range of a sample, and it is the
    scaling of the stages which brings it back; a datapath which does not scale
    cannot hold this.
    """
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
    """A linear ramp, whose spectrum is a known closed form."""
    step = (SCALE - 1) // max(1, points)
    return [(n * step, 0) for n in range(points)]


def vectors(points: int):
    """Every classic vector, with the name a failure report should show."""
    yield "impulse", impulse(points)
    yield "constant", constant(points)
    yield "alternating", alternating(points)
    yield "exponential", exponential(points, 3 % points)
    yield "cosine", cosine(points, 3 % points)
    yield "sine", sine(points, 3 % points)
    yield "two tones", [(a[0] + b[0], a[1] + b[1]) for a, b in
                        zip(cosine(points, 1 % points, 0.2),
                            cosine(points, 3 % points, 0.2))]
    yield "ramp", ramp(points)
    yield "full scale", full_scale(points)


def compute_all(frame: list[tuple[int, int]], points: int, radices: str):
    """The four models, so a failure names all of them at once."""
    return {
        "fft": fft(frame, WIDTH, points, dit=False),
        "mixed": fft_mixed(frame, WIDTH, points, radices, dit=False),
        "sdf": sdf_radix(frame, WIDTH, points, radices),
        "sdc": sdc_radix(frame, WIDTH, points, radices),
    }


def golden(frame: list[tuple[int, int]], points: int) -> np.ndarray:
    """The transform, by NumPy."""
    values = np.array([complex(re, im) for re, im in frame]) / SCALE
    return np.fft.fft(values) * SCALE / points


def deviation(got: list[tuple[int, int]], want: np.ndarray) -> float:
    """The largest deviation, in units of the last bit."""
    worst = 0.0
    for (re, im), value in zip(got, want):
        worst = max(worst, abs(re - value.real), abs(im - value.imag))
    return worst


def bound(radices: str, points: int) -> float:
    """The deviation a datapath of this decomposition is allowed."""
    stages = expand_radices(radices, points)
    widest = max(int(math.log2(radix)) for radix in stages)
    return 8.0 * (len(stages) + 1) * (widest + 1)


RADICES = [("2", 4), ("2", 8), ("2", 16), ("2", 32), ("2", 64),
           ("4", 16), ("4", 64), ("8", 8), ("4,2", 8), ("4,4", 16)]


@pytest.mark.parametrize("radices,points", RADICES)
def test_every_classic_vector_agrees_with_the_golden(radices, points):
    """Every vector, through every model, against NumPy."""
    allowed = bound(radices, points)
    for label, frame in vectors(points):
        want = golden(frame, points)
        for name, got in compute_all(frame, points, radices).items():
            worst = deviation(got, want)
            assert worst <= allowed, (
                f"{label} through {name} ({radices}) off by {worst:.2f} "
                f"LSB, bound {allowed:.1f}")


@pytest.mark.parametrize("radices,points", RADICES)
def test_the_constant_is_the_zeroth_bin(radices, points):
    """A constant gives one bin, exactly, in integer arithmetic.

    `N` samples of `A` sum to `N * A`, and the stages divide by `N`, so the
    zeroth bin is `A` exactly and every other bin cancels exactly - no tolerance
    is involved.
    """
    height = amplitude(0.5)
    frame = constant(points, 0.5)
    # A butterfly of radix 2 or 4 cancels the other bins exactly, because its
    # rotations are the trivial ones and a sum of equal terms cancels in
    # integer arithmetic.  A direct 8 point DFT does not: its forty five degree
    # factors are truncated, and for an input whose bins should cancel the
    # truncation has nothing to cancel against - measured at two units.
    slack = 0 if max(expand_radices(radices, points)) <= 4 else 3
    for name, got in compute_all(frame, points, radices).items():
        assert got[0] == (height, 0), f"{name}: bin 0 is {got[0]}"
        for k in range(1, points):
            assert abs(got[k][0]) <= slack and abs(got[k][1]) <= slack, \
                f"{name}: bin {k} is {got[k]}, slack {slack}"


@pytest.mark.parametrize("radices,points", RADICES)
def test_the_alternating_sequence_is_the_bin_at_half_the_band(radices, points):
    """A constant times `(-1)**n` is one bin, exactly."""
    height = amplitude(0.5)
    frame = alternating(points, 0.5)
    slack = 0 if max(expand_radices(radices, points)) <= 4 else 3
    for name, got in compute_all(frame, points, radices).items():
        peak = got[points // 2]
        assert abs(peak[0] - height) <= slack and abs(peak[1]) <= slack, \
            f"{name}: bin {points // 2} is {peak}"
        for k in range(points):
            if k != points // 2:
                assert abs(got[k][0]) <= slack and abs(got[k][1]) <= slack, \
                    f"{name}: bin {k} is {got[k]}, slack {slack}"


@pytest.mark.parametrize("radices,points", RADICES)
def test_the_impulse_is_flat(radices, points):
    """An impulse is flat, and exactly so when the sum divides by the points.

    The height is chosen as a multiple of the number of points, so that the
    scaling of the stages - which divides by `points` in total - lands on an
    integer and the comparison needs no tolerance.
    """
    per_bin = 64
    height = per_bin * points
    frame = impulse(points, height / SCALE)
    expected = (per_bin, 0)
    for name, got in compute_all(frame, points, radices).items():
        for k in range(points):
            assert got[k] == expected, f"{name}: bin {k} is {got[k]}"


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8), ("2", 16)])
def test_the_exponential_is_a_single_bin(radices, points):
    """A complex exponential lands in its own bin and nowhere else."""
    bin_index = 3
    frame = exponential(points, bin_index)
    got = fft_mixed(frame, WIDTH, points, radices, dit=False)
    magnitudes = [math.hypot(re, im) for re, im in got]
    peak = magnitudes.index(max(magnitudes))
    assert peak == bin_index, f"peaked at {peak}, not {bin_index}"
    # everything else is small next to the peak
    others = max(m for k, m in enumerate(magnitudes) if k != bin_index)
    assert others < magnitudes[peak] * 0.02, f"leakage of {others}"


@pytest.mark.parametrize("radices,points", [("4", 16), ("8", 8), ("2", 16)])
def test_the_cosine_and_the_sine_differ_by_minus_j(radices, points):
    """A cosine has two bins, a sine two bins, and they are a quarter turn apart.

    It is the relation which ties the real and the imaginary datapath together:
    a datapath which computes one of them right and the other wrong passes any
    check which only looks at magnitudes.
    """
    bin_index = 3
    cos_frame = cosine(points, bin_index)
    sin_frame = sine(points, bin_index)
    cos_spec = fft_mixed(cos_frame, WIDTH, points, radices, dit=False)
    sin_spec = fft_mixed(sin_frame, WIDTH, points, radices, dit=False)

    # A cosine and a sine of the same frequency have the same magnitude in every
    # bin - they are the same signal a quarter turn apart - while the turn itself
    # changes sign between the bin and its conjugate, because the two describe
    # opposite rotations: `sin = -j cos` at the bin, `+j` at `points - bin`.
    for k in range(points):
        c_re, c_im = cos_spec[k]
        s_re, s_im = sin_spec[k]
        assert abs(math.hypot(c_re, c_im) - math.hypot(s_re, s_im)) <= 4, \
            f"bin {k}: magnitudes differ"

    for k, sign in ((bin_index, 1), (points - bin_index, -1)):
        c_re, c_im = cos_spec[k]
        s_re, s_im = sin_spec[k]
        # sign * (-j) * (c_re, c_im) = sign * (c_im, -c_re)
        want_re, want_im = sign * c_im, sign * -c_re
        assert abs(s_re - want_re) <= 4, f"bin {k}: {s_re} against {want_re}"
        assert abs(s_im - want_im) <= 4, f"bin {k}: {s_im} against {want_im}"


@pytest.mark.parametrize("radices,points", RADICES)
def test_two_tones_are_the_sum_of_their_spectra(radices, points):
    """The datapath is linear, which no single tone can show."""
    first = cosine(points, 1 % points, 0.2)
    second = cosine(points, 3 % points, 0.2)
    both = [(a[0] + b[0], a[1] + b[1]) for a, b in zip(first, second)]
    spec_both = fft_mixed(both, WIDTH, points, radices, dit=False)
    spec_first = fft_mixed(first, WIDTH, points, radices, dit=False)
    spec_second = fft_mixed(second, WIDTH, points, radices, dit=False)
    # Truncation is not linear: rounding two operands and then adding is not
    # the same as adding and then rounding, so the sum of two spectra and the
    # spectrum of the sum differ by the rounding of every stage.  Measured at
    # three to six units for the decompositions here.
    stages = expand_radices(radices, points)
    slack = 2.0 * len(stages) + 4.0
    for k in range(points):
        want_re = spec_first[k][0] + spec_second[k][0]
        want_im = spec_first[k][1] + spec_second[k][1]
        assert abs(spec_both[k][0] - want_re) <= slack, f"bin {k} real"
        assert abs(spec_both[k][1] - want_im) <= slack, f"bin {k} imaginary"


@pytest.mark.parametrize("radices,points", RADICES)
def test_full_scale_input_stays_inside_the_datapath(radices, points):
    """Samples of magnitude one are the worst case for the width of the sum.

    The sum of `N` samples is `N` times the range of one, and the stages divide
    by `N` in total; a datapath which did not scale would wrap here and nowhere
    else.
    """
    allowed = bound(radices, points)
    frame = full_scale(points)
    want = golden(frame, points)
    for name, got in compute_all(frame, points, radices).items():
        worst = deviation(got, want)
        assert worst <= allowed, f"{name} off by {worst:.2f} at full scale"


@pytest.mark.parametrize("radices,points", RADICES)
def test_every_vector_passes_through_every_topology_identically(radices, points):
    """The vectors are also the ones which separate the topologies."""
    for label, frame in vectors(points):
        results = compute_all(frame, points, radices)
        base = results["mixed"]
        for name in ("sdf", "sdc"):
            assert results[name] == base, f"{label}: {name} differs from mixed"
