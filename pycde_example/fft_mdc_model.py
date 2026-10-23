"""The multi path delay commutator, composed out of the commutator chain.

The first stage of the decimation in frequency pairs ``a[j]`` with
``a[j + points / 2]``, so the two halves of the frame meet there and nowhere
else: from the second stage on the pairing distance is at most ``points / 4``,
which keeps both members of a pair inside the same half.

The architecture follows from that, and it is the commutator sibling of the
feedback one: a butterfly of the first stage splits the frame, and each half is
transformed by a delay commutator chain of its own.  The two halves meet in the
first stage and nowhere else, so the chains are independent and work at the same
time.

The arithmetic is therefore the one of the multi path delay feedback architecture
- the transform does not care which hardware computes it - and only the datapath
of a chain differs: a feedback stage writes the difference of its butterfly back
into a line of its own, a commutator stage forwards it through a line of its own.
This model is written on top of the commutator chain so that the two cannot drift
apart, and the tests compare it with the feedback one bit for bit.
"""

from __future__ import annotations

from .fft_model import apply_twiddle, wrap
from .fft_radix_model import expand_radices
from .fft_sdc_radix_model import sdc_radix


def chain_radices(radices: str | list[int], points: int) -> list[int]:
    """The radices of the two chains.

    The decomposition starts with the stage which splits the frame - a radix 2
    one, since it is the butterfly of the first stage of the decimation in
    frequency - and the rest belongs to the chains, which work on half of the
    frame each.
    """
    stages = expand_radices(radices, points)
    if stages[0] != 2:
        raise ValueError(f"the first stage of this architecture splits the frame "
                         f"and is a radix 2 one, got the radices {radices!r}")
    return stages[1:]


def mdc(samples: list[tuple[int, int]], width: int, points: int,
        scale: bool = True, radices: str | list[int] = "2",
        ) -> list[tuple[int, int]]:
    """The spectrum of one frame, in the natural order."""
    half = points // 2
    stages = chain_radices(radices, points)

    # the leading butterfly: the sum down one path, the rotated difference down
    # the other one
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

    # every half is transformed by a commutator chain of its own
    even_path = sdc_radix(sums, width, half, stages, scale)
    odd_path = sdc_radix(differences, width, half, stages, scale)

    # the chains hand out the natural order, so the halves interleave directly
    result = [(0, 0)] * points
    for k in range(half):
        result[2 * k] = even_path[k]
        result[2 * k + 1] = odd_path[k]
    return result
