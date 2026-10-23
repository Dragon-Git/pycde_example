"""Tests of the two twiddle structures which need no memory.

The two are different structures, so they are checked differently: the logic one
has to reproduce the table exactly, because it is the same truth table realised
as gates; the cascade is a chain of truncated constant rotations, so it is
checked against a bound which follows from the number of cells.
"""

from __future__ import annotations

import pytest

from .fft_model import fft, to_fixed, twiddle_table
from .fft_no_mem_model import (
    GUARD,
    LOGIC_LIMIT,
    cascade_cells,
    constant,
    saturate,
    twiddle_cascade,
    twiddle_logic,
    twiddle_no_mem,
)


def worst_deviation(points: int, width: int, compute) -> int:
    """The largest deviation of a structure from the table."""
    table = twiddle_table(points, width)
    worst = 0
    for k in range(points // 2):
        re, im = compute(k)
        worst = max(worst, abs(re - table[k][0]), abs(im - table[k][1]))
    return worst


@pytest.mark.parametrize("width,points", [(12, 16), (16, 16), (16, 64),
                                          (20, 256), (24, 1024), (16, 4096)])
def test_the_cascade_stays_within_a_unit(width, points):
    """A chain of truncated rotations is off by at most a unit.

    The chain truncates once per cell which is set; with the extra bits of
    `GUARD` and the saturation of every cell, the error does not accumulate
    past a single unit whatever the width or the number of points is.  Without
    either of the two, a product whose magnitude is exactly one wraps to the
    other end of the range and the factor comes out with the wrong sign.
    """
    assert worst_deviation(points, width,
                           lambda k: twiddle_cascade(k, width, points)) <= 1


@pytest.mark.parametrize("width,points", [(12, 16), (16, 16), (16, 64)])
def test_the_logic_is_the_table(width, points):
    """The gates realise the entries of the table, bit for bit."""
    assert worst_deviation(points, width,
                           lambda k: twiddle_logic(k, width, points)) == 0


def test_the_logic_is_only_for_a_small_transform():
    """The gates grow with the number of points, the cells with its logarithm."""
    with pytest.raises(ValueError):
        twiddle_logic(0, 16, LOGIC_LIMIT * 2)


def test_the_cascades_cells_grow_with_the_logarithm():
    """One cell per bit of the index which is not a trivial factor."""
    assert cascade_cells(16) == 2
    assert cascade_cells(64) == 4
    assert cascade_cells(256) == 6
    assert cascade_cells(1024) == 8


def test_a_trivial_factor_needs_no_cell():
    """`W**0`, `-1` and `-j` are wiring, so they are no rotators."""
    for points in (16, 64, 256):
        # the factors of the powers of two which are a quarter or a half of the
        # transform are the trivial ones
        assert cascade_cells(points) == points.bit_length() - 3


@pytest.mark.parametrize("points", [16, 64, 256])
def test_every_index_is_a_unit_vector(points):
    """The factor of any index has the magnitude of a unit vector."""
    width = 16
    scale = 1 << (width - 1)
    for k in range(points):
        re, im = twiddle_cascade(k, width, points)
        magnitude = (re * re + im * im) ** 0.5 / scale
        assert 0.98 < magnitude <= 1.001, f"index {k} has magnitude {magnitude}"


def test_the_inverse_conjugates_the_factor():
    """The inverse transform conjugates every factor."""
    width, points = 16, 64
    for k in range(points):
        forward = twiddle_cascade(k, width, points)
        backward = twiddle_cascade(k, width, points, inverse=True)
        assert backward[0] == forward[0]
        assert backward[1] == -forward[1]


def test_the_saturation_clamps_instead_of_wrapping():
    """A value past the range is clamped, which is what keeps the sign right."""
    width = 16
    maximum = (1 << (width - 1)) - 1
    assert saturate(maximum + 100, width) == maximum
    assert saturate(-maximum - 100, width) == -maximum
    assert saturate(1234, width) == 1234


def test_the_zero_index_is_the_table_entry():
    """`W**0` is one unit short of one, exactly as in the table."""
    width = 16
    for points in (16, 64):
        assert twiddle_cascade(0, width, points) == constant(0, width, points)
        assert twiddle_logic(0, width, points) == constant(0, width, points)


@pytest.mark.parametrize("mode", ["no_mem_cascade", "no_mem_logic"])
def test_the_transform_with_each_structure(mode):
    """A transform built on either structure still computes the transform."""
    width, points = 16, 16
    from .fft_golden import golden
    frame = [(to_fixed(0.3 * ((-1) ** n) / (n + 1), width), 0)
             for n in range(points)]
    got = fft(frame, width, points, dit=True, twiddle_mode=mode)
    # the golden already carries the scaling of the stages
    expected = golden(frame, width, points)
    worst = max(max(abs(got[i][0] - expected[i].real),
                    abs(got[i][1] - expected[i].imag))
                for i in range(points))
    # the cascade truncates its chain, the logic one is the table
    bound = 40 if mode == "no_mem_cascade" else 8
    assert worst <= bound, f"{mode} off by {worst}"


def test_an_unknown_structure_is_rejected():
    """Two structures are supported, not any name."""
    with pytest.raises(ValueError):
        twiddle_no_mem(0, 16, 16, "no_mem")


def test_the_guard_is_what_makes_the_cascade_exact_enough():
    """The extra bits are a decision, not an accident."""
    assert GUARD >= 2
