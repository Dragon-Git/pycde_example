
from pycde import (Clock, Reset, InputChannel, OutputChannel, Module, System, generator, esi)
from pycde.types import Bits, SInt, UInt  # noqa: F401

XLEN = 32
DEPTH_1 = 31
RamI32x32 = esi.DeclareRandomAccessMemory(Bits(XLEN), DEPTH_1 +1, "RamI32x32")
WriteType = RamI32x32.write.to_server_type

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
        RamI32x32.write(io.rd_write, "rd_write")
        io.rs1_read_data = RamI32x32.read(io.rs1_read_addr, "rs1_read")
        io.rs2_read_data = RamI32x32.read(io.rs2_read_addr, "rs2_read")
 
        RamI32x32.instantiate_builtin("sv_mem", [], inputs=[io.clk, io.rst])

if __name__ == '__main__':
    mod = System([Regfile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
