"""Bit exact model of the multi path delay feedback (MDF) architecture.

The derivation
--------------
The first stage of the decimation in frequency pairs ``a[j]`` with
``a[j + points / 2]``::

    u[j] = a[j] + a[j + points / 2]
    v[j] = (a[j] - a[j + points / 2]) * W**j

The two halves meet there and nowhere else, because from the second stage on the
pairing distance is at most ``points / 4``, so both members of a pair lie inside
the same half.  The architecture is therefore a butterfly of the first stage
followed by two delay feedback chains, one per half: the sum travels down the
first path and the rotated difference down the second one, and each path is a
single path delay feedback chain of its own.

That is what the name says - several paths, each of them fed back - and it is
where the throughput comes from: two chains work at the same time, each on half
of the frame.

The results come out interleaved: a chain produces its half of the spectrum in
the bit reversed order, the sum path holds the even bins and the difference path
the odd ones.
"""

from __future__ import annotations

from .fft_model import apply_twiddle, twiddle_table, wrap
from .fft_radix_model import expand_radices
from .fft_sdf_model import SdfStage, bit_reverse
from .fft_sdf_radix_model import sdf_radix


class MdfPath:
    """One of the two delay feedback chains of the architecture."""

    def __init__(self, width: int, points: int, scale: bool,
                 table: list[tuple[int, int]], step_scale: int = 1):
        self.width = width
        self.points = points
        self.scale = scale
        self.levels = points.bit_length() - 1
        # the decimation in frequency shrinks the pairing distance
        self.delays = [(points >> (s + 1)) for s in range(self.levels)]
        self.offsets = [sum(self.delays[:i]) for i in range(self.levels)]
        self.stages = [
            SdfStage(width, self.delays[s], False, scale, table,
                     (1 << s) * step_scale, points)
            for s in range(self.levels)
        ]

    def latency(self) -> int:
        """The number of cycles until the first result leaves the chain."""
        return sum(self.delays)

    def step(self, value: tuple[int, int], count: int) -> tuple[int, int]:
        for s, stage in enumerate(self.stages):
            phase = (count - self.offsets[s]) % (2 * stage.delay)
            value = stage.step(value, phase)
        return value


def chain_radices(radices: str | list[int], points: int) -> list[int]:
    """The radices of the two chains.

    The decomposition of a multi path delay feedback transform starts with the
    stage which splits the frame - a radix 2 one, since it is the butterfly of
    the first stage of the decimation in frequency - and the rest belongs to the
    chains, which work on half of the frame each.  So ``"2,4"`` on 16 points is
    the split followed by one radix 4 stage on eight points.
    """
    stages = expand_radices(radices, points)
    if stages[0] != 2:
        raise ValueError(f"the first stage of this architecture splits the frame "
                         f"and is a radix 2 one, got the radices {radices!r}")
    return stages[1:]


def mdf(samples: list[tuple[int, int]], width: int, points: int,
        scale: bool = True, radices: str | list[int] = "2",
        ) -> list[tuple[int, int]]:
    """The spectrum of one frame in the natural order."""
    half = points // 2
    stages = chain_radices(radices, points)
    if any(radix != 2 for radix in stages):
        # a larger radix inside the chains is the same transform, so the
        # chains are the ones the radix model builds
        return mdf_radix(samples, width, points, stages, scale)
    table = twiddle_table(points, width)

    # the leading butterfly: the two halves meet here
    sums = []
    differences = []
    for j in range(half):
        a_re, a_im = samples[j]
        b_re, b_im = samples[j + half]
        if scale:
            a_re, a_im = a_re >> 1, a_im >> 1
            b_re, b_im = b_re >> 1, b_im >> 1
        sums.append((wrap(a_re + b_re, width), wrap(a_im + b_im, width)))
        difference = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))
        # the difference is rotated, which is what makes the halves independent
        differences.append(apply_twiddle(j, difference[0], difference[1],
                                         width, points))

    # every half is transformed by a delay feedback chain of its own
    even_path = MdfPath(width, half, scale, table)
    odd_path = MdfPath(width, half, scale, table)
    latency = even_path.latency()
    cycles = latency + 2 * half
    even_out = []
    odd_out = []
    for count in range(cycles):
        even_out.append(even_path.step(
            sums[count] if count < half else (0, 0), count))
        odd_out.append(odd_path.step(
            differences[count] if count < half else (0, 0), count))

    # A delay feedback chain of the decimation in frequency produces its result
    # bit reversed, so the window is read in that order; the two paths then
    # interleave into the even and the odd bins of the transform.
    sub_levels = half.bit_length() - 1
    result = [(0, 0)] * points
    for k in range(half):
        source = bit_reverse(k, sub_levels)
        result[2 * k] = even_out[latency + source]
        result[2 * k + 1] = odd_out[latency + source]
    return result


def mdf_radix(samples: list[tuple[int, int]], width: int, points: int,
              stages: list[int], scale: bool = True,
              ) -> list[tuple[int, int]]:
    """The spectrum when the chains carry a butterfly of their own radix.

    The first stage is the same whatever the chains are: it splits the frame into
    the sum and the rotated difference.  What changes is only how a half is
    transformed, and that is the delay feedback chain over `points / 2` points.
    """
    half = points // 2
    sums = []
    differences = []
    for j in range(half):
        a_re, a_im = samples[j]
        b_re, b_im = samples[j + half]
        if scale:
            a_re, a_im = a_re >> 1, a_im >> 1
            b_re, b_im = b_re >> 1, b_im >> 1
        sums.append((wrap(a_re + b_re, width), wrap(a_im + b_im, width)))
        difference = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))
        differences.append(apply_twiddle(j, difference[0], difference[1],
                                         width, points))
    even_path = sdf_radix(sums, width, half, stages, scale)
    odd_path = sdf_radix(differences, width, half, stages, scale)
    result = [(0, 0)] * points
    for k in range(half):
        result[2 * k] = even_path[k]
        result[2 * k + 1] = odd_path[k]
    return result
