"""Shared cocotb test bodies for the configurable CORDIC.

The test modules (``test_cordic_<arch>_<mode>.py``) only instantiate the
tests for their configuration, the actual test logic lives here so that all
architectures are checked in exactly the same way.
"""

from __future__ import annotations

import math
import random

import cocotb
import cocotb.clock
from cocotb.triggers import RisingEdge, Timer

from .cordic_model import VECTORING, atan_table, cordic


def to_signed(value: int, width: int) -> int:
    """Interpret the low ``width`` bits of ``value`` as a two's complement number."""
    value &= (1 << width) - 1
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


def to_bits(value: int, width: int) -> int:
    """The unsigned bit pattern of a signed value (as it is driven into the RTL)."""
    return value & ((1 << width) - 1)


def max_angle(width: int, iterations: int) -> int:
    """The largest angle a CORDIC is able to process (sum of all atan(2**-i))."""
    return sum(atan_table(width, iterations))


def test_vectors(width: int, iterations: int, mode: str,
                 count: int = 12) -> list[tuple[int, int, int]]:
    """Deterministic test vectors which stay inside the dynamic range.

    The magnitude of the input is limited so that the (uncompensated) gain of
    the CORDIC cannot overflow the datapath and the angles are limited to the
    rotation range of the CORDIC.
    """
    rng = random.Random(0xC0D1C + width * 131 + iterations * 17 + len(mode))
    limit = 1 << (width - 4)
    angle_limit = int(0.9 * max_angle(width, iterations))

    candidates = [
        (0, 0, 0),
        (limit, 0, 0),
        (0, limit, 0),
        (0, -limit, 0),
        (limit, limit, 0),
        (-limit, limit, 0),
        (limit, 0, angle_limit),
        (limit, 0, -angle_limit),
        (-limit, 0, angle_limit),
    ]
    while len(candidates) < count:
        candidates.append((rng.randint(-limit, limit), rng.randint(-limit, limit),
                           rng.randint(-angle_limit, angle_limit)))

    vectors = []
    for (x, y, z) in candidates:
        if mode == VECTORING and abs(math.atan2(y, x)) > 1.6:
            # the vectoring mode rotates the vector onto the x axis, so the
            # angle of the input vector has to be within the rotation range
            continue
        vectors.append((x, y, z))
    return vectors


def read_outputs(dut, width: int) -> tuple[int, int, int]:
    """Read the result of the DUT."""
    return (to_signed(int(dut.x_o.value), width),
            to_signed(int(dut.y_o.value), width),
            to_signed(int(dut.z_o.value), width))


async def reset(dut) -> None:
    """Apply the reset and release it."""
    dut.rst.value = 0
    dut.in_valid.value = 0
    dut.out_ready.value = 1
    dut.x_i.value = 0
    dut.y_i.value = 0
    dut.z_i.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")


async def wait_ready(dut, timeout: int = 1000) -> None:
    """Wait until the DUT accepts the input."""
    for _ in range(timeout):
        await Timer(1, units="ps")
        if int(dut.in_ready.value) == 1:
            return
        await RisingEdge(dut.clk)
    raise AssertionError("the CORDIC did not accept the input")


async def wait_valid(dut, timeout: int = 1000) -> None:
    """Wait until the DUT presents a result."""
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        if int(dut.out_valid.value) == 1:
            return
    raise AssertionError("the CORDIC did not produce a result")


def make_cordic_tests(arch: str, mode: str, width: int, iterations: int):
    """Create the cocotb tests of a single CORDIC configuration."""

    @cocotb.test()
    async def test_cordic(dut):
        """Compare the RTL against the bit exact reference model."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        for (x, y, z) in test_vectors(width, iterations, mode):
            expected = cordic(x, y, z, width, iterations, mode)
            dut.x_i.value = to_bits(x, width)
            dut.y_i.value = to_bits(y, width)
            dut.z_i.value = to_bits(z, width)

            if arch == "comb":
                # the fully combinational CORDIC produces its result in the
                # very same cycle
                dut.in_valid.value = 1
                await Timer(1, units="ps")
                assert int(dut.out_valid.value) == 1, \
                    "the combinational CORDIC must be valid"
                got = read_outputs(dut, width)
                assert got == expected, f"got {got}, expected {expected}"
                dut.in_valid.value = 0
                await Timer(1, units="ps")
                continue

            dut.in_valid.value = 1
            await wait_ready(dut)
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
            dut.in_valid.value = 0
            await wait_valid(dut)
            got = read_outputs(dut, width)
            assert got == expected, f"got {got}, expected {expected}"

    @cocotb.test()
    async def test_cordic_handshake(dut):
        """Check the ready/valid behaviour of the CORDIC."""
        clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
        cocotb.start_soon(clock.start())
        await reset(dut)

        if arch == "comb":
            # the combinational CORDIC is always ready and passes the valid
            # through combinationally
            assert int(dut.in_ready.value) == 1, "the combinational CORDIC is always ready"
            dut.in_valid.value = 0
            await Timer(1, units="ps")
            assert int(dut.out_valid.value) == 0, "no valid input, no valid output"
            dut.in_valid.value = 1
            await Timer(1, units="ps")
            assert int(dut.out_valid.value) == 1, "the valid is passed through"
            dut.in_valid.value = 0
            await Timer(1, units="ps")
            assert int(dut.out_valid.value) == 0, "the valid is passed through"
            return

        # The sequential architectures must hold their result until the
        # consumer accepts it.
        (x, y, z) = test_vectors(width, iterations, mode)[0]
        expected = cordic(x, y, z, width, iterations, mode)
        dut.x_i.value = to_bits(x, width)
        dut.y_i.value = to_bits(y, width)
        dut.z_i.value = to_bits(z, width)
        dut.out_ready.value = 0
        dut.in_valid.value = 1
        await wait_ready(dut)
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        dut.in_valid.value = 0
        await wait_valid(dut)
        got = read_outputs(dut, width)
        assert got == expected, f"got {got}, expected {expected}"

        # the result must be stable as long as it is not accepted
        for _ in range(5):
            await RisingEdge(dut.clk)
            await Timer(1, units="ps")
            assert int(dut.out_valid.value) == 1, "the result must be held"
            assert read_outputs(dut, width) == expected, "the result must be held"

        # accepting the result releases the CORDIC
        dut.out_ready.value = 1
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        assert int(dut.out_valid.value) == 0, "the result must be consumed"

    return test_cordic, test_cordic_handshake
