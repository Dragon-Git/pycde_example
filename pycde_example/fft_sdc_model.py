"""Bit exact model of the single path delay commutator (SDC) architecture.

Relation to the delay feedback architecture
-------------------------------------------
This module and ``fft_sdf_model`` are two hardware mappings of the same
transform (the radix-2 decimation in frequency).  They share the butterfly
arithmetic and the mathematical definition of the twiddle factors, but the
pipelines are organised differently:

* the delay feedback chain is a **feedback** structure: the sum of a butterfly
  is forwarded and the difference is written back into the shift register of
  the *same* stage, from which it returns to the same butterfly a few cycles
  later.  The butterfly is time shared between the two roles, and the storage
  is ``points - 1`` registers.
* the delay commutator chain is a **feed forward, commutating** structure:
  there is no loop.  A commutator - a multiplexer together with a delay line -
  rearranges the stream so that one word per cycle leaves every stage.  The
  storage is ``2 * points - 2`` registers, and the control is a commutator
  schedule rather than write enables.

The arithmetic core is shared, the pipeline organisation is not.

The structure of a stage
------------------------
* the stage 0 pairs the input with the input delayed by ``points / 2``; it has
  no commutator, because both of its outputs are consumed by the next stage,
* every other stage multiplies the difference of the previous stage with the
  twiddle factor of the stage, delays it by ``points / 2**(s+1)`` and hands it
  to the commutator, which swaps it with the sum of the previous stage; the
  commutator is driven by ``counter[levels - 1 - s]``,
* the butterfly of the stage combines the delayed first output of the
  commutator with its second output, the operands are halved before they are
  added,
* the last stage rotates with a trivial rotator, its factor is ``-j``.

The output stage
----------------
The sum of the last stage and its difference delayed by ``points / 2`` are
interleaved by a multiplexer.  Its selection is the valid signal of the
architecture, which is delayed by the whole latency ``points - 1``, so the
window of the multiplexer is **rotated by ``points - 1``** with respect to the
frame counter - it is not ``counter < points / 2``.

The spectrum leaves the chain in the first ``points`` cycles of the rotated
window, ``points - 1`` cycles after the first sample of the frame.  The output
stream is bit reversed and interleaved: the first half of the window carries
the even bins, the second half the odd ones, both in bit reversed order.

The architecture is a streaming pipeline: frames are fed back to back, the
delay lines hold the data of the previous frame while the current one is
processed.  A frame must not be followed by zeros.

The model was derived by expressing every output position of the chain as a
linear combination of the input samples (with exact arithmetic) and matching it
against the discrete Fourier transform.
"""

from __future__ import annotations

from .fft_model import apply_twiddle, wrap


def bit_reverse(value: int, bits: int) -> int:
    """Reverse the ``bits`` bits of ``value``."""
    result = 0
    for i in range(bits):
        if value & (1 << i):
            result |= 1 << (bits - 1 - i)
    return result


def output_order(points: int) -> list[int]:
    """The bin which every position of the output window holds.

    The first half carries the even bins, the second half the odd ones, both
    in bit reversed order.
    """
    levels = points.bit_length() - 1
    half = points // 2
    order = [bit_reverse((2 * c) % points, levels) for c in range(half)]
    order += [bit_reverse((2 * c + 1) % points, levels) for c in range(half)]
    return order


def output_position(bin_index: int, points: int) -> int:
    """The position of ``bin_index`` in the output window of a frame."""
    return output_order(points).index(bin_index)


class Shift:
    """A delay line of ``depth`` entries."""

    def __init__(self, depth: int):
        self.depth = max(1, depth)
        self.q: list[tuple[int, int]] = []

    def step(self, value: tuple[int, int]) -> tuple[int, int]:
        out = self.q[0] if len(self.q) >= self.depth else (0, 0)
        self.q.append(value)
        if len(self.q) > self.depth:
            self.q.pop(0)
        return out


def sdc_stream(samples: list[tuple[int, int]], width: int, points: int,
               scale: bool = True, cycles: int | None = None,
               ) -> list[tuple[int, int]]:
    """The output stream of the commutator architecture.

    ``samples`` are fed into the chain on consecutive cycles; the frames follow
    each other without gaps, because the chain is a streaming pipeline.
    """
    levels = points.bit_length() - 1
    half = points // 2
    if cycles is None:
        cycles = len(samples) + 3 * points

    # the selection of the output multiplexer is the valid signal of the
    # architecture, delayed by the latency of the chain
    out_shift = points - 1

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
            a_re, a_im = a_re >> 1, a_im >> 1
            b_re, b_im = b_re >> 1, b_im >> 1
        e = (wrap(a_re + b_re, width), wrap(a_im + b_im, width))
        o = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))

        for s in range(1, levels):
            sel = (cnt >> (levels - 1 - s)) & 1
            if s == levels - 1:
                # the last stage rotates with a trivial rotator only: the
                # factor is -j
                rot = (o[1], wrap(-o[0], width)) if sel else o
            else:
                index = (cnt * (1 << (s - 1))) % half
                rot = apply_twiddle(index, o[0], o[1], width, points)
            rotated = rot_bufs[s - 1].step(rot)
            m0, m1 = (rotated, e) if sel else (e, rotated)
            m0_delayed = mux_bufs[s - 1].step(m0)
            a_re, a_im = m0_delayed
            b_re, b_im = m1
            if scale:
                a_re, a_im = a_re >> 1, a_im >> 1
                b_re, b_im = b_re >> 1, b_im >> 1
            e = (wrap(a_re + b_re, width), wrap(a_im + b_im, width))
            o = (wrap(a_re - b_re, width), wrap(a_im - b_im, width))

        # the output multiplexer: its window is rotated by the latency
        delayed_o = out_buf.step(o)
        in_first_half = ((cnt - out_shift) % points) < half
        stream.append(e if in_first_half else delayed_o)
    return stream


def sdc(samples: list[tuple[int, int]], width: int, points: int,
        scale: bool = True) -> list[tuple[int, int]]:
    """The spectrum of the frame in the natural order.

    ``samples`` is one frame; the chain is streamed with the frame repeated,
    and the window of the frame is taken ``points - 1`` cycles after its first
    sample.
    """
    stream = sdc_stream(samples, width, points, scale=scale,
                        cycles=2 * points)
    window = stream[points - 1:2 * points - 1]
    result = [(0, 0)] * points
    for position, bin_index in enumerate(output_order(points)):
        result[bin_index] = window[position]
    return result
