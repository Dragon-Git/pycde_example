"""Bit exact model of the single path delay commutator (SDC) architecture.

Where the delay feedback chain of ``fft_sdf_model`` writes the difference of
the butterfly back into the delay line of the stage, the delay commutator
chain keeps the delay line for the forward stream only and uses a commutator
(a rotating switch) to send both the sum and the difference of the butterfly
to the next stage.  Both are radix-2 DIF pipelines, the difference is the
structure of the stage.

The structure of a stage (``s >= 1``):

* the difference of the previous stage is multiplied with the twiddle factor
  of the stage and delayed by ``points / 2**(s+1)`` cycles,
* the commutator is driven by one bit of the frame counter: in the first half
  of its window it passes the sum of the previous stage through and swaps the
  delayed difference into the delay line, in the second half it swaps them,
* the butterfly combines the delayed first output of the commutator with the
  second one and scales the result by ``1/2``.

The stage 0 pairs the input with the input delayed by ``points / 2``.

The output stream of the architecture is bit reversed and interleaved: the
first half of the frame carries the even bins, the second half the odd ones,
both in bit reversed order and rotated by one position.  :func:`sdc` returns
the spectrum in the natural order.

The model was verified against a cycle accurate simulation of the reference
implementation of the architecture (the relations of every stage were checked
cycle by cycle).
"""

from __future__ import annotations

from .fft_model import complex_multiply, twiddle_table, wrap


def bit_reverse(value: int, bits: int) -> int:
    """Reverse the ``bits`` bits of ``value``."""
    result = 0
    for i in range(bits):
        if value & (1 << i):
            result |= 1 << (bits - 1 - i)
    return result


class Shift:
    """A shift register of ``depth`` entries (the buffers of the stages)."""

    def __init__(self, depth: int):
        self.depth = max(1, depth)
        self.q: list[tuple[int, int]] = []

    def step(self, value: tuple[int, int]) -> tuple[int, int]:
        """Shift one value in and return the value which leaves the line."""
        out = self.q[0] if len(self.q) >= self.depth else (0, 0)
        self.q.append(value)
        if len(self.q) > self.depth:
            self.q.pop(0)
        return out


def sdc_stream(samples: list[tuple[int, int]], width: int, points: int,
               scale: bool = True, cycles: int | None = None,
               ) -> list[tuple[int, int]]:
    """The output stream of the commutator architecture.

    ``samples`` holds the samples of one frame; they are fed into the
    architecture over and over again, so the stream is periodic with the
    frame.  The result of the frame appears after ``points`` cycles.
    """
    levels = points.bit_length() - 1
    half = points // 2
    table = twiddle_table(points, width)
    if cycles is None:
        cycles = len(samples) + 3 * points

    buf0 = Shift(half)
    rot_bufs = [Shift(max(1, points >> (s + 1))) for s in range(1, levels)]
    mux_bufs = [Shift(max(1, points >> (s + 1))) for s in range(1, levels)]
    out_buf = Shift(half)

    stream = []
    for cnt in range(cycles):
        value = samples[cnt % len(samples)]

        # stage 0: the input paired with the input delayed by points / 2
        delayed = buf0.step(value)
        a_re, a_im = delayed
        b_re, b_im = value
        if scale:
            # the operands of the butterfly are halved before they are added
            a_re, a_im = a_re >> 1, a_im >> 1
            b_re, b_im = b_re >> 1, b_im >> 1
        e = (wrap(a_re + b_re, width), wrap(a_im + b_im, width))
        o = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))

        for s in range(1, levels):
            # the commutator of the stage is driven by one bit of the counter
            sel = (cnt >> (levels - 1 - s)) & 1
            if s == levels - 1:
                # the last stage uses a trivial rotator: the factor is -j
                rot = (o[1], wrap(-o[0], width)) if sel else o
            else:
                index = (cnt * (1 << (s - 1))) % half
                w_re, w_im = table[index]
                rot = complex_multiply(w_re, w_im, o[0], o[1], width)
            rotated = rot_bufs[s - 1].step(rot)
            m0, m1 = ((rotated, e) if sel else (e, rotated))
            m0_delayed = mux_bufs[s - 1].step(m0)
            a_re, a_im = m0_delayed
            b_re, b_im = m1
            if scale:
                # the operands of the butterfly are halved before they are
                # added
                a_re, a_im = a_re >> 1, a_im >> 1
                b_re, b_im = b_re >> 1, b_im >> 1
            e = (wrap(a_re + b_re, width), wrap(a_im + b_im, width))
            o = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))

        # the output multiplexer: the sum in the first half of the window, the
        # difference delayed by points / 2 in the second one
        delayed_o = out_buf.step(o)
        stream.append(e if (cnt % points) < half else delayed_o)
    return stream


def output_order(points: int) -> list[int]:
    """The bin which every position of the output stream of a frame holds.

    The first half of the window carries the bins which the reference
    implementation calls the even ones, the second half the odd ones; both are
    bit reversed and rotated by one position.
    """
    levels = points.bit_length() - 1
    half = points // 2
    order = []
    for i in range(half):
        c = (i + 1) % half
        order.append(bit_reverse((2 * c) % points, levels))
    for i in range(half):
        c = (i + 1) % half
        order.append(bit_reverse((2 * c + 1) % points, levels))
    return order


def output_position(bin_index: int, points: int) -> int:
    """The position of ``bin_index`` in the output stream of a frame."""
    return output_order(points).index(bin_index)


def sdc(samples: list[tuple[int, int]], width: int, points: int,
        scale: bool = True) -> list[tuple[int, int]]:
    """The spectrum of one frame in the natural order."""
    stream = sdc_stream(samples, width, points, scale=scale,
                        cycles=len(samples) + 3 * points)
    window = stream[points:2 * points]
    result = [(0, 0)] * points
    for position, bin_index in enumerate(output_order(points)):
        result[bin_index] = window[position]
    return result
