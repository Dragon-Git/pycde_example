import random
import cocotb
import cocotb.clock
import pytest
from cocotb.triggers import RisingEdge
from cocotbext.ahb import AHBBus, AHBLiteMaster
import numpy as np
from multiprocessing import shared_memory, resource_tracker


async def monitor(dut):
    while True:
        await RisingEdge(dut.hclk)
        cocotb.log.info(dut.hready.value)
        cocotb.log.info(dut.hresp.value)
        cocotb.log.info(dut.hrdata.value)

@cocotb.test()
async def random_test(dut):

    # Create a 10us period clock on port clk
    clock = cocotb.clock.Clock(dut.hclk, 10, units="us")
    cocotb.start_soon(clock.start())  # Start the clock
    cocotb.start_soon(monitor(dut)) 
    # Reset the DUT
    dut.hresetn.value = 1
    await RisingEdge(dut.hclk)
    dut.hresetn.value = 0

    ahb_lite_master = AHBLiteMaster(
        AHBBus.from_entity(dut), dut.hclk, dut.hresetn, def_val="0"
    )
    

    shm = shared_memory.SharedMemory("my_shm", create=False, size=8)
    resource_tracker.unregister(shm._name, "shared_memory")
    arr = np.ndarray(8, dtype=np.int8, buffer=shm.buf)
    print(f"Test data from shared memory: {arr}")
    shm.close()  # 仅关闭当前进程的引用，不 unlink


    # Perform the writes and reads
    value = random.randint(0, 2**32)
    resp = await ahb_lite_master.write(0, value, pip=False, verbose=True)
    resp = await ahb_lite_master.read(0, pip=False, verbose=True)
    cocotb.log.info(f"Write response: {resp}")
    assert int(resp[0]["data"], 16) == value, "Read data does not match expected value"

    value = list(range(0x0, 0x400, 4))
    resp = await ahb_lite_master.write(value, value, pip=False, verbose=True)
    resp = await ahb_lite_master.read(value, pip=False, verbose=True)
    cocotb.log.info(f"Write response: {resp}")
    assert [int(r["data"], 16) for r in resp] == value, "Read data does not match expected value"

@pytest.mark.parametrize("cnt", list(range(100)))
def test_ahb_sram_runner(cnt):
    pass

shm = shared_memory.SharedMemory("my_shm", create=False, size=8)
resource_tracker.unregister(shm._name, "shared_memory")
arr = np.ndarray(8, dtype=np.int8, buffer=shm.buf)
arr[:] = np.arange(0, 8, dtype=np.int8)
shm.close()
