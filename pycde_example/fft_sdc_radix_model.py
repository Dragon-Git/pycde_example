"""The radix R delay commutator chain.

The radix 2 commutator stage differs from the feedback one in a single thing: the
difference of the butterfly is not written back into the delay line of its stage,
it is forwarded.  The stage therefore keeps two kinds of line - the ones which
hold the samples until the butterfly can run, and the ones which delay the
results until it is their turn to leave - and a multiplexer puts them in order.
Nothing is fed back, so the chain is a pipeline of the same depth with no loop in
it.

What stays the same is the timing.  A stage of radix `R` has `R` quarters of
`sub = L/R` cycles, the sample of quarter `q` waits `(R-1-q)*sub` cycles for the
butterfly, and the result of arm `r` leaves at quarter `r` of the next window.
The number of registers is the same as the feedback stage, `L*(R-1)/2`, and the
latency is `points - 1` for every radix.

Which topology to pick is then a question of shape rather than of arithmetic: the
commutator chain has no feedback loop, so its timing is easier to close, and the
feedback one needs fewer multiplexers.
"""

from __future__ import annotations

from .fft_model import apply_twiddle
from .fft_radix_model import butterfly, expand_radices, mixed_reverse


class CommutatorLine:
    """A shift register of ``depth`` entries."""

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


class RadixSdcStage:
    """One radix ``radix`` stage of the delay commutator chain."""

    def __init__(self, width: int, block: int, radix: int, points: int,
                 scale: bool = True):
        self.width = width
        self.block = block
        self.radix = radix
        self.points = points
        self.scale = scale
        self.sub = block // radix
        # the lines which hold the samples until the butterfly can run
        self.sample_lines = [CommutatorLine(k * self.sub)
                             for k in range(1, radix)]
        # the lines which hold the results until their quarter comes
        self.result_lines = [CommutatorLine(k * self.sub)
                             for k in range(1, radix)]
        self.count = 0

    def storage(self) -> int:
        """The registers of the stage."""
        return sum(k * self.sub for k in range(1, self.radix)) * 2

    def reset(self) -> None:
        for line in self.sample_lines + self.result_lines:
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

        sample_taps = [line.tap() for line in self.sample_lines]
        result_taps = [line.tap() for line in self.result_lines]
        zero = (0, 0)

        if quarter == radix - 1:
            # the butterfly: the sample lines hold the samples of the block
            operands = [sample_taps[k - 1] for k in range(radix - 1, 0, -1)]
            operands.append(value)
            transformed = butterfly(operands, self.width)
            # the differences go into the result lines, arm r into line r - 1
            for r in range(1, radix):
                self.result_lines[r - 1].step(transformed[r])
            for line in self.sample_lines:
                line.step(zero)
            return transformed[0]

        # not the last quarter: hand out the result of one arm, rotated, and
        # push the sample into the line which holds it long enough
        out = result_taps[quarter]
        index = (position * (quarter + 1) * (self.points // self.block)) \
            % self.points
        rotated = apply_twiddle(index, out[0], out[1], self.width, self.points)
        for k in range(radix - 1):
            self.sample_lines[k].step(
                value if k == radix - 2 - quarter else zero)
        for line in self.result_lines:
            line.step(zero)
        return rotated


def sdc_radix_stream(samples: list[tuple[int, int]], width: int, points: int,
                     radices: str | list[int] = "2", scale: bool = True,
                     cycles: int | None = None) -> list[tuple[int, int]]:
    """The output stream of the chain, one word per cycle."""
    radix_list = expand_radices(radices, points)
    block = points
    stages = []
    for radix in radix_list:
        stages.append(RadixSdcStage(width, block, radix, points, scale))
        block //= radix
    if cycles is None:
        cycles = len(samples) + 8 * points
    out = []
    for t in range(cycles):
        value = samples[t] if t < len(samples) else (0, 0)
        for stage in stages:
            value = stage.step(value)
        out.append(value)
    return out


def sdc_radix(samples: list[tuple[int, int]], width: int, points: int,
              radices: str | list[int] = "2", scale: bool = True,
              ) -> list[tuple[int, int]]:
    """The spectrum of one frame, in the natural order."""
    radix_list = expand_radices(radices, points)
    latency = points - 1
    stream = sdc_radix_stream(samples, width, points, radix_list, scale,
                              cycles=latency + 8 * points)
    result = stream[latency:latency + points]
    return [result[mixed_reverse(i, radix_list)] for i in range(points)]


def sdc_radix_storage(points: int, radices: str | list[int] = "2") -> int:
    """The registers of the chain, without building it."""
    radix_list = expand_radices(radices, points)
    block = points
    total = 0
    for radix in radix_list:
        total += block * (radix - 1)
        block //= radix
    return total
