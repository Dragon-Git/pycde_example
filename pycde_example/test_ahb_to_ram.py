import cocotb
import cocotb.clock
from cocotb.triggers import RisingEdge
from cocotb.runner import get_runner
from cocotbext.ahb import AHBBus, AHBLiteMaster
import sys


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
    dut.SRAMRDATA.value = 0xdeadbeef

    ahb_lite_master = AHBLiteMaster(
        AHBBus.from_entity(dut), dut.hclk, dut.hresetn, def_val="0"
    )

    # Perform the writes and reads
    resp = await ahb_lite_master.write(0, 1, 4, pip=False, verbose=True)
    resp = await ahb_lite_master.read(0, 1, pip=False, verbose=True)
    cocotb.log.info(f"Write response: {resp}")
    assert resp[0]["data"] == "0xdeadbeef", "Read data does not match expected value"

def test_ahb_sram_runner():

    sys.path.append(__file__.replace("test_ahb_to_ram.py", ""))
    runner = get_runner("verilator")
    runner.build(
        sources=[__file__.replace("pycde_example/test_ahb_to_ram.py", "build/ahb_to_ram/hw/AHBRam.sv")],
        hdl_toplevel="AHBRam",
        always=True,
        build_args=[],
    )
    runner.test(
        hdl_toplevel="AHBRam", test_module="test_ahb_to_ram", test_args=[]
    )


if __name__ == "__main__":
    test_ahb_sram_runner()