
from pycde import (AppID, Clock, Reset, InputChannel, OutputChannel, Module, System, generator, esi)
from pycde.types import Bits, SInt, UInt  # noqa: F401

from .const import XLEN
DEPTH_1 = 31
RamI32x32 = esi.DeclareRandomAccessMemory(Bits(XLEN), DEPTH_1 +1, "RamI32x32")
WriteType = RamI32x32.write.type.req

class Regfile(Module):
    clk = Clock()
    rst = Reset()
    rs1_read_addr = InputChannel(Bits(DEPTH_1.bit_length()))
    rs1_read_data = OutputChannel(Bits(XLEN))
    rs2_read_addr = InputChannel(Bits(DEPTH_1.bit_length()))
    rs2_read_data = OutputChannel(Bits(XLEN))
    rd_write = InputChannel(WriteType)

    @generator
    def construct(io):
        write_bundle = RamI32x32.write(appid=AppID("rd_writer"))
        write_bundle.unpack(req=io.rd_write)
        read_bundle = RamI32x32.read(AppID("rs1_read"))
        bundled_channels = read_bundle.unpack(address=io.rs1_read_addr)
        io.rs1_read_data = bundled_channels["data"]
        read_bundle = RamI32x32.read(AppID("rs2_read"))
        bundled_channels = read_bundle.unpack(address=io.rs2_read_addr)
        io.rs2_read_data = bundled_channels["data"]
 
        RamI32x32.instantiate_builtin(appid=AppID("mem"), builtin="sv_mem", result_types=[], inputs=[io.clk, io.rst])

if __name__ == '__main__':
    mod = System([Regfile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
