"""Drive a radix chain and watch its control registers.

The regular tests say only that no result came out, which does not say where.  This
runs the design of a failing configuration and prints the control registers every
few cycles, so a chain which never drains can be told apart from one whose data
path is wrong.

Run it with `python -m pycde_example.radix_probe`.  It needs the generated RTL, so
it only works where pycde is installed.
"""
from __future__ import annotations

import cocotb
from cocotb.runner import get_runner
from cocotb.triggers import RisingEdge, Timer

from .cocotb_runner import RTL_SPECS, build_dir, rtl_files  # noqa: F401

# the configuration to look at
CONFIG_MODULE = "pycde_example.test_fft_pipelined_sdf_dif_r4_w16_p16"
POINTS = 16


@cocotb.test()
async def test_probe(dut):
    """Watch the control of a radix chain while one frame goes through it."""
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

    fed = 0
    for n in range(POINTS):
        dut.in_real.value = 1000 + 100 * n
        dut.in_imag.value = 0
        dut.in_valid.value = 1
        while True:
            await Timer(1, units="ps")
            if int(dut.in_ready.value) == 1:
                break
            await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        fed += 1
    dut.in_valid.value = 0
    print(f"fed {fed} samples")

    for cycle in range(140):
        await RisingEdge(dut.clk)
        await Timer(1, units="ps")
        phase = int(dut.phase.value)
        adv = int(dut.adv.value)
        wc = int(dut.write_count.value)
        ov = int(dut.out_valid.value)
        if cycle % 6 == 0 or ov:
            print(f"cycle={cycle:3d} phase={phase} adv={adv} wc={wc} ov={ov} "
                  f"out={int(dut.out_real.value)}")


def main() -> None:
    """Build the design of the configuration and run the probe against it."""
    sources, rtl_name = RTL_SPECS[CONFIG_MODULE]
    directory = build_dir(CONFIG_MODULE)
    runner = get_runner("verilator")
    runner.build(
        sources=sources,
        hdl_toplevel=rtl_name,
        always=False,
        build_dir=directory,
        build_args=["--public-flat-rw"],
        waves=True,
    )
    runner.test(
        hdl_toplevel=rtl_name,
        hdl_toplevel_lang="verilog",
        test_module="pycde_example.radix_probe",
        build_dir=directory,
        test_dir=None,
        waves=True,
    )


if __name__ == "__main__":
    main()
