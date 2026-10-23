"""The mixed radix model of the FFT datapath.

The radix 2 model is the special case where every stage halves the length of the
sub transform.  A stage of radix ``R`` instead combines ``R`` samples which are
``length / R`` apart, applies an ``R`` point transform to them and rotates the
result::

    y[r] = sum(l = 0 .. R-1) x[l] * W_R ** (l * r)
    x[j + r * M] = y[r] * W_L ** (j * r) / R

with ``L`` the length of the sub transform the stage works on and ``M = L / R``.
Writing ``R = 2`` gives back the radix 2 stage of the reference model, which is
why the two agree bit for bit when the datapath arithmetic is the same.

The radices are a list whose product is the number of points, so ``"4"`` is a
pure radix 4 transform, ``"4,2"`` a radix 4 pass followed by a radix 2 one.  The
rotation of the result is what makes the passes differ; the ``R`` point
transform inside a butterfly uses only the ``R``-th roots of unity, which are
applied exactly where they are trivial (``+1``, ``-1``, ``-j``).
"""

from __future__ import annotations

from .fft_model import apply_twiddle, wrap


def parse_radices(radices: str | list[int]) -> list[int]:
    """The radices as a list of integers, checking that they are usable."""
    items = ([int(part) for part in radices.split(",") if part.strip()]
             if isinstance(radices, str) else [int(r) for r in radices])
    if not items:
        raise ValueError("at least one radix is needed")
    for radix in items:
        if radix < 2 or (radix & (radix - 1)):
            raise ValueError(f"a radix must be a power of two and at least 2, "
                             f"got {radix}")
    return items


def radix_size(radices: str | list[int]) -> int:
    """The number of points the radices describe."""
    size = 1
    for radix in parse_radices(radices):
        size *= radix
    return size


def expand_radices(radices: str | list[int], points: int) -> list[int]:
    """The radices of a transform of ``points`` points.

    A single radix is repeated until it fills the transform, which is how a
    configuration says "all stages have this radix": ``"2"`` on 16 points is
    four radix 2 stages and ``"4"`` on 64 points three radix 4 ones.  A list of
    several radices is taken literally and has to describe exactly ``points``
    points, because how a mixed list should be repeated would be a guess.
    """
    stages = parse_radices(radices)
    if len(stages) == 1:
        radix = stages[0]
        if points % radix:
            raise ValueError(f"a radix of {radix} does not fill {points} points")
        expanded = []
        size = 1
        while size < points:
            expanded.append(radix)
            size *= radix
        return expanded
    size = radix_size(stages)
    if size != points:
        raise ValueError(f"the radices {radices!r} describe {size} points, "
                         f"not {points}")
    return stages


def log2(value: int) -> int:
    """The binary logarithm of a power of two."""
    return value.bit_length() - 1


def mixed_reverse(index: int, radices: list[int]) -> int:
    """Reverse the order of the mixed radix digits of ``index``.

    The digits of a mixed radix number are the remainders of the successive
    divisions by the radices, the most significant digit belonging to the last
    radix of the list.  Reversing them gives the index whose digits are the
    same in the opposite order, which is the permutation of a mixed radix
    transform - for a single radix 2 it is the bit reversal.
    """
    digits = []
    rest = index
    for radix in radices:
        digits.append(rest % radix)
        rest //= radix
    # the weight of a digit is the product of the radices to its right
    result = 0
    for position, digit in enumerate(digits):
        weight = 1
        for radix in radices[position + 1:]:
            weight *= radix
        result += digit * weight
    return result


def butterfly(values: list[tuple[int, int]], width: int,
              inverse: bool = False) -> list[tuple[int, int]]:
    """The ``R`` point transform inside a stage of radix ``R``.

    It uses the ``R``-th roots of unity only, and those which are trivial
    (``+1``, ``-1``, ``-j``) are applied exactly: a table cannot hold them in
    the fixed point format, so multiplying with an entry a unit short of one
    would cost a unit of the last bit inside every butterfly.
    """
    size = len(values)
    if size == 2:
        a_re, a_im = values[0]
        b_re, b_im = values[1]
        return [(wrap(a_re + b_re, width), wrap(a_im + b_im, width)),
                (wrap(a_re - b_re, width), wrap(a_im - b_im, width))]
    result = []
    for r in range(size):
        total_re = 0
        total_im = 0
        for l, (re, im) in enumerate(values):
            rotated_re, rotated_im = apply_twiddle(
                l * r, re, im, width, size, inverse)
            total_re += rotated_re
            total_im += rotated_im
        result.append((wrap(total_re, width), wrap(total_im, width)))
    return result


def fft_mixed(samples: list[tuple[int, int]], width: int, points: int,
              radices: str | list[int] = "2", dit: bool = True,
              scale: bool = True, inverse: bool = False,
              ) -> list[tuple[int, int]]:
    """The bit exact model of a mixed radix FFT datapath.

    ``samples`` holds the ``points`` input samples in natural order and the
    result is the spectrum in natural order as well: the decimation in time
    reads the samples in the permuted order and the decimation in frequency
    writes the result in it, the spectrum itself is always natural.
    """
    stages = expand_radices(radices, points)
    if len(samples) != points:
        raise ValueError("the number of samples must match the number of points")

    data = [(wrap(re, width), wrap(im, width)) for (re, im) in samples]
    stage_list = list(reversed(stages)) if dit else list(stages)
    if dit:
        # Decimation in time reads the samples in the permuted order.  The
        # permutation has to follow the order in which the stages run, so it
        # is built from the reversed list - the same thing as the bit
        # reversal for a uniform radix, and the difference for a mixed one.
        permuted_radices = list(reversed(stages))
        data = [data[mixed_reverse(i, permuted_radices)]
                for i in range(points)]

    if dit:
        # The decimation in time starts with the smallest butterfly: a stage
        # works on blocks of `length` samples, made of `radix` interleaved
        # sub blocks, and the twiddle belongs to the input of the butterfly.
        length = 1
        for radix in stage_list:
            length *= radix
            sub = length // radix
            shift = log2(radix)
            for base in range(0, points, length):
                for j in range(sub):
                    values = []
                    for l in range(radix):
                        re, im = data[base + j + l * sub]
                        if scale:
                            re >>= shift
                            im >>= shift
                        if l:
                            # the rotation of the input, as a factor of the
                            # whole transform
                            index = (j * l * (points // length)) % points
                            re, im = apply_twiddle(index, re, im, width,
                                                   points, inverse)
                        values.append((re, im))
                    transformed = butterfly(values, width, inverse)
                    for r in range(radix):
                        data[base + j + r * sub] = transformed[r]
    else:
        # The decimation in frequency works the large butterflies first and
        # rotates the result of a butterfly, not its input.
        length = points
        for radix in stage_list:
            sub = length // radix
            shift = log2(radix)
            for base in range(0, points, length):
                for j in range(sub):
                    values = []
                    for l in range(radix):
                        re, im = data[base + j + l * sub]
                        if scale:
                            re >>= shift
                            im >>= shift
                        values.append((re, im))
                    transformed = butterfly(values, width, inverse)
                    for r in range(radix):
                        re, im = transformed[r]
                        if r:
                            index = (j * r * (points // length)) % points
                            re, im = apply_twiddle(index, re, im, width,
                                                   points, inverse)
                        data[base + j + r * sub] = (re, im)
            length = sub

    if not dit:
        # decimation in frequency writes the result in the permuted order
        data = [data[mixed_reverse(i, stages)] for i in range(points)]
    return data
