"""Unit tests of the bit exact model of the delay feedback architecture.

The model is the reference of the RTL in ``fft_sdf.py``: it has to produce
the same spectrum as the reference model of the transform.  These tests do
not need any RTL.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_model import fft, to_fixed
from .fft_sdf_model import bit_reverse, sdf, sdf_stream


def random_samples(points: int, width: int, seed: int = 0,
                   amplitude: float = 0.6) -> list[tuple[int, int]]:
    """Deterministic random samples with a magnitude below ``amplitude``."""
    rng = random.Random(seed)
    samples = []
    for _ in range(points):
        radius = rng.uniform(0.0, amplitude)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        samples.append((to_fixed(radius * math.cos(angle), width),
                        to_fixed(radius * math.sin(angle), width)))
    return samples


@pytest.mark.parametrize("width,points", [(16, 4), (16, 8), (16, 16), (24, 32)])
@pytest.mark.parametrize("dit", [True, False])
def test_sdf_matches_the_transform(width, points, dit):
    """The delay feedback architecture computes the same spectrum."""
    samples = random_samples(points, width, seed=points)
    assert sdf(samples, width, points, dit=dit) == fft(samples, width, points,
                                                        dit=dit, scale=True)


@pytest.mark.parametrize("pipeline", [0, 1, 2])
def test_sdf_with_pipeline_registers(pipeline):
    """The registers between the stages do not change the result."""
    width, points = 16, 16
    samples = random_samples(points, width, seed=13)
    assert sdf(samples, width, points, dit=False, pipeline=pipeline) == fft(
        samples, width, points, dit=False, scale=True)


def test_sdf_impulse_response():
    """An impulse in the input is flat in the output."""
    width, points = 16, 16
    samples = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    # the transform scales by 1/points
    expected = to_fixed(0.5 / points, width)
    for dit in (True, False):
        got = sdf(samples, width, points, dit=dit)
        for k in range(points):
            assert abs(got[k][0] - expected) <= 4
            assert abs(got[k][1]) <= 4


def test_sdf_latency():
    """The result of the frame appears after `points - 1` cycles."""
    width, points = 16, 8
    samples = random_samples(points, width, seed=17)
    stream = sdf_stream(samples, width, points, cycles=3 * points)
    # the result of the frame is the spectrum, bit reversed
    expected = sdf(samples, width, points, dit=False)
    levels = points.bit_length() - 1
    for k in range(points):
        got = stream[points - 1 + k]
        ref = expected[bit_reverse(k, levels)]
        assert got == ref


def test_sdf_is_deterministic():
    width, points = 16, 8
    samples = random_samples(points, width, seed=19)
    assert sdf(samples, width, points) == sdf(samples, width, points)
