"""The twiddle factors of a transform, without a memory of its own.

A table holds ``points / 2`` factors, which for a small FFT is its largest part.
There are two ways to get the same factors without it, and they are different
structures rather than two names for one thing.

The cascade of rotator cells
----------------------------
Writing the index in binary and splitting the factor along its bits::

    W**k = product over the bits i of k which are set of W**(2**i)

so a chain of ``log2(points)`` cells does the job: cell ``i`` rotates by the
constant angle ``2*pi*2**i/points`` when bit ``i`` of the index is set and passes
its input through when it is not.  The cell is a constant rotation, so it is a
shift and add chain, not a multiplier - this is the multiplier free cascade of
Huang and Chen (IEEE TVLSI, 2014).  It has no angle iteration and no residual,
which is what separates it from a CORDIC: the structure is feed forward, its
latency is the number of cells which are set, and adding a cell extends the
supported number of points.  It fits a pipelined and a memory based datapath
alike.

Most of the constants are trivial (``W**(N/2) = -1``, ``W**(N/4) = -j``), so a
chain of a small transform is two or three real rotators.

The chain multiplies constants, so it truncates once per cell which is set and
differs from the table by a few units of the last bit.  Two details make the
difference between a chain which is nearly exact and one which is not:

* it starts at the factor of the highest bit which is set rather than at
  ``+1.0`` - the fixed point format cannot hold ``+1.0``, so starting from it
  would cost a unit before the chain began;
* the cells work in ``GUARD`` more bits and saturate, because a product whose
  magnitude is exactly ``1.0`` is one unit past what the format holds; without
  the extra bits and the saturation that product wraps around and the factor
  comes out with the wrong sign.

The logic and the bus
---------------------
The other way keeps the values but not the memory: every output bit is a boolean
function of the index bits, and the function is synthesized as gates.  This is
the ROMless generator of the low power literature - the values are split into
terms which simple logic modules produce in parallel and a bus adds up.  The
values are the entries of the table, so there is nothing to approximate, but the
number of gates grows with the number of points: it is the structure for a small
transform with a fixed size, the cascade is the one which grows with the
logarithm and scales to any number of points.

Which one to use
----------------
The cascade is small, logarithmic and a few units off; the logic one is flat,
exact and only affordable for a small transform.  Both are checked against the
table here: the cascade against a bound which is written down, the logic one
exactly.
"""

from __future__ import annotations

import math

from .fft_model import wrap
from .fft_radix_model import log2

NO_MEM_MODES = ("no_mem_cascade", "no_mem_logic")

# The number of extra bits a cascade cell works in, and the reason it needs them
# is in the module documentation.
GUARD = 4

# The number of points above which the logic of a bus summation would be larger
# than the memory it replaces.  The bound is the one the structure has: the
# gates grow with the number of points, the rotators of a cascade with its
# logarithm.
LOGIC_LIMIT = 64


def constant(index: int, width: int, points: int) -> tuple[int, int]:
    """The factor ``W**index`` as the table holds it.

    It is computed at elaboration time and baked into the wiring, which is what
    makes the structure free of a memory.  The components are clamped to the
    representable range, so ``W**0`` is one unit short of ``+1.0`` exactly as in
    the table.
    """
    scale = 1 << (width - 1)
    maximum = (1 << (width - 1)) - 1
    minimum = -maximum
    angle = -2.0 * math.pi * (index % points) / points
    re = min(max(round(scale * math.cos(angle)), minimum), maximum)
    im = min(max(round(scale * math.sin(angle)), minimum), maximum)
    return re, im


def saturate(value: int, width: int) -> int:
    """Clamp to the range the fixed point format holds."""
    maximum = (1 << (width - 1)) - 1
    return min(max(value, -maximum), maximum)


def multiply(a_re: int, a_im: int, b_re: int, b_im: int,
             width: int) -> tuple[int, int]:
    """The complex product, saturated the way a cell saturates."""
    product_re = a_re * b_re - a_im * b_im
    product_im = a_re * b_im + a_im * b_re
    shift = width - 1
    return (saturate(product_re >> shift, width),
            saturate(product_im >> shift, width))


def twiddle_cascade(index: int, width: int, points: int,
                    inverse: bool = False) -> tuple[int, int]:
    """The factor of ``index`` from the cascade of rotator cells.

    The chain starts at the factor of the highest bit of the index which is set
    and multiplies in the factors of the lower ones, in the extra bits
    :data:`GUARD` provides; the result is truncated to the datapath width at the
    end.
    """
    index %= points
    if index == 0:
        return constant(0, width, points)
    inner = width + GUARD
    levels = log2(points)
    bits = [i for i in range(levels) if index & (1 << i)]
    result = constant(1 << bits[-1], inner, points)
    for bit in reversed(bits[:-1]):
        factor = constant(1 << bit, inner, points)
        result = multiply(result[0], result[1], factor[0], factor[1], inner)
    # The chain is truncated and only then conjugated.  Negating before the
    # truncation would not be symmetric: an arithmetic shift rounds towards
    # minus infinity, so the conjugate of a truncated negative value is not the
    # truncation of the conjugate.
    # The division rounds towards minus infinity, so it can land one unit past
    # the range of the datapath - which is why it is clamped again, the way the
    # hardware clamps it.
    scale = 1 << GUARD
    re = saturate(saturate(result[0], inner) // scale, width)
    im = saturate(saturate(result[1], inner) // scale, width)
    return (re, wrap(-im, width) if inverse else im)


def twiddle_logic(index: int, width: int, points: int,
                  inverse: bool = False) -> tuple[int, int]:
    """The factor of ``index`` as the logic which replaces the memory.

    The gates realise the same function as the table, so the value is the entry
    of the table: there is nothing to approximate, only something to pay for in
    gates.
    """
    if points > LOGIC_LIMIT:
        raise ValueError(f"the logic structure is meant for a small transform, "
                         f"{points} points is past the {LOGIC_LIMIT} this model "
                         f"supports")
    re, im = constant(index % points, width, points)
    if inverse:
        im = wrap(-im, width)
    return re, im


def twiddle_no_mem(index: int, width: int, points: int, mode: str,
                   inverse: bool = False) -> tuple[int, int]:
    """The factor of ``index`` in one of the two memory free structures."""
    if mode == "no_mem_cascade":
        return twiddle_cascade(index, width, points, inverse)
    if mode == "no_mem_logic":
        return twiddle_logic(index, width, points, inverse)
    raise ValueError(f"not a memory free twiddle mode: {mode!r}")


def cascade_cells(points: int) -> int:
    """The number of cells of a cascade, the multiplier free ones.

    A cell whose constant is ``+1``, ``-1`` or ``-j`` is wiring, so only the
    cells of the other factors count as rotators.
    """
    trivial = {0, points // 4, points // 2}
    return sum(1 for i in range(log2(points)) if (1 << i) not in trivial)
