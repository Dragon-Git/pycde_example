import os
import sys
from multiprocessing import resource_tracker, shared_memory

import pytest
from cocotb_tools.runner import get_runner

from .cordic_configs import CORDIC_CONFIGS

#: The RTL which is built and simulated for a test module:
#: test module -> (source file, top level module)
RTL_SPECS = {
    "pycde_example.test_ahb_ram": ("build/ip_amba_lib/hw/Sram.sv", "Sram"),
    "pycde_example.test_ahb_to_ram": ("build/ip_amba_lib/hw/AHBRam.sv", "AHBRam"),
}
for _cfg in CORDIC_CONFIGS:
    RTL_SPECS[_cfg["test_module"]] = ("build/ip_cordic_lib/hw/Cordic.sv", _cfg["name"])

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rtl_path(source: str) -> str:
    """The absolute path of a generated RTL file."""
    return os.path.join(REPO_ROOT, source)


def build_dir(module_name: str) -> str:
    """The directory the simulator of a test module is built in."""
    return os.path.join(REPO_ROOT, "build", f"{module_name}__build")


def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):  # 仅在主进程执行
        return
    shm = shared_memory.SharedMemory("my_shm", create=True, size=8)
    resource_tracker.unregister(shm._name, "shared_memory")
    shm.close()

    sys.path.append(__file__.replace("conftest.py", ""))
    runner = get_runner("verilator")
    for module_name, (source, rtl_name) in RTL_SPECS.items():
        runner.build(
            sources=[rtl_path(source)],
            hdl_toplevel=rtl_name,
            always=True,
            build_dir=build_dir(module_name),
            build_args=[],
        )

@pytest.fixture(scope="module", autouse=True)
def setup(request):
    module_name = request.module.__name__
    if module_name not in RTL_SPECS:
        # not a cocotb test module (the pure python unit tests for example)
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

def pytest_sessionfinish(session, exitstatus):
    if not hasattr(session.config, "workerinput"):  # 仅在主进程执行
        shm = shared_memory.SharedMemory("my_shm", create=False)
        shm.close()
        shm.unlink()
