"""The radix R delay feedback stage, and the chain built from it.

The radix 2 stage keeps one shift register of `sub = L/2` and works in a window
of `L` cycles.  In the first half the samples enter the register and it hands out
the ones the previous window left; in the second half the butterfly adds them and
the difference goes back into the register.

The generalisation follows from one observation: a shift register of depth `d`
hands out what was pushed into it `d` cycles ago, so `d` is the time a value has
to be held.  A stage of radix `R` has `R` quarters of `sub = L/R` cycles each,
and two kinds of value need holding:

* the sample of quarter `q` takes part in the butterfly of quarter `R - 1`, so it
  waits `(R - 1 - q) * sub` cycles;
* the difference of arm `r` is produced at quarter `R - 1` and handed out at
  quarter `r - 1` of the next window, so it waits `r * sub` cycles.

Both are the same set of durations, so the stage keeps `R - 1` registers,
register `k` of depth `k * sub`.  Register `k` carries the sample of quarter
`R - 1 - k` and the difference of arm `k`: exactly what the single register of
the radix 2 stage carries in the two halves of its window.  Every register is
pushed on every cycle, with a zero when it is not its turn, because a shift
register has to keep moving for its depth to mean a time.

The storage of a stage is `L * (R - 1) / 2`, against `L / 2` at radix 2.  A
uniform radix `R` transform of `N` points therefore needs about `N * R / 2`
registers: a larger butterfly trades storage for fewer stages.  The latency of
the chain does not change, it is `points - 1` for every radix, because the last
stage always has a window of `R` cycles and the registers of the stages add up to
the same total.
"""

from __future__ import annotations

from .fft_model import apply_twiddle
from .fft_radix_model import butterfly, expand_radices, mixed_reverse


class RadixLine:
    """A shift register of ``depth`` entries which moves on every cycle."""

    def __init__(self, depth: int):
        self.depth = max(1, depth)
        self.q: list[tuple[int, int]] = []

    def tap(self) -> tuple[int, int]:
        """What was pushed ``depth`` cycles ago."""
        return self.q[0] if len(self.q) >= self.depth else (0, 0)

    def step(self, value: tuple[int, int]) -> tuple[int, int]:
        """Shift the register, pushing ``value`` in."""
        out = self.tap()
        self.q.append(value)
        if len(self.q) > self.depth:
            self.q.pop(0)
        return out

    def reset(self) -> None:
        self.q.clear()


class RadixSdfStage:
    """One radix ``radix`` stage of the delay feedback chain."""

    def __init__(self, width: int, block: int, radix: int, points: int,
                 scale: bool = True):
        self.width = width
        self.block = block
        self.radix = radix
        self.points = points
        self.scale = scale
        self.sub = block // radix
        # index 0 is unused, register k has depth k * sub
        self.lines = [RadixLine(1) for _ in range(radix)]
        for k in range(1, radix):
            self.lines[k] = RadixLine(k * self.sub)
        self.count = 0

    def storage(self) -> int:
        """The number of registers of the stage."""
        return sum(k * self.sub for k in range(1, self.radix))

    def reset(self) -> None:
        for line in self.lines:
            line.reset()
        self.count = 0

    def step(self, fresh: tuple[int, int]) -> tuple[int, int]:
        """One cycle: the sample goes in, one word comes out."""
        radix = self.radix
        sub = self.sub
        phase = self.count % self.block
        quarter = phase // sub
        position = phase % sub
        self.count += 1

        value = fresh
        if self.scale:
            shift = radix.bit_length() - 1
            value = (fresh[0] >> shift, fresh[1] >> shift)

        # the values the registers hold at this cycle, before this one shifts in
        taps = [line.tap() for line in self.lines]
        zero = (0, 0)

        if quarter < radix - 1:
            # hand out the difference of this arm of the previous window
            index = (position * (quarter + 1)
                     * (self.points // self.block)) % self.points
            out = apply_twiddle(index, taps[quarter + 1][0],
                                taps[quarter + 1][1], self.width, self.points)
            # only the register which carries this quarter's sample takes one
            for k in range(1, radix):
                self.lines[k].step(value if k == radix - 1 - quarter else zero)
            return out

        # the last quarter: the registers hold the samples of this window
        operands = [taps[k] for k in range(radix - 1, 0, -1)] + [value]
        transformed = butterfly(operands, self.width)
        for k in range(1, radix):
            self.lines[k].step(transformed[k])
        return transformed[0]


def sdf_radix_stream(samples: list[tuple[int, int]], width: int, points: int,
                     radices: str | list[int] = "2", scale: bool = True,
                     cycles: int | None = None) -> list[tuple[int, int]]:
    """The output stream of the chain, one word per cycle."""
    radix_list = expand_radices(radices, points)
    block = points
    stages = []
    for radix in radix_list:
        stages.append(RadixSdfStage(width, block, radix, points, scale))
        block //= radix
    if cycles is None:
        cycles = len(samples) + 6 * points
    out = []
    for t in range(cycles):
        value = samples[t] if t < len(samples) else (0, 0)
        for stage in stages:
            value = stage.step(value)
        out.append(value)
    return out


def sdf_radix(samples: list[tuple[int, int]], width: int, points: int,
              radices: str | list[int] = "2", scale: bool = True,
              ) -> list[tuple[int, int]]:
    """The spectrum of one frame, in the natural order."""
    radix_list = expand_radices(radices, points)
    latency = points - 1
    stream = sdf_radix_stream(samples, width, points, radix_list, scale,
                              cycles=latency + 8 * points)
    result = stream[latency:latency + points]
    # the chain of the decimation in frequency produces the spectrum in the
    # mixed radix permuted order
    return [result[mixed_reverse(i, radix_list)] for i in range(points)]


def sdf_radix_storage(points: int, radices: str | list[int] = "2") -> int:
    """The registers of the chain, without building it."""
    radix_list = expand_radices(radices, points)
    block = points
    total = 0
    for radix in radix_list:
        total += block * (radix - 1) // 2
        block //= radix
    return total
