import sys
import pytest
from cocotb_tools.runner import get_runner
from multiprocessing import shared_memory, resource_tracker

def pytest_sessionstart(session):
    if hasattr(session.config, "workerinput"):  # 仅在主进程执行
        return
    shm = shared_memory.SharedMemory("my_shm", create=True, size=8)
    resource_tracker.unregister(shm._name, "shared_memory")
    shm.close()

    sys.path.append(__file__.replace("conftest.py", ""))
    runner = get_runner("verilator")
    rtl_names = {"pycde_example.test_ahb_ram": "Sram", "pycde_example.test_ahb_to_ram": "AHBRam"}
    for module_name, rtl_name in rtl_names.items():
        runner.build(
            sources=[__file__.replace("pycde_example/conftest.py", f"build/ip_amba_lib/hw/{rtl_name}.sv")],
            hdl_toplevel=rtl_name,
            always=True,
            build_dir=f"build/{module_name}__build",
            build_args=[],
        )

@pytest.fixture(scope="module", autouse=True)
def setup(request):
    rtl_names = {"pycde_example.test_ahb_ram": "Sram", "pycde_example.test_ahb_to_ram": "AHBRam"}
    runner = get_runner("verilator")
    runner.test(
        hdl_toplevel=rtl_names[request.module.__name__], 
        hdl_toplevel_lang="verilog",
        test_module=request.module.__name__, 
        build_dir=f"build/{request.module.__name__}__build",
        test_dir=f"build/{request.module.__name__}__build",
        test_args=[]
    )


def pytest_sessionfinish(session, exitstatus):
    if not hasattr(session.config, "workerinput"):  # 仅在主进程执行
        shm = shared_memory.SharedMemory("my_shm", create=False)
        shm.close()
        shm.unlink()
