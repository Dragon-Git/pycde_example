from pycde import (System, Module, Input, Output, generator)
from pycde.types import Bits, SInt
from pycde.constructs import Mux

from .const import XLEN

class BRU(Module):
    rs1 = Input(SInt(XLEN))
    rs2 = Input(SInt(XLEN))
    br_type = Input(Bits(3))
    taken = Output(Bits(1))
  
    @generator
    def build(io):

        io.taken = Mux(io.br_type, *[
            io.rs1 != io.rs1,
            io.rs1.as_uint() < io.rs2.as_uint(),
            io.rs1 < io.rs2,
            io.rs1 == io.rs2,
            io.rs1.as_uint() >= io.rs2.as_uint(),
            io.rs1 >= io.rs2,
            io.rs1 != io.rs2,
            io.rs1 != io.rs1,
        ]).as_bits(1)

if __name__ == '__main__':
    mod = System([BRU],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()