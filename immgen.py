from pycde import (System, Module, Clock, Input, Output, generator, types, dim)
from pycde.dialects import comb, hw
from pycde.types import Bits, SInt, UInt
from pycde.constructs import Mux
from pycde.dialects import hw
from pycde.signals import ArraySignal

XLEN = 32

class Immgen(Module):
    insn = Input(Bits(XLEN))
    sel = Input(Bits(3))
    out = Output(SInt(XLEN))
  
    @generator
    def build(io):

        lookup = ArraySignal.create([
            io.insn.as_sint(XLEN), # TODO: cut and extension 
            io.insn.as_sint(XLEN),
            io.insn.as_sint(XLEN),
            io.insn.as_sint(XLEN),
            io.insn.as_sint(XLEN),
            io.insn.as_sint(XLEN),
            SInt(XLEN)(-2),
            SInt(XLEN)(-2),
        ])
        io.out = lookup[io.sel]

if __name__ == '__main__':
    mod = System([Immgen],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
    