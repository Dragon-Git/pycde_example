"""Unit tests of the bit exact model of the delay commutator architecture.

The model computes the same spectrum as the reference model of the transform.
The two differ by a couple of units of the last bit: the last stage of the
commutator architecture uses a trivial rotator (an exact multiplication by
-j), while the reference model multiplies the difference of every stage with
the twiddle factor of the table, whose first entry is clamped one unit below
one.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_model import dft, fft, to_fixed
from .fft_sdc_model import bit_reverse, output_position, sdc, sdc_stream


def random_samples(points: int, width: int, seed: int = 0,
                   amplitude: float = 0.4) -> list[tuple[int, int]]:
    """Deterministic random samples with a magnitude below ``amplitude``."""
    rng = random.Random(seed)
    samples = []
    for _ in range(points):
        radius = rng.uniform(0.0, amplitude)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        samples.append((to_fixed(radius * math.cos(angle), width),
                        to_fixed(radius * math.sin(angle), width)))
    return samples


def max_deviation(got: list[tuple[int, int]],
                  expected: list[tuple[int, int]]) -> int:
    """The largest difference of the two results, in units of the last bit."""
    return max(max(abs(a - c), abs(b - d))
               for (a, b), (c, d) in zip(got, expected))


@pytest.mark.parametrize("width,points", [(16, 4), (16, 8), (16, 16),
                                          (16, 32), (24, 32)])
def test_sdc_matches_the_transform(width, points):
    """The commutator architecture computes the same spectrum."""
    for seed in range(3):
        samples = random_samples(points, width, seed=points + seed)
        got = sdc(samples, width, points)
        expected = fft(samples, width, points, dit=False, scale=True)
        # the last stage rotates with an exact -j instead of the clamped
        # entry of the twiddle table
        assert max_deviation(got, expected) <= 2


def test_sdc_impulse_response():
    """An impulse in the input is flat in the output."""
    width, points = 16, 16
    samples = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    got = sdc(samples, width, points)
    # the transform scales by 1/points
    expected = to_fixed(0.5 / points, width)
    for k in range(points):
        assert abs(got[k][0] - expected) <= 2
        assert abs(got[k][1]) <= 2


def test_sdc_tone_response():
    """A tone in the input is a peak in the output."""
    width, points = 16, 16
    bin_index = 3
    samples = []
    for n in range(points):
        angle = 2.0 * math.pi * bin_index * n / points
        samples.append((to_fixed(0.5 * math.cos(angle), width),
                        to_fixed(0.5 * math.sin(angle), width)))
    got = sdc(samples, width, points)
    for k in range(points):
        magnitude = math.hypot(got[k][0], got[k][1])
        if k == bin_index:
            assert abs(magnitude - to_fixed(0.5, width)) < 0.05 * (1 << width)
        else:
            assert magnitude < 0.02 * (1 << width)


def test_sdc_matches_the_float_transform():
    """The fixed point spectrum matches the floating point transform."""
    width, points = 16, 16
    samples = random_samples(points, width, seed=5)
    got = sdc(samples, width, points)
    reference = dft(samples)
    for k in range(points):
        expected = reference[k] / points
        assert abs(complex(got[k][0], got[k][1]) - expected) < 4.0


def test_sdc_latency():
    """The result of the frame appears after `points` cycles."""
    width, points = 16, 8
    samples = random_samples(points, width, seed=17)
    stream = sdc_stream(samples, width, points, cycles=3 * points)
    # the first half of the window carries the even bins
    levels = points.bit_length() - 1
    half = points // 2
    spectrum = sdc(samples, width, points)
    for i in range(half):
        even_bin = bit_reverse((2 * ((i + 1) % half)) % points, levels)
        assert stream[points + i] == spectrum[even_bin]


def test_output_position_is_a_permutation():
    """Every bin has a position of its own in the output stream."""
    for points in (4, 8, 16, 32):
        positions = [output_position(k, points) for k in range(points)]
        assert sorted(positions) == list(range(points))


def test_sdc_is_deterministic():
    width, points = 16, 8
    samples = random_samples(points, width, seed=19)
    assert sdc(samples, width, points) == sdc(samples, width, points)
