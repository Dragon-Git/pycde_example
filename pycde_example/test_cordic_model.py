"""Unit tests of the pure python CORDIC reference model.

These tests do not need any RTL: they verify the algorithm itself (against a
floating point reference) and they are the reference the cocotb tests compare
the generated RTL against.
"""

import math
import random

import pytest

from .cordic_model import (
    ROTATION,
    VECTORING,
    angle_scale,
    angle_to_fixed,
    atan_table,
    cordic,
    cordic_gain,
    cordic_reference,
    fixed_to_angle,
    from_fixed,
    to_fixed,
    wrap,
)


def magnitude_tolerance(width: int, iterations: int, x: int, y: int) -> float:
    """The error of the fixed point datapath.

    The truncation of the arithmetic shifts contributes an error of about one
    LSB per iteration, the error of the datapath itself is proportional to the
    magnitude of the vector.
    """
    return 8 + iterations + 4 * (abs(x) + abs(y)) * 2.0 ** -(iterations - 1)


def angle_tolerance(width: int, iterations: int, magnitude: float = 0.0) -> float:
    """The angular resolution of the CORDIC plus the rounding of the table.

    The angle of the vectoring mode is only accurate as long as the vector is
    large enough: the truncation of the datapath shifts the angle by roughly
    ``iterations / magnitude`` radian.
    """
    resolution = math.atan(2.0 ** -(iterations - 1)) * angle_scale(width) / math.pi
    truncation = 0.0
    if magnitude > 0:
        truncation = iterations * 0.5 * angle_scale(width) / (math.pi * magnitude)
    return 2 * resolution + truncation + 4 * iterations


@pytest.mark.parametrize("width,iterations", [(16, 12), (24, 12), (32, 16)])
def test_atan_table(width, iterations):
    table = atan_table(width, iterations)
    assert len(table) == iterations
    # atan(1) is a quarter turn
    assert table[0] == angle_scale(width) // 4
    # the table is strictly decreasing and positive
    assert all(table[i] > table[i + 1] > 0 for i in range(iterations - 1))
    # the sum of the table is the rotation range of the CORDIC
    assert sum(table) < angle_scale(width)


def test_wrap():
    assert wrap(0, 8) == 0
    assert wrap(127, 8) == 127
    assert wrap(128, 8) == -128
    assert wrap(255, 8) == -1
    assert wrap(256, 8) == 0
    assert wrap(-1, 8) == -1
    assert wrap(-129, 8) == 127


def test_angle_conversion():
    width = 16
    assert angle_to_fixed(0.0, width) == 0
    assert angle_to_fixed(math.pi, width) == angle_scale(width)
    assert angle_to_fixed(-math.pi, width) == -angle_scale(width)
    for angle in (-3.0, -1.0, -0.25, 0.0, 0.25, 1.0, 3.0):
        assert math.isclose(fixed_to_angle(angle_to_fixed(angle, width), width),
                            angle, abs_tol=1e-4)


def test_gain():
    assert math.isclose(cordic_gain(1), math.sqrt(2), rel_tol=1e-9)
    assert math.isclose(cordic_gain(16), 1.646760258121, rel_tol=1e-9)


@pytest.mark.parametrize("width,iterations", [(16, 12), (24, 12), (32, 16)])
def test_rotation_matches_float(width, iterations):
    rng = random.Random(width * 31 + iterations)
    limit = 1 << (width - 4)
    angle_limit = int(0.9 * sum(atan_table(width, iterations)))
    for _ in range(200):
        x = rng.randint(-limit, limit)
        y = rng.randint(-limit, limit)
        z = rng.randint(-angle_limit, angle_limit)
        got = cordic(x, y, z, width, iterations, ROTATION)
        ref = cordic_reference(from_fixed(x, width), from_fixed(y, width),
                               fixed_to_angle(z, width), iterations, ROTATION)
        tol = magnitude_tolerance(width, iterations, x, y)
        assert abs(got[0] - to_fixed(ref[0], width)) <= tol
        assert abs(got[1] - to_fixed(ref[1], width)) <= tol
        # the angle is driven to zero
        assert abs(got[2]) <= angle_tolerance(width, iterations)


@pytest.mark.parametrize("width,iterations", [(16, 12), (24, 12), (32, 16)])
def test_vectoring_matches_float(width, iterations):
    rng = random.Random(width * 17 + iterations * 7)
    limit = 1 << (width - 4)
    angle_limit = int(0.9 * sum(atan_table(width, iterations)))
    for _ in range(200):
        x = rng.randint(-limit, limit)
        y = rng.randint(-limit, limit)
        if abs(math.atan2(y, x)) > 1.6:
            continue
        z = rng.randint(-angle_limit, angle_limit)
        got = cordic(x, y, z, width, iterations, VECTORING)
        ref = cordic_reference(from_fixed(x, width), from_fixed(y, width),
                               fixed_to_angle(z, width), iterations, VECTORING)
        tol = magnitude_tolerance(width, iterations, x, y)
        # x holds the (gain compensated) magnitude
        assert abs(got[0] - to_fixed(ref[0], width)) <= tol
        # y is driven to zero
        assert abs(got[1]) <= tol
        # z holds the angle of the vector
        magnitude = math.hypot(x, y)
        assert abs(got[2] - angle_to_fixed(ref[2], width)) <= \
            angle_tolerance(width, iterations, magnitude)


@pytest.mark.parametrize("width,iterations", [(16, 12), (24, 12)])
def test_zero_input(width, iterations):
    # a zero vector stays zero.  The rotation mode drives the angle to zero
    # (up to the resolution of the CORDIC), the angle of the vectoring mode is
    # undefined for a zero vector.
    (x, y, z) = cordic(0, 0, 0, width, iterations, ROTATION)
    assert x == 0
    assert y == 0
    assert abs(z) <= angle_tolerance(width, iterations)
    (x, y, _) = cordic(0, 0, 0, width, iterations, VECTORING)
    assert x == 0
    assert y == 0


def test_rotation_by_zero_only_gains():
    # rotating by zero does not change the direction of the vector, it only
    # scales it with the gain of the CORDIC
    width, iterations = 16, 12
    gain = cordic_gain(iterations)
    x, y = 1000, -500
    got = cordic(x, y, 0, width, iterations, ROTATION)
    assert math.isclose(from_fixed(got[0], width), gain * x / (1 << (width - 1)),
                        abs_tol=0.01)
    assert math.isclose(from_fixed(got[1], width), gain * y / (1 << (width - 1)),
                        abs_tol=0.01)


def test_rotation_and_vectoring_are_consistent():
    """Rotating a vector by the angle found by the vectoring mode moves it onto
    the x axis - the same result the vectoring mode produces."""
    width, iterations = 16, 12
    x, y = 1000, 500
    (magnitude, _, angle) = cordic(x, y, 0, width, iterations, VECTORING)
    (rx, ry, _) = cordic(x, y, -angle, width, iterations, ROTATION)
    tol = magnitude_tolerance(width, iterations, x, y)
    assert abs(rx - magnitude) <= tol
    assert abs(ry) <= tol


def test_model_is_deterministic():
    for _ in range(10):
        assert cordic(1234, -4321, 999, 16, 12, ROTATION) == \
            cordic(1234, -4321, 999, 16, 12, ROTATION)


def test_unknown_mode():
    with pytest.raises(ValueError):
        cordic(1, 1, 1, 16, 12, "nonsense")
