"""Unit tests of the pure python FFT reference model.

These tests do not need any RTL: they verify the algorithm itself (against a
floating point reference) and they are the reference the cocotb tests compare
the generated RTL against.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_model import (
    bit_reverse,
    complex_multiply,
    dft,
    fft,
    fft_inverse,
    from_fixed,
    to_fixed,
    truncate,
    twiddle_cordic,
    twiddle_table,
    wrap,
)


def random_samples(points: int, width: int, seed: int = 0,
                   amplitude: float = 0.7) -> list[tuple[int, int]]:
    """Deterministic random samples with a magnitude below ``amplitude``.

    The magnitude of a sample has to stay below one: the complex product of
    two samples would overflow the datapath otherwise.
    """
    rng = random.Random(seed)
    samples = []
    for _ in range(points):
        radius = rng.uniform(0.0, amplitude)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        samples.append((to_fixed(radius * math.cos(angle), width),
                        to_fixed(radius * math.sin(angle), width)))
    return samples


def max_error(got: list[tuple[int, int]], ref: list[complex], width: int,
              points: int) -> float:
    """The maximum error of the fixed point result against the float reference.

    The fixed point result is the discrete Fourier transform scaled by 1/N
    (every stage is scaled by 1/2).
    """
    error = 0.0
    for k in range(points):
        expected = ref[k] / points
        actual = complex(got[k][0], got[k][1])
        error = max(error, abs(actual - expected))
    return error


def test_wrap():
    assert wrap(0, 8) == 0
    assert wrap(127, 8) == 127
    assert wrap(128, 8) == -128
    assert wrap(255, 8) == -1
    assert wrap(256, 8) == 0
    assert wrap(-1, 8) == -1


def test_truncate():
    # the fractional bits are dropped, the sign is kept
    assert truncate(1 << 15, 16) == 1
    assert truncate(-(1 << 15), 16) == -1
    assert truncate(0, 16) == 0


def test_bit_reverse():
    assert bit_reverse(0, 4) == 0
    assert bit_reverse(1, 4) == 8
    assert bit_reverse(2, 4) == 4
    assert bit_reverse(3, 4) == 12
    assert bit_reverse(15, 4) == 15
    for value in range(16):
        assert bit_reverse(bit_reverse(value, 4), 4) == value


def test_twiddle_table():
    width, points = 16, 8
    table = twiddle_table(points, width)
    assert len(table) == points // 2
    # W^0 is one (the fixed point format cannot represent +1.0 exactly)
    assert abs(table[0][0] - (1 << (width - 1))) <= 1
    assert table[0][1] == 0
    # W^(N/4) is -j (the most negative value is not representable)
    assert table[points // 4] == (0, -((1 << (width - 1)) - 1))
    # the twiddles lie on the unit circle
    for (re, im) in table:
        assert abs(math.hypot(from_fixed(re, width), from_fixed(im, width)) - 1.0) < 1e-3


def test_complex_multiply():
    width = 16
    one = (1 << (width - 1)) - 1
    # (1 + 0j) * (0 + 1j) = j
    (re, im) = complex_multiply(one, 0, 0, one, width)
    assert abs(re) <= 1 and abs(im - one) <= 2
    # (1 + 0j) * (1 + 0j) = 1
    (re, im) = complex_multiply(one, 0, one, 0, width)
    assert abs(re - one) <= 2 and abs(im) <= 1
    # (0 + 1j) * (0 + 1j) = -1
    (re, im) = complex_multiply(0, one, 0, one, width)
    assert abs(re + one) <= 2 and abs(im) <= 1


@pytest.mark.parametrize("width,points", [(16, 8), (16, 16), (24, 32)])
def test_fft_matches_dft(width, points):
    """The fixed point FFT matches the discrete Fourier transform."""
    for dit in (True, False):
        samples = random_samples(points, width, seed=points)
        got = fft(samples, width, points, dit=dit, scale=True)
        ref = dft(samples)
        # the truncation of the fixed point multiplier dominates the error
        assert max_error(got, ref, width, points) < 4 * points


def test_impulse_response():
    """An impulse in the input is flat in the output."""
    width, points = 16, 16
    samples = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    for dit in (True, False):
        got = fft(samples, width, points, dit=dit, scale=True)
        for k in range(points):
            assert abs(from_fixed(got[k][0], width) - 0.5 / points) < 1e-4
            assert abs(from_fixed(got[k][1], width)) < 1e-4


def test_tone_response():
    """A tone in the input is a peak in the output."""
    width, points = 16, 16
    bin = 3
    samples = []
    for n in range(points):
        angle = 2.0 * math.pi * bin * n / points
        samples.append((to_fixed(0.5 * math.cos(angle), width),
                        to_fixed(0.5 * math.sin(angle), width)))
    for dit in (True, False):
        got = fft(samples, width, points, dit=dit, scale=True)
        for k in range(points):
            magnitude = math.hypot(from_fixed(got[k][0], width),
                                   from_fixed(got[k][1], width))
            if k == bin:
                assert abs(magnitude - 0.5) < 1e-2
            else:
                assert magnitude < 1e-2


def test_dit_and_dif_agree():
    """Both orderings compute the same spectrum."""
    width, points = 16, 16
    samples = random_samples(points, width, seed=7)
    dit = fft(samples, width, points, dit=True, scale=True)
    dif = fft(samples, width, points, dit=False, scale=True)
    for k in range(points):
        # the two orderings truncate in a different order
        assert abs(dit[k][0] - dif[k][0]) <= 4
        assert abs(dit[k][1] - dif[k][1]) <= 4


def test_parseval():
    """The energy of the output matches the energy of the input."""
    width, points = 16, 16
    samples = random_samples(points, width, seed=11)
    got = fft(samples, width, points, dit=True, scale=True)
    in_energy = sum(re * re + im * im for (re, im) in samples)
    out_energy = sum(re * re + im * im for (re, im) in got)
    # the output is scaled by 1/N
    assert abs(out_energy - in_energy / points) < 0.02 * in_energy / points


def test_inverse_transform():
    """The inverse transform undoes the transform (up to the scaling)."""
    width, points = 16, 16
    samples = random_samples(points, width, seed=5)
    spectrum = fft(samples, width, points, dit=True, scale=True)
    back = fft_inverse(spectrum, width, points, dit=True, scale=True)
    for (re, im), (orig_re, orig_im) in zip(back, samples):
        # the transform scales by 1/points, the inverse one as well
        assert abs(re - orig_re / points) <= 8 * points
        assert abs(im - orig_im / points) <= 8 * points


def test_twiddle_cordic():
    """The CORDIC generates the same twiddle factors as the table."""
    width, points = 16, 16
    iterations = max(4, width - 2)
    table = twiddle_table(points, width)
    for index in range(points // 2):
        (re, im) = twiddle_cordic(index, width, points, iterations)
        # the CORDIC is not exact, a few units of the last bit are allowed
        assert abs(re - table[index][0]) <= 16
        assert abs(im - table[index][1]) <= 16
        # the factor lies on the unit circle
        magnitude = math.hypot(from_fixed(re, width), from_fixed(im, width))
        assert abs(magnitude - 1.0) < 1e-3


def test_model_is_deterministic():
    width, points = 16, 8
    samples = random_samples(points, width, seed=3)
    assert fft(samples, width, points) == fft(samples, width, points)


def test_invalid_arguments():
    with pytest.raises(ValueError):
        fft([(0, 0)] * 4, 16, 8)
    with pytest.raises(ValueError):
        fft([(0, 0)] * 6, 16, 6)
