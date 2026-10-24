"""Temporary trace of the two point memory based FFT (debug branch only)."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from pycde_example.cocotb_runner import run_cocotb
from pycde_example.fft_tb import to_bits

WIDTH = 16
FRAME = [(128, 0), (0, 0)]


def _read(dut, path):
    """Read a signal, spelled as a hierarchy path, or report that it is gone."""
    value = dut
    for part in path.split("."):
        try:
            value = getattr(value, part)
        except AttributeError:
            return "?"
    try:
        return int(value.value)
    except Exception:  # noqa: BLE001 - the trace must not abort on one signal
        return "?"


def show(dut, tag):
    """Print the state of the design as the next edge will see it."""
    fields = [
        "phase", "in_count", "out_count", "pass_count", "butterfly_count",
        "group_count", "addr", "twiddle_index", "in_ready", "out_valid",
        "twiddle.re", "twiddle.im",
        "memory.mem_re_0", "memory.mem_im_0",
        "memory.mem_re_1", "memory.mem_im_1",
        "memory.r0_addr", "memory.r1_addr", "memory.r2_addr",
        "out_real", "out_imag",
    ]
    print(tag, " ".join(f"{field}={_read(dut, field)}" for field in fields))


@cocotb.test()
async def trace(dut):
    """Run one frame through the design and dump every cycle."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())
    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.out_ready.value = 1
    dut.in_real.value = 0
    dut.in_imag.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    show(dut, "reset")

    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    show(dut, "released")

    for index, (re, im) in enumerate(FRAME):
        dut.in_real.value = to_bits(re, WIDTH)
        dut.in_imag.value = to_bits(im, WIDTH)
        dut.in_valid.value = 1
        await Timer(1, units="ps")
        show(dut, f"drive{index}")
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        show(dut, f"accept{index}")
    dut.in_valid.value = 0

    for cycle in range(12):
        show(dut, f"cycle{cycle}")
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")


def test_trace():
    """Run the cocotb test above."""
    run_cocotb(__name__)
