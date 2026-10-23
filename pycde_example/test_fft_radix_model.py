"""Tests of the mixed radix model.

The model has to reproduce the floating point transform, and it has to agree
with the radix 2 model bit for bit when every radix is 2 - the second check is
the strong one, the first says that the mixed radix decomposition is right.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_model import dft, fft, to_fixed
from .fft_radix_model import expand_radices, fft_mixed, log2, mixed_reverse, parse_radices, radix_size


def tolerance(width: int, stages: list[int]) -> int:
    """The units of the last bit a mixed radix datapath may be off.

    Every multiplication of the datapath loses at most half a unit, and a
    stage of radix ``R`` multiplies each of its ``R`` outputs ``R`` times, so
    the bound grows with the radices and with the number of stages.  It stays
    far below the errors of a wrong decomposition, which are of the order of
    the datapath itself.
    """
    widest = max(log2(radix) for radix in stages)
    return 4 * len(stages) * widest + 4


def random_frame(points: int, width: int, seed: int = 0,
                 amplitude: float = 0.3) -> list[tuple[int, int]]:
    """A deterministic random frame."""
    rng = random.Random(seed)
    return [(to_fixed(rng.uniform(-amplitude, amplitude), width),
             to_fixed(rng.uniform(-amplitude, amplitude), width))
            for _ in range(points)]


@pytest.mark.parametrize("radices,points", [
    ("2", 2), ("4", 4), ("8", 8), ("16", 16),
    ("2,2,2", 8), ("4,4", 16), ("8,8", 64), ("4,4,4", 64),
    ("4,2", 8), ("2,4", 8), ("8,2", 16), ("4,2,2", 16),
    ("8,4", 32), ("4,8", 32), ("16,2", 32), ("2,2,2,2,2", 32),
])
@pytest.mark.parametrize("dit", [False, True])
def test_mixed_radix_matches_the_transform(radices, points, dit):
    """The mixed radix decomposition computes the transform."""
    width = 24
    stages = parse_radices(radices)
    frame = random_frame(points, width, seed=points + len(radices))
    got = fft_mixed(frame, width, points, radices, dit=dit, scale=True)
    expected = dft(frame)
    # the stages scale the datapath by the number of points in total
    worst = max(max(abs(got[i][0] - expected[i].real / points),
                    abs(got[i][1] - expected[i].imag / points))
                for i in range(points))
    assert worst <= tolerance(width, stages), f"{radices} off by {worst}"


@pytest.mark.parametrize("width,points", [(12, 4), (16, 8), (16, 16), (24, 32)])
@pytest.mark.parametrize("dit", [False, True])
def test_radix_two_is_bit_exact(width, points, dit):
    """With every radix 2 the model is the radix 2 model, bit for bit."""
    radices = ",".join(["2"] * log2(points))
    frame = random_frame(points, width, seed=width + points)
    assert (fft_mixed(frame, width, points, radices, dit=dit, scale=True)
            == fft(frame, width, points, dit=dit, scale=True))


def test_radix_two_without_scaling_is_bit_exact():
    """The unscaled datapath matches the unscaled radix 2 model as well."""
    width, points = 24, 16
    radices = ",".join(["2"] * log2(points))
    frame = random_frame(points, width, seed=7, amplitude=0.01)
    assert (fft_mixed(frame, width, points, radices, dit=False, scale=False)
            == fft(frame, width, points, dit=False, scale=False))


def test_a_mixed_radix_is_not_the_same_radix_order():
    """Two different stage orders both compute the transform."""
    width, points = 24, 32
    frame = random_frame(points, width, seed=11)
    expected = dft(frame)
    for radices, stages in (("8,4", [8, 4]), ("4,8", [4, 8])):
        got = fft_mixed(frame, width, points, radices, dit=False)
        worst = max(max(abs(got[i][0] - expected[i].real / points),
                        abs(got[i][1] - expected[i].imag / points))
                    for i in range(points))
        assert worst <= tolerance(width, stages)


def test_both_quarter_turns_are_exact():
    """`-j` and `+j` are a swap and a negation, not a table entry.

    A radix 2 stage only ever rotates by `-j`, so the `+j` case was missing from
    the twiddle arithmetic until a butterfly of radix 4 needed it.  Falling
    through to the table costs a unit of the last bit, because the entry is
    32767/32768 of the factor it stands for.
    """
    from .fft_model import apply_twiddle
    width = 16
    for points in (4, 8, 16, 64):
        mine = apply_twiddle(points // 4, 1000, 2000, width, points)
        assert mine == (2000, -1000), f"-j at {points} points is {mine}"
        plus = apply_twiddle(3 * points // 4, 1000, 2000, width, points)
        assert plus == (-2000, 1000), f"+j at {points} points is {plus}"
        minus = apply_twiddle(points // 2, 1000, 2000, width, points)
        assert minus == (-1000, -2000), f"-1 at {points} points is {minus}"


def test_parse_radices_rejects_a_radix_which_is_not_a_power_of_two():
    """The butterflies are powers of two."""
    for bad in ("3", "4,3", "0", "1"):
        with pytest.raises(ValueError):
            parse_radices(bad)


def test_a_single_radix_is_repeated_to_fill_the_transform():
    """`"2"` on 16 points means four radix 2 stages, not two points."""
    assert expand_radices("2", 16) == [2, 2, 2, 2]
    assert expand_radices("4", 64) == [4, 4, 4]
    assert expand_radices("8", 8) == [8]
    assert expand_radices("2", 2) == [2]


def test_a_list_of_radices_is_taken_literally():
    """A mixed list has to describe exactly the number of points."""
    assert expand_radices("4,2", 8) == [4, 2]
    with pytest.raises(ValueError):
        expand_radices("4,2", 16)


def test_a_single_radix_has_to_divide_the_points():
    """A radix which does not fill the transform is a mistake."""
    with pytest.raises(ValueError):
        expand_radices("8", 12)


def test_parse_radices_accepts_a_list():
    """The radices may be handed over as a list of integers."""
    assert parse_radices([4, 2]) == [4, 2]
    assert radix_size("4,2") == 8


def test_the_number_of_points_has_to_match_the_radices():
    """A mismatch is a mistake of the caller, not something to guess."""
    with pytest.raises(ValueError):
        fft_mixed([(0, 0)] * 8, 16, 8, "4,4", dit=False)


def test_mixed_reverse_is_a_permutation():
    """The digit reversal maps the indices onto themselves, one to one.

    It is its own inverse only when every radix is the same - with unequal
    radices the digits are weighted differently on the way back, so reversing
    twice does not have to return the original index.
    """
    for radices in ([4, 2], [2, 4], [8, 2], [4, 2, 2], [2, 2, 2, 2]):
        points = 1
        for radix in radices:
            points *= radix
        images = sorted(mixed_reverse(index, radices) for index in range(points))
        assert images == list(range(points))


def test_mixed_reverse_is_its_own_inverse_for_a_uniform_radix():
    """With equal radices reversing twice gives the original index."""
    for radices in ([2, 2, 2], [2, 2, 2, 2], [4, 4], [8, 8]):
        points = 1
        for radix in radices:
            points *= radix
        for index in range(points):
            once = mixed_reverse(index, radices)
            assert mixed_reverse(once, radices) == index


def test_mixed_reverse_is_the_bit_reversal_for_radix_two():
    """A single radix 2 degenerates into the familiar bit reversal."""
    from .fft_model import bit_reverse
    for stages in (3, 4, 5):
        radices = [2] * stages
        for index in range(1 << stages):
            assert mixed_reverse(index, radices) == bit_reverse(index, stages)


def test_the_result_is_in_the_natural_order():
    """A tone has a single peak, at the bin it belongs to, in both orders."""
    width, points = 24, 16
    for dit in (False, True):
        for radices in ("4,4", "8,2", "2,2,2,2"):
            bin_index = 3
            frame = [(to_fixed(0.4 * math.cos(
                2.0 * math.pi * bin_index * n / points), width),
                to_fixed(0.4 * math.sin(
                    2.0 * math.pi * bin_index * n / points), width))
                for n in range(points)]
            got = fft_mixed(frame, width, points, radices, dit=dit)
            magnitudes = [abs(complex(re, im)) for (re, im) in got]
            peak = magnitudes.index(max(magnitudes))
            assert peak == bin_index, f"{radices} dit={dit} peaked at {peak}"
