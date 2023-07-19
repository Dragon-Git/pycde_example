from pycde import (System, Module, Clock, Input, Output, generator, types, dim)
from pycde.dialects import comb, hw
from pycde.types import Bits, SInt, UInt
from pycde.constructs import Mux
from pycde.signals import ArraySignal

XLEN = 32

class BRU(Module):
    rs1 = Input(SInt(XLEN))
    rs2 = Input(SInt(XLEN))
    br_type = Input(Bits(3))
    taken = Output(Bits(1))
  
    @generator
    def build(io):

        lookup = ArraySignal.create([
            io.rs1 != io.rs1,
            io.rs1 == io.rs1, # TODO:NotImplemented
            io.rs1 == io.rs1, # TODO:NotImplemented
            io.rs1 == io.rs2,
            io.rs2 != io.rs2, # TODO:NotImplemented
            io.rs2 != io.rs2, # TODO:NotImplemented
            io.rs1 != io.rs2,
            io.rs2 != io.rs2,
        ])
        io.taken = lookup[io.br_type].as_bits(1)

if __name__ == '__main__':
    mod = System([BRU],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()