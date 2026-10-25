"""Unit test of the twiddle factor generator.

The generator is instantiated as a top level module, so that the twiddle
factors can be checked against the reference model without the transform.
"""

from __future__ import annotations

import cocotb
import cocotb.clock
from cocotb.triggers import RisingEdge, Timer

from .cocotb_runner import run_cocotb
from .fft_model import cordic_iterations, twiddle_cordic

WIDTH = 16
POINTS = 16
ITERATIONS = cordic_iterations(WIDTH)  # the CORDIC of the generator


def to_signed(value: int, width: int) -> int:
    """Interpret the low ``width`` bits of ``value`` as a two's complement number."""
    value &= (1 << width) - 1
    if value & (1 << (width - 1)):
        value -= 1 << width
    return value


@cocotb.test()
async def test_twiddle_cordic(dut):
    """The factors of the CORDIC are the expected ones."""
    clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    dut.rst.value = 0
    dut.out_ready.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")

    for index in range(POINTS // 2):
        dut.index.value = index
        dut.index_valid.value = 1
        # the index is registered, the factor is valid a couple of cycles later
        for _ in range(8):
            await Timer(1, units="ps")
            if int(dut.valid.value) == 1:
                break
            await RisingEdge(dut.clk)
        assert int(dut.valid.value) == 1, "the factor has to be valid"
        got = (to_signed(int(dut.re.value), WIDTH),
               to_signed(int(dut.im.value), WIDTH))
        expected = twiddle_cordic(index, WIDTH, POINTS, ITERATIONS)
        assert got == expected, f"index {index}: {got} != {expected}"
    dut.index_valid.value = 0


def test_twiddle_runner():
    """The twiddle generator is verified by the cocotb tests above."""
    run_cocotb(__name__)
