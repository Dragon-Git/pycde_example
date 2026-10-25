"""The golden reference of the transform, computed by NumPy.

Every expected value in the tests of this package comes from here.  Nothing is
worked out by hand: a hand derived expectation is a place where a mistake in the
reasoning looks exactly like a mistake in the model, and four of them went wrong
while these tests were being written - a real sine was put in the imaginary part,
an impulse was expected at its own height instead of a divided one, the cosine and
the sine were related the same way at every bin instead of oppositely at the
mirrored one, and linearity was expected to hold exactly in a datapath which
truncates.

The reference shares no code with the models, so it cannot inherit a mistake from
one.  It works in floating point, which is what makes it a reference: the models
work in fixed point and are compared against it with a bound.
"""

from __future__ import annotations

import math

import numpy as np


def golden(frame: list[tuple[int, int]], width: int,
           points: int) -> np.ndarray:
    """The transform of a fixed point frame, by NumPy.

    The integer ``re`` stands for ``re / 2**(width - 1)``, so the frame is brought
    to that scale, transformed, brought back to the integer scale, and divided by
    the number of points because the datapath scales by ``1 / points`` over all of
    its stages.
    """
    scale = 1 << (width - 1)
    values = np.array([complex(re, im) for re, im in frame], dtype=np.complex128)
    return np.fft.fft(values / scale) * scale / points


def deviation(got: list[tuple[int, int]], want: np.ndarray) -> float:
    """The largest deviation of a fixed point spectrum, in units of the last bit."""
    worst = 0.0
    for (re, im), value in zip(got, want):
        worst = max(worst, abs(re - value.real), abs(im - value.imag))
    return worst


def deviations(got: list[tuple[int, int]], want: np.ndarray) -> list[float]:
    """The deviation of every bin, in units of the last bit."""
    return [max(abs(re - value.real), abs(im - value.imag))
            for (re, im), value in zip(got, want)]


def truncation_bound(radices: list[int]) -> float:
    """The deviation a fixed point datapath of this shape is allowed.

    Every stage shifts its operands right, dropping up to a unit of the last bit
    per term, and every rotation truncates a product the same way, so a stage of
    radix ``R`` adds a couple of units per term and the stages add up.  The
    constant is generous on purpose: this bound separates a datapath which is
    right to within its own rounding from one which is structurally wrong, and
    those are off by thousands.

    It is not a claim about a single unit.  A claim about a single unit is made
    only where the golden says the answer is an exact integer, and then the
    allowed deviation is half a unit.
    """
    stages = len(radices)
    widest = max(int(math.log2(radix)) for radix in radices)
    return 8.0 * (stages + 1) * (widest + 1)
