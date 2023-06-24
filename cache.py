
from pycde import (Clock, Input, Module, System, generator, types)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import Wire
from pycde import esi

XLEN = 32

RamI32x32 = esi.DeclareRandomAccessMemory(types.i32, 32, "RamI32x32")
WriteType = RamI32x32.write.to_server_type

@esi.ServiceDecl
class Cache_io:
    write = esi.FromServer(WriteType)
    read = esi.ToFromServer(to_server_type=types.i32, to_client_type=types.i5)

class Cache(Module):
    clk = Clock()
    rst = Input(types.i1)

    @generator
    def construct(io):
        RamI32x32.write(Cache_io.write("write"))
        read_address = Wire(RamI32x32.read.to_server_type)
        read_data = RamI32x32.read(read_address)
        read_address.assign(Cache_io.read(read_data, "read"))

        RamI32x32.instantiate_builtin("sv_mem", [], inputs=[io.clk, io.rst])

if __name__ == '__main__':
    mod = System([Cache],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
