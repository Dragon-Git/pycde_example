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


def make_fft_tests(**params):
    """Create the cocotb tests of a single FFT configuration."""
    width = params["width"]
    points = params["points"]
    dit = params.get("ordering", "dit") == "dit"
    inverse = params.get("inverse", False)
    twiddle_mode = params.get("twiddle_mode", "rom")

    def reference(frame):
        """The expected result of the transform."""
        if inverse:
            return fft_inverse(frame, width, points, dit=dit, scale=True)
        return fft(frame, width, points, dit=dit, scale=True,
                   twiddle_mode=twiddle_mode)

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
