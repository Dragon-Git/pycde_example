"""Unit tests of the bit exact model of the delay commutator architecture.

The decisive test is the one with *different consecutive frames*: the delay
lines of the chain hold the data of the previous frame while the current one is
processed, so feeding the same frame over and over again hides any mistake in
the way the frames follow each other.  Every architecture of the FFT is tested
that way.

The model is bit exact with the reference model of the transform: the trivial
twiddle factors (``W**0`` and ``-j``) are applied the way the hardware applies
them, as a wire and as a swap with a negation, so no unit of the last bit is
lost.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_model import dft, fft, to_fixed
from .fft_sdc_model import (
    bit_reverse,
    output_order,
    output_position,
    sdc,
    sdc_stream,
)


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


def frame_of(samples, points, width, index):
    """The samples of one frame of a stream."""
    return samples[index * points:(index + 1) * points]


@pytest.mark.parametrize("width,points", [(16, 4), (16, 8), (16, 16),
                                          (16, 32), (24, 32)])
def test_sdc_consecutive_frames(width, points):
    """Different consecutive frames are transformed independently.

    This is the test which matters for a streaming pipeline: the previous
    frame is still inside the delay lines when the next one arrives.
    """
    samples = random_samples(points * 4, width, seed=points)
    stream = sdc_stream(samples, width, points, cycles=len(samples) + 2 * points)
    order = output_order(points)
    for frame_index in (1, 2):
        base = frame_index * points + points - 1
        window = stream[base:base + points]
        expected = fft(frame_of(samples, points, width, frame_index),
                       width, points, dit=False, scale=True)
        got = [(0, 0)] * points
        for position, bin_index in enumerate(order):
            got[bin_index] = window[position]
        assert got == expected


@pytest.mark.parametrize("width,points", [(16, 4), (16, 8), (16, 16),
                                          (16, 32), (24, 32)])
def test_sdc_matches_the_transform(width, points):
    """The commutator architecture computes the same spectrum, bit for bit."""
    for seed in range(3):
        samples = random_samples(points, width, seed=points + seed)
        assert sdc(samples, width, points) == fft(samples, width, points,
                                                   dit=False, scale=True)


@pytest.mark.parametrize("width,points", [(24, 8), (24, 16)])
def test_sdc_without_scaling(width, points):
    """The stages can be left unscaled (the datapath has to be wide enough)."""
    samples = random_samples(points, width, seed=points, amplitude=0.02)
    assert sdc(samples, width, points, scale=False) == fft(
        samples, width, points, dit=False, scale=False)


def test_sdc_impulse_response():
    """An impulse in the input is flat in the output."""
    width, points = 16, 16
    samples = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    got = sdc(samples, width, points)
    # the transform scales by 1/points, and the impulse response of a correct
    # datapath is exactly flat (the trivial factors are not multiplied)
    expected = to_fixed(0.5 / points, width)
    for k in range(points):
        assert got[k] == (expected, 0)


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


def test_output_window_is_rotated():
    """The window of the output multiplexer is rotated by the latency.

    Selecting the sum with ``counter < points / 2`` instead of the rotated
    window turns the bins 0 and points / 2 into garbage - the mistake which
    this test guards against.
    """
    width, points = 16, 16
    samples = random_samples(points, width, seed=11)
    stream = sdc_stream(samples * 2, width, points, cycles=2 * points)
    # the window starts at points - 1, not at 0
    for start, ok in ((points - 1, True), (0, False)):
        window = stream[start:start + points]
        expected = fft(samples, width, points, dit=False, scale=True)
        got = [(0, 0)] * points
        for position, bin_index in enumerate(output_order(points)):
            got[bin_index] = window[position]
        matched = got == expected
        assert matched is ok


def test_output_position_is_a_permutation():
    """Every bin has a position of its own in the output window."""
    for points in (4, 8, 16, 32):
        positions = [output_position(k, points) for k in range(points)]
        assert sorted(positions) == list(range(points))


def test_output_order_interleaves_the_bins():
    """The first half of the window carries the even bins of the algorithm.

    The parity is the one of the index before the bit reversal: reversing the
    bits of an even number does not necessarily give an even number, so the
    order is compared against the definition rather than against the parity of
    the bins.
    """
    for points in (8, 16, 32):
        order = output_order(points)
        half = points // 2
        levels = points.bit_length() - 1
        assert order[:half] == [bit_reverse(2 * c, levels)
                                for c in range(half)]
        assert order[half:] == [bit_reverse(2 * c + 1, levels)
                                for c in range(half)]


def test_sdc_is_deterministic():
    width, points = 16, 8
    samples = random_samples(points, width, seed=19)
    assert sdc(samples, width, points) == sdc(samples, width, points)
