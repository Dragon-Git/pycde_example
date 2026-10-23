"""Shared cocotb test bodies for the configurable FFT.

The test modules (``test_fft_*.py``) only instantiate the tests for their
configuration, the actual test logic lives here so that all architectures are
checked in exactly the same way.
"""

from __future__ import annotations

import math
import random

import cocotb
import cocotb.clock
from cocotb.triggers import RisingEdge, Timer

from .fft_model import fft, fft_inverse, to_fixed


def to_signed(value: int, width: int) -> int:
    """Interpret the low ``width`` bits of ``value`` as a two's complement number."""
    value &= (1 << width) - 1
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


def to_bits(value: int, width: int) -> int:
    """The unsigned bit pattern of a signed value (as it is driven into the RTL)."""
    return value & ((1 << width) - 1)


def test_frames(points: int, width: int, count: int = 3) -> list[list[tuple[int, int]]]:
    """Deterministic input frames.

    The magnitude of a sample has to stay below one: the complex product of
    two samples would overflow the datapath otherwise.
    """
    rng = random.Random(0xFF7 + width * 131 + points * 17)
    frames = []

    # an impulse: the spectrum is flat
    impulse = [(0, 0)] * points
    impulse[0] = (to_fixed(0.5, width), 0)
    frames.append(impulse)

    # a tone: the spectrum has a single peak
    bin = 1
    tone = []
    for n in range(points):
        angle = 2.0 * math.pi * bin * n / points
        tone.append((to_fixed(0.5 * math.cos(angle), width),
                     to_fixed(0.5 * math.sin(angle), width)))
    frames.append(tone)

    # random noise
    for _ in range(count - 2):
        frame = []
        for _ in range(points):
            radius = rng.uniform(0.0, 0.7)
            angle = rng.uniform(0.0, 2.0 * math.pi)
            frame.append((to_fixed(radius * math.cos(angle), width),
                          to_fixed(radius * math.sin(angle), width)))
        frames.append(frame)
    return frames


async def reset(dut) -> None:
    """Apply the reset and release it.

    The reset of the generated RTL is active high ("if (rst)" in the
    always_ff block).
    """
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.out_ready.value = 1
    dut.in_real.value = 0
    dut.in_imag.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")


async def send_frame(dut, frame: list[tuple[int, int]], width: int) -> None:
    """Send one frame of samples into the DUT."""
    for (re, im) in frame:
        dut.in_real.value = to_bits(re, width)
        dut.in_imag.value = to_bits(im, width)
        dut.in_valid.value = 1
        # wait until the sample is accepted
        while True:
            await Timer(1, units="ps")
            if int(dut.in_ready.value) == 1:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
    dut.in_valid.value = 0


async def receive_frame(dut, points: int, width: int,
                        timeout: int = 10000) -> list[tuple[int, int]]:
    """Receive one frame of samples from the DUT."""
    result = []
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        if int(dut.out_valid.value) == 1 and int(dut.out_ready.value) == 1:
            result.append((to_signed(int(dut.out_real.value), width),
                           to_signed(int(dut.out_imag.value), width)))
            if len(result) == points:
                return result
    raise AssertionError("the FFT did not produce a result")


async def drive_with_backpressure(dut, frames, width: int) -> list[list[tuple[int, int]]]:
    """Stream the frames while the consumer stalls.

    The handshake is sampled just before the clock edge, which is the moment the
    design sees it: after `await RisingEdge` the signals describe the following
    cycle, so reading them there counts a sample as taken which was not, and the
    whole transaction slips by one.

    Everything is driven from a single coroutine as well: two of them would
    apply their signals in an unspecified order around the edge.
    """
    points = len(frames[0])
    samples = [s for frame in frames for s in frame]
    results = []
    current = []
    sample = 0
    stall_for = 0
    for cycle in range(6000):
        # the consumer stalls for a few cycles in the middle of a window
        if stall_for > 0:
            dut.out_ready.value = 0
            stall_for -= 1
        else:
            dut.out_ready.value = 1
        if sample < len(samples):
            re, im = samples[sample]
            dut.in_valid.value = 1
            dut.in_real.value = to_bits(re, width)
            dut.in_imag.value = to_bits(im, width)
        else:
            dut.in_valid.value = 0
            dut.in_real.value = 0
            dut.in_imag.value = 0
        # let the combinational logic settle for this cycle, then read the
        # handshake the way the design will see it at the edge
        await Timer(1, units="ps")
        in_ready = int(dut.in_ready.value)
        in_valid = int(dut.in_valid.value)
        out_valid = int(dut.out_valid.value)
        out_ready = int(dut.out_ready.value)
        if in_valid == 1 and in_ready == 1:
            sample += 1
        if out_valid == 1 and out_ready == 1:
            current.append((to_signed(int(dut.out_real.value), width),
                            to_signed(int(dut.out_imag.value), width)))
        await RisingEdge(dut.clk)
        if len(current) == points:
            results.append(current)
            current = []
            if len(results) >= len(frames):
                dut.out_ready.value = 1
                dut.in_valid.value = 0
                return results
        if cycle % 7 == 3:
            stall_for = 4
    raise AssertionError("the FFT did not produce a result under backpressure,"
                         f" collected {len(results)} of {len(frames)} spectra")


def mixed_radix_reference(params, width, points, dit, scaled, inverse,
                          twiddle_mode):
    """The reference model of a configuration.

    A radix larger than 2 is modelled by the mixed radix model, which is bit
    exact with the radix 2 one when every radix is 2 - so the radices only pick
    the model, they do not change the arithmetic.
    """
    from .fft_radix_model import fft_mixed, parse_radices

    radices = params.get("radices", "2")
    if not any(radix != 2 for radix in parse_radices(radices)):
        if inverse:
            return lambda frame: fft_inverse(frame, width, points, dit=dit,
                                             scale=scaled)
        return lambda frame: fft(frame, width, points, dit=dit, scale=scaled,
                                 twiddle_mode=twiddle_mode)
    if inverse:
        raise NotImplementedError("the inverse transform is radix 2 only")
    # the mixed radix model takes the radices instead of a twiddle mode: the
    # table it uses is the one of the whole transform
    return lambda frame: fft_mixed(frame, width, points, radices, dit=dit,
                                   scale=scaled)


def make_streaming_fft_tests(**params):
    """Create the cocotb tests of a streaming FFT configuration.

    A streaming architecture must be fed without gaps: the delay lines hold the
    data of the previous frame while the current one is processed, so the
    frames follow each other back to back and the samples are accepted on every
    cycle.
    """
    width = params["width"]
    points = params["points"]
    dit = params.get("ordering", "dit") == "dit"
    inverse = params.get("inverse", False)
    twiddle_mode = params.get("twiddle_mode", "rom")
    # the stages of the datapath are scaled unless the configuration says
    # otherwise; the reference model has to be told the same
    scaled = params.get("scaling", "stage") == "stage"
    # The reference is the radix 2 model unless a radix is larger than 2, in
    # which case the mixed radix one is used; the two agree bit for bit when
    # every radix is 2.  Both apply the trivial twiddle factors exactly, the
    # way the RTL applies them.
    reference = mixed_radix_reference(params, width, points, dit, scaled,
                                      inverse, twiddle_mode)

    async def stream_frames(dut, frames):
        """Send the frames back to back.

        A sample is held until the interface accepts it: the pipeline freezes
        while the consumer of the spectrum is not ready, so `in_ready` can be
        low in the middle of a frame.
        """
        for frame in frames:
            for (re, im) in frame:
                # out_ready belongs to the consumer: the tests which stall it
                # drive it themselves
                dut.in_real.value = to_bits(re, width)
                dut.in_imag.value = to_bits(im, width)
                dut.in_valid.value = 1
                while True:
                    await Timer(1, units="ps")
                    if int(dut.in_ready.value) == 1:
                        break
                    await RisingEdge(dut.clk)
                await RisingEdge(dut.clk)
                await Timer(1, units="ps")
        # The chain keeps the last sample if it stays valid, and it would then
        # be received again as the beginning of the next frame.
        dut.in_valid.value = 0
        dut.in_real.value = 0
        dut.in_imag.value = 0

    async def collect_spectra(dut, count):
        """Collect `count` spectra, each of `points` samples.

        The receiver drops the spectra which were produced while the chain
        was still being filled, so the first spectrum it returns is the one of
        the first frame which was sent.
        """
        spectra = []
        current = []
        for _ in range(20000):
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
            if int(dut.out_valid.value) == 1 and int(dut.out_ready.value) == 1:
                current.append((to_signed(int(dut.out_real.value), width),
                                to_signed(int(dut.out_imag.value), width)))
                if len(current) == points:
                    spectra.append(current)
                    current = []
                    if len(spectra) == count:
                        return spectra
        raise AssertionError("the FFT did not produce enough results")

    @cocotb.test()
    async def test_fft(dut):
        """Compare the RTL against the bit exact reference model."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        frames = test_frames(points, width)
        # the collector runs while the frames are streamed: the spectra appear
        # after the latency of the chain
        collector = cocotb.start_soon(collect_spectra(dut, len(frames)))
        await stream_frames(dut, frames)
        results = await collector

        for frame, got in zip(frames, results):
            expected = reference(frame)
            assert got == expected, f"got {got}, expected {expected}"

    @cocotb.test()
    async def test_fft_handshake(dut):
        """Check that the interface accepts a sample on every cycle."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        # the chain is free running: it is always ready
        assert int(dut.in_ready.value) == 1, "the FFT has to accept a sample"

        frames = test_frames(points, width)[:2]
        collector = cocotb.start_soon(collect_spectra(dut, len(frames)))
        await stream_frames(dut, frames)
        results = await collector

        for frame, got in zip(frames, results):
            expected = reference(frame)
            assert got == expected, f"got {got}, expected {expected}"

    @cocotb.test()
    async def test_fft_backpressure(dut):
        """A stalled consumer must not lose a sample."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        frames = test_frames(points, width)[:1]
        # one coroutine drives the input and the consumer together: two of them
        # would race around the clock edge
        results = await drive_with_backpressure(dut, frames, width)

        for frame, got in zip(frames, results):
            expected = reference(frame)
            assert got == expected, f"got {got}, expected {expected}"

    return test_fft, test_fft_handshake, test_fft_backpressure



async def stream_frames(dut, frames, width):
    """Send the frames back to back, holding a sample until it is taken."""
    for frame in frames:
        for (re, im) in frame:
            dut.in_real.value = to_bits(re, width)
            dut.in_imag.value = to_bits(im, width)
            dut.in_valid.value = 1
            while True:
                await Timer(1, units="ps")
                if int(dut.in_ready.value) == 1:
                    break
                await RisingEdge(dut.clk)
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
    dut.in_valid.value = 0
    dut.in_real.value = 0
    dut.in_imag.value = 0


async def collect_spectra(dut, count, width, points):
    """Collect `count` spectra, each of `points` samples."""
    spectra = []
    current = []
    for _ in range(20000):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        if int(dut.out_valid.value) == 1 and int(dut.out_ready.value) == 1:
            current.append((to_signed(int(dut.out_real.value), width),
                            to_signed(int(dut.out_imag.value), width)))
            if len(current) == points:
                spectra.append(current)
                current = []
                if len(spectra) == count:
                    return spectra
    raise AssertionError("the FFT did not produce enough results")


def make_mdc_tests(**params):
    """Create the cocotb tests of a multi path delay commutator.

    The chains of the architecture are commutator chains, which hand a spectrum
    over one window late: the first frame only fills them and the spectrum of a
    frame leaves the architecture after the next frame was fed.  The tests
    therefore stream the frames and compare every spectrum with the frame it
    belongs to, one frame behind.
    """
    width = params["width"]
    points = params["points"]
    dit = params.get("ordering", "dit") == "dit"
    twiddle_mode = params.get("twiddle_mode", "rom")
    scaled = params.get("scaling", "stage") == "stage"

    def reference(frame):
        """The expected result of the transform."""
        return fft(frame, width, points, dit=dit, scale=scaled,
                   twiddle_mode=twiddle_mode)

    @cocotb.test()
    async def test_fft(dut):
        """Compare the RTL against the bit exact reference model."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        frames = test_frames(points, width)
        collector = cocotb.start_soon(
            collect_spectra(dut, len(frames) - 1, width, points))
        await stream_frames(dut, frames, width)
        results = await collector

        for frame, got in zip(frames, results):
            expected = reference(frame)
            assert got == expected, f"got {got}, expected {expected}"

    @cocotb.test()
    async def test_fft_handshake(dut):
        """Check the ready/valid behaviour of the FFT."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        assert int(dut.in_ready.value) == 1, "the FFT has to accept a frame"
        assert int(dut.out_valid.value) == 0, "there is no result yet"

        frames = test_frames(points, width)[:2]
        collector = cocotb.start_soon(collect_spectra(dut, 1, width, points))
        await stream_frames(dut, frames, width)
        results = await collector

        expected = reference(frames[0])
        assert results[0] == expected, f"got {results[0]}, expected {expected}"

    return test_fft, test_fft_handshake


def make_fft_tests(**params):
    """Create the cocotb tests of a single FFT configuration."""
    width = params["width"]
    points = params["points"]
    dit = params.get("ordering", "dit") == "dit"
    inverse = params.get("inverse", False)
    twiddle_mode = params.get("twiddle_mode", "rom")
    scaled = params.get("scaling", "stage") == "stage"

    # the reference of the configuration, radix 2 or mixed radix
    reference = mixed_radix_reference(params, width, points, dit, scaled,
                                      inverse, twiddle_mode)

    @cocotb.test()
    async def test_fft(dut):
        """Compare the RTL against the bit exact reference model."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        for frame in test_frames(points, width):
            await send_frame(dut, frame, width)
            got = await receive_frame(dut, points, width)
            expected = reference(frame)
            assert got == expected, f"got {got}, expected {expected}"

    @cocotb.test()
    async def test_fft_handshake(dut):
        """Check the ready/valid behaviour of the FFT."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        # the module is ready for a new frame
        assert int(dut.in_ready.value) == 1, "the FFT has to accept a frame"
        assert int(dut.out_valid.value) == 0, "there is no result yet"

        frame = test_frames(points, width)[0]
        await send_frame(dut, frame, width)
        got = await receive_frame(dut, points, width)
        expected = reference(frame)
        assert got == expected, f"got {got}, expected {expected}"
        # the module is ready for the next frame again
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        assert int(dut.in_ready.value) == 1, "the FFT has to accept a frame"

    return test_fft, test_fft_handshake
