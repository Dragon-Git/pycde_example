"""Bit exact model of the single path delay feedback (SDF) architecture.

The model is cycle accurate: it runs the chain of the stages and returns the
output stream.  It is the reference of the RTL in ``fft_sdf.py``.

The structure of a stage (the decimation in frequency):

* the stage owns a shift register (the delay line) of ``delay`` entries,
* the fresh value of the stage is combined with the oldest entry of the shift
  register (the 'delayed' operand),
* the difference of the butterfly is fed back into the shift register, the sum
  is forwarded to the next stage,
* while the stage loads its shift register (the first ``delay`` cycles of its
  window) the delayed data is forwarded instead, multiplied by the twiddle
  factor of the window.

The decimation in time is the mirror image of it: the twiddle factor
multiplies the fresh value of the stage and the delays grow from stage to
stage.

The shift register holds the operands of the butterfly: the fresh value is
halved (the scaling of the stage) when it enters the shift register, the
difference of the butterfly is at the same scale already.
"""

from __future__ import annotations

from .fft_model import apply_twiddle, twiddle_table, wrap


def bit_reverse(value: int, bits: int) -> int:
    """Reverse the ``bits`` bits of ``value``."""
    result = 0
    for i in range(bits):
        if value & (1 << i):
            result |= 1 << (bits - 1 - i)
    return result


class SdfStage:
    """One stage of the delay feedback chain."""

    def __init__(self, width: int, delay: int, dit: bool, scale: bool,
                 table: list[tuple[int, int]], step_size: int,
                 points: int = 0):
        self.width = width
        self.delay = delay
        self.dit = dit
        self.scale = scale
        self.table = table
        self.points = points or 2 * delay
        # the distance between two twiddle factors of the stage
        self.step_size = step_size
        # the shift register, the oldest entry first
        self.shift: list[tuple[int, int]] = []

    def _rotate(self, phase: int, re: int, im: int) -> tuple[int, int]:
        """Multiply with the twiddle factor of this phase of the window.

        The stage uses every ``step_size`` th factor of the table, and the
        trivial ones of them are applied exactly (see ``apply_twiddle``).
        """
        index = (phase % self.delay) * self.step_size
        return apply_twiddle(index, re, im, self.width, self.points)

    def step(self, inp: tuple[int, int], phase: int) -> tuple[int, int]:
        """One cycle of the stage: the input is consumed, the output is produced."""
        load = phase < self.delay
        delayed = self.shift[0] if self.shift else (0, 0)

        # the operands of the butterfly are halved before they are added
        fresh = (inp[0] >> 1, inp[1] >> 1) if self.scale else inp
        if self.dit and phase >= self.delay:
            # the twiddle factor multiplies the fresh value of the stage
            fresh = self._rotate(phase - self.delay, fresh[0], fresh[1])

        d_re, d_im = delayed
        f_re, f_im = fresh
        total = (wrap(d_re + f_re, self.width), wrap(d_im + f_im, self.width))
        difference = (wrap(d_re - f_re, self.width), wrap(d_im - f_im, self.width))

        if self.dit:
            out = delayed if load else total
        elif load:
            # the twiddle factor multiplies the data which leaves the delay
            # line, the difference of the previous window
            out = self._rotate(phase, d_re, d_im)
        else:
            out = total

        self.shift.append(fresh if load else difference)
        if len(self.shift) > self.delay:
            self.shift.pop(0)
        return out


def sdf_stream(samples: list[tuple[int, int]], width: int, points: int,
               dit: bool = False, scale: bool = True, pipeline: int = 0,
               cycles: int | None = None) -> list[tuple[int, int]]:
    """The output stream of the delay feedback architecture.

    ``samples`` holds the samples of one frame, they are fed into the
    architecture over and over again (the architecture is a streaming one).
    The result of a frame appears in the output stream after ``points - 1``
    cycles (plus the latency of the pipeline registers).

    ``pipeline`` is the number of registers between two stages, the window of
    a stage is shifted by the latency of the previous stages.
    """
    levels = points.bit_length() - 1
    if dit:
        delays = [1 << s for s in range(levels)]
    else:
        delays = [1 << s for s in range(levels)][::-1]
    # the offset of the window of a stage: the sum of the delays of the
    # previous stages and the latency of the pipeline registers
    offsets = [sum(delays[:i]) + i * pipeline for i in range(levels)]
    table = twiddle_table(points, width)
    stages = []
    for s, delay in enumerate(delays):
        # the decimation in frequency uses the factors with an increasing, the
        # decimation in time with a decreasing exponent
        step_size = 1 << s if not dit else 1 << (levels - 1 - s)
        stages.append(SdfStage(width, delay, dit, scale, table, step_size,
                              points))

    if cycles is None:
        cycles = len(samples) + points
    # the registers between the stages
    pipes = [[] for _ in range(levels)]
    out = []
    for cnt in range(cycles):
        value = samples[cnt % len(samples)]
        for s, stage in enumerate(stages):
            phase = (cnt - offsets[s]) & (2 * stage.delay - 1)
            value = stage.step(value, phase)
            if pipeline:
                # the register between two stages: the value of the stage
                # which is `pipeline` cycles old is passed on
                pipes[s].append(value)
                if len(pipes[s]) > pipeline:
                    value = pipes[s].pop(0)
                else:
                    value = (0, 0)
        out.append(value)
    return out


def sdf(samples: list[tuple[int, int]], width: int, points: int,
        dit: bool = False, scale: bool = True,
        pipeline: int = 0) -> list[tuple[int, int]]:
    """The spectrum of one frame, in the natural order.

    The decimation in frequency produces the spectrum bit reversed, the
    decimation in time reads the samples bit reversed.
    """
    levels = points.bit_length() - 1
    if dit:
        # the decimation in time reads the samples bit reversed
        data = [samples[bit_reverse(i, levels)] for i in range(points)]
    else:
        data = list(samples)
    latency = points - 1 + pipeline * levels
    stream = sdf_stream(data, width, points, dit=dit, scale=scale,
                        pipeline=pipeline, cycles=points + 3 * points)
    # the result of the frame appears after the latency of the architecture
    result = stream[latency:latency + points]
    if not dit:
        # the decimation in frequency produces the spectrum bit reversed
        result = [result[bit_reverse(i, levels)] for i in range(points)]
    return result
