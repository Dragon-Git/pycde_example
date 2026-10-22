"""Bit exact software model of the configurable FFT.

This module is free of any PyCDE dependency: it is used by the RTL generator
(``fft.py``) *and* by the tests, which allows the expected results to be
computed on the host without running a simulator.

Fixed point format
------------------
A real number ``v`` is represented by ``round(v * 2**(width - 1))`` in a two's
complement integer of ``width`` bits (the sign bit included).  The complex
product of two such numbers is truncated to the most significant ``width``
bits, exactly like a fixed point multiplier which drops the fractional bits.

The model mirrors the RTL exactly: the same twiddle factors, the same
truncation of the arithmetic and the same scaling of the stages.
"""

from __future__ import annotations

import math


def wrap(value: int, width: int) -> int:
    """Truncate ``value`` to ``width`` bits, interpreting it as two's complement."""
    mask = (1 << width) - 1
    value &= mask
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


def truncate(value: int, width: int) -> int:
    """Keep the most significant ``width`` bits of ``value``.

    This is what a fixed point multiplier does: the product of two numbers
    with ``width`` bits has ``2 * width`` bits, the fractional bits are
    dropped.
    """
    return wrap(value >> (width - 1), width)


def bit_reverse(value: int, bits: int) -> int:
    """Reverse the ``bits`` bits of ``value``."""
    result = 0
    for i in range(bits):
        if value & (1 << i):
            result |= 1 << (bits - 1 - i)
    return result


def twiddle_table(points: int, width: int) -> list[tuple[int, int]]:
    """``W_N**k = exp(-2j*pi*k/N)`` in the fixed point format.

    Only the first ``N/2`` entries are needed, the remaining ones are the
    conjugates of the first ones.  The components are clamped to the
    representable range: the fixed point format cannot represent exactly
    ``+1.0`` (that would be the value ``1 << (width - 1)``).
    """
    scale = 1 << (width - 1)
    maximum = (1 << (width - 1)) - 1
    # the most negative value is not representable as a constant
    minimum = -((1 << (width - 1)) - 1)
    table = []
    for k in range(points // 2):
        angle = -2.0 * math.pi * k / points
        re = min(max(round(scale * math.cos(angle)), minimum), maximum)
        im = min(max(round(scale * math.sin(angle)), minimum), maximum)
        table.append((re, im))
    return table


def complex_multiply(a_re: int, a_im: int, b_re: int, b_im: int,
                     width: int) -> tuple[int, int]:
    """The complex product of two fixed point numbers (truncating)."""
    return (truncate(a_re * b_re - a_im * b_im, width),
            truncate(a_re * b_im + a_im * b_re, width))


def apply_twiddle(index: int, re: int, im: int, width: int, points: int,
                  inverse: bool = False) -> tuple[int, int]:
    """Multiply a complex number with the twiddle factor ``W**index``.

    The trivial factors are applied exactly, the way the hardware does it:
    ``W**0`` is a wire - the table cannot hold ``+1.0`` (it needs one bit more
    than the datapath has), so its entry is one unit short of one and
    multiplying with it would lose a unit of the last bit in every stage - and
    ``W**(N/4)`` is ``-j``, which is a swap and a negation.  A multiplier is
    only needed for the factors which are neither.

    This is the single definition of the twiddle factor arithmetic: the models
    of the architectures and their RTL all follow it.
    """
    if index % points == 0:
        return (re, im)
    if index % points == points // 4:
        # -j for the transform, +j for the inverse one
        if inverse:
            return (wrap(-im, width), re)
        return (im, wrap(-re, width))
    table = twiddle_table(points, width)
    w_re, w_im = table[index % (points // 2)]
    if inverse:
        w_im = -w_im
    return complex_multiply(w_re, w_im, re, im, width)


def fft(samples: list[tuple[int, int]], width: int, points: int,
        dit: bool = True, scale: bool = True, inverse: bool = False,
        twiddle_mode: str = "rom") -> list[tuple[int, int]]:
    """The bit exact model of the FFT datapath.

    ``samples`` holds the ``points`` input samples (real, imaginary) in
    natural order as fixed point numbers.  The result is the spectrum in
    natural order as well: the difference between decimation in time and
    decimation in frequency is the order in which the samples are read from
    (and written to) the frame memory, not the order of the result.

    ``inverse`` conjugates the twiddle factors, the input and the output have
    to be conjugated by the caller.
    """
    if len(samples) != points:
        raise ValueError("the number of samples must match the number of points")
    if points & (points - 1):
        raise ValueError("the number of points must be a power of two")
    stages = points.bit_length() - 1

    data = [(wrap(re, width), wrap(im, width)) for (re, im) in samples]
    if dit:
        # decimation in time: the input is read bit reversed
        data = [data[bit_reverse(i, stages)] for i in range(points)]

    table = twiddle_table(points, width)
    if inverse:
        table = [(re, -im) for (re, im) in table]
    if twiddle_mode == "rom":
        def get_twiddle(index: int) -> tuple[int, int]:
            return table[index]
    elif twiddle_mode in ("cordic", "hybrid"):
        iterations = cordic_iterations(width)

        def get_twiddle(index: int) -> tuple[int, int]:
            return twiddle_cordic(index, width, points, iterations, inverse)
    else:
        raise ValueError(f"unknown twiddle mode: {twiddle_mode!r}")
    def rotate(index: int, re: int, im: int) -> tuple[int, int]:
        """Multiply a complex number with the twiddle factor of ``index``."""
        if twiddle_mode == "rom":
            return apply_twiddle(index, re, im, width, points, inverse)
        # the CORDIC produces its own factors, they are all non trivial
        w_re, w_im = get_twiddle(index)
        return complex_multiply(w_re, w_im, re, im, width)

    # the decimation in time processes the small butterflies first, the
    # decimation in frequency the large ones
    pass_order = range(stages) if dit else reversed(range(stages))
    for s in pass_order:
        half = 1 << s
        step = points // (2 * half)
        for group in range(points // (2 * half)):
            for j in range(half):
                i0 = group * 2 * half + j
                i1 = i0 + half
                a_re, a_im = data[i0]
                b_re, b_im = data[i1]
                if scale:
                    # the operands are halved before they are added, so that
                    # the magnitude of the datapath does not grow from stage
                    # to stage (the stage scales by 1/2 in total)
                    a_re >>= 1
                    a_im >>= 1
                    b_re >>= 1
                    b_im >>= 1
                if dit:
                    # the twiddle multiplies the second input of the butterfly
                    t_re, t_im = rotate(j * step, b_re, b_im)
                    u_re, u_im = a_re, a_im
                else:
                    # the twiddle multiplies the output of the butterfly
                    u_re, u_im = a_re, a_im
                    t_re, t_im = b_re, b_im
                sum_re = wrap(u_re + t_re, width)
                sum_im = wrap(u_im + t_im, width)
                diff_re = wrap(u_re - t_re, width)
                diff_im = wrap(u_im - t_im, width)
                if not dit:
                    diff_re, diff_im = rotate(j * step, diff_re, diff_im)
                data[i0] = (sum_re, sum_im)
                data[i1] = (diff_re, diff_im)

    if not dit:
        # decimation in frequency: the output is written bit reversed
        data = [data[bit_reverse(i, stages)] for i in range(points)]
    return data


def dft(samples: list[tuple[int, int]]) -> list[complex]:
    """The floating point reference: the discrete Fourier transform."""
    points = len(samples)
    result = []
    for k in range(points):
        acc = 0j
        for n, (re, im) in enumerate(samples):
            angle = -2.0 * math.pi * k * n / points
            acc += complex(re, im) * complex(math.cos(angle), math.sin(angle))
        result.append(acc)
    return result


def cordic_iterations(width: int) -> int:
    """The number of iterations of the CORDIC which generates the twiddles.

    The CORDIC has to resolve the angle down to the least significant bit of
    the angle format, so it depends on the width of the datapath.
    """
    return max(4, width - 2)


def twiddle_cordic(index: int, width: int, points: int, iterations: int | None = None,
                   inverse: bool = False) -> tuple[int, int]:
    """The twiddle factor which is generated by a CORDIC rotator.

    The result is bit exact with the hardware: the CORDIC of the ``cordic``
    example is used, its gain is compensated by the magnitude of its input.
    A CORDIC can only rotate by about +-1.74 radian, the factors of the
    second quadrant are built from the first ones.
    """
    from .cordic_model import cordic as cordic_rotate
    from .cordic_model import cordic_gain

    if iterations is None:
        iterations = cordic_iterations(width)
    angle_shift = width - 1 - (points.bit_length() - 1)
    quarter = max(1, points // 4)
    reduced = index % quarter
    second = index >= quarter
    angle = reduced << angle_shift
    if not inverse:
        angle = -angle
    gain = cordic_gain(iterations)
    real_input = int(((1 << (width - 1)) - 1) / gain)
    (re, im, _) = cordic_rotate(real_input, 0, angle, width, iterations,
                              "rotation")
    if second:
        # multiply by -j
        (re, im) = (im, wrap(-re, width))
    return (re, im)


def fft_inverse(samples: list[tuple[int, int]], width: int, points: int,
                dit: bool = True, scale: bool = True,
                twiddle_mode: str = "rom") -> list[tuple[int, int]]:
    """The bit exact model of the inverse transform.

    The inverse transform uses the conjugated twiddle factors, the structure
    of the transform is the same.
    """
    return fft(samples, width, points, dit=dit, scale=scale, inverse=True,
               twiddle_mode=twiddle_mode)


def to_fixed(value: float, width: int) -> int:
    """Convert a real number into the fixed point format."""
    return round(value * (1 << (width - 1)))


def from_fixed(value: int, width: int) -> float:
    """Convert a fixed point number back into a real number."""
    return value / (1 << (width - 1))
