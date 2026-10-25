"""A diagnostic of the radix chain, run as a cocotb test.

It is not part of the regular suite: it exists to look at the internal signals of a
chain which produces nothing, because a failure of that shape says little about
where it happens.  Run it with `pytest` on the configuration which fails, or by
calling `run_cocotb` on it directly.
"""
from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from .cocotb_runner import run_cocotb

params = {"width": 16, "points": 16, "ordering": "dif",
          "eval_mode": "pipelined", "pipeline_style": "sdf",
          "stages": 1, "radices": "4", "twiddle_mode": "rom",
          "data_format": "fixed", "scaling": "stage", "inverse": False,
          "parallel": 1}


@cocotb.test()
async def test_probe(dut):
    """Look at the control registers of a chain which produces nothing."""
    clock = cocotb.clock.Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    dut.in_valid.value = 0
    dut.out_ready.value = 1
    dut.in_real.value = 0
    dut.in_imag.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, units="ps")
    dut.rst.value = 0

    # feed a frame
    for n in range(params["points"]):
        dut.in_real.value = 1000 + n
        dut.in_imag.value = 0
        dut.in_valid.value = 1
        while True:
            await Timer(1, units="ps")
            if int(dut.in_ready.value) == 1:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
    dut.in_valid.value = 0

    # watch the control for a while
    for cycle in range(160):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        phase = int(dut.phase.value)
        adv = int(dut.adv.value)
        write_count = int(dut.write_count.value)
        out_valid = int(dut.out_valid.value)
        if cycle % 10 == 0 or out_valid:
            print(f"cycle={cycle} phase={phase} adv={adv} "
                  f"wc={write_count} out_valid={out_valid} "
                  f"out_real={int(dut.out_real.value)}")


if __name__ == "__main__":
    run_cocotb(__name__)
