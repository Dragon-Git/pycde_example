
from pycde import (Clock, Input, Module, System, generator, types)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import Wire
from pycde import esi

XLEN = 32

RamI32x32 = esi.DeclareRandomAccessMemory(types.i32, 32, "RamI32x32")
WriteType = RamI32x32.write.to_server_type

@esi.ServiceDecl
class Regfile_io:
    write = esi.FromServer(WriteType)
    read = esi.ToFromServer(to_server_type=types.i32, to_client_type=types.i5)

class Regfile(Module):
    clk = Clock()
    rst = Input(types.i1)

    @generator
    def construct(io):
        RamI32x32.write(Regfile_io.write("write"))

        rs1_read_address = Wire(RamI32x32.read.to_server_type)
        rs1_read_data = RamI32x32.read(rs1_read_address, "rs1_read")
        rs1_read_address.assign(Regfile_io.read(rs1_read_data, "rs1_read"))

	rs2_read_address = Wire(RamI32x32.read.to_server_type)                                                                     
        rs2_read_data = RamI32x32.read(rs2_read_address, "rs2_read")                                                                               
        rs2_read_address.assign(Regfile_io.read(rs2_read_data, "rs2_read"))
 
        RamI32x32.instantiate_builtin("sv_mem", [], inputs=[io.clk, io.rst])

if __name__ == '__main__':
    mod = System([Regfile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
