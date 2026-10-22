"""Helper to build and run the cocotb tests of a test module.

The cocotb tests are started by the test function of the module (and not by a
fixture): a module scoped fixture is instantiated again for every module it is
used with, which pytest 9 does not accept.
"""

from __future__ import annotations

import glob
import os

from cocotb_tools.runner import get_runner

from .cordic_configs import CORDIC_CONFIGS
from .fft_configs import FFT_CONFIGS, TWIDDLE_TEST

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rtl_files(directory: str) -> list[str]:
    """All the generated RTL files of a design.

    Every module is emitted into its own file, so the submodules of the top
    level module have to be compiled as well.
    """
    return sorted(glob.glob(os.path.join(REPO_ROOT, directory, "*.sv")))


#: The RTL which is built and simulated for a test module:
#: test module -> (list of source files, top level module)
RTL_SPECS = {
    "pycde_example.test_ahb_ram": (rtl_files("build/ip_amba_lib/hw"), "Sram"),
    "pycde_example.test_ahb_to_ram": (rtl_files("build/ip_amba_lib/hw"), "AHBRam"),
}
for _cfg in CORDIC_CONFIGS:
    RTL_SPECS[_cfg["test_module"]] = (rtl_files(os.path.dirname(_cfg["rtl"])),
                                     _cfg["name"])
for _cfg in FFT_CONFIGS:
    RTL_SPECS[_cfg["test_module"]] = (rtl_files(os.path.dirname(_cfg["rtl"])),
                                     _cfg["name"])
RTL_SPECS[TWIDDLE_TEST["test_module"]] = (rtl_files(os.path.dirname(TWIDDLE_TEST["rtl"])),
                                          TWIDDLE_TEST["name"])


def build_dir(module_name: str) -> str:
    """The directory the simulator of a test module is built in."""
    return os.path.join(REPO_ROOT, "build", f"{module_name}__build")


def build_rtl() -> None:
    """Build the RTL of all the test modules."""
    runner = get_runner("verilator")
    for module_name, (sources, rtl_name) in RTL_SPECS.items():
        runner.build(
            sources=sources,
            hdl_toplevel=rtl_name,
            always=True,
            build_dir=build_dir(module_name),
            # the internal signals of the design are made visible to the
            # test, they are handy to debug a failure
            build_args=["--public-flat-rw"],
        )


def run_cocotb(module_name: str) -> None:
    """Run the cocotb tests of a test module."""
    if module_name not in RTL_SPECS:
        return
    rtl_name = RTL_SPECS[module_name][1]
    runner = get_runner("verilator")
    runner.test(
        hdl_toplevel=rtl_name,
        hdl_toplevel_lang="verilog",
        test_module=module_name,
        build_dir=build_dir(module_name),
        test_dir=build_dir(module_name),
        test_args=[]
    )
