from pycde import (System, Module, Clock, Input, Output, generator, types)  # noqa: F401
from pycde.dialects import comb, hw  # noqa: F401
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import Mux  # noqa: F401
from pycde.signals import ArraySignal

XLEN = 32

class Immgen(Module):
    insn = Input(Bits(XLEN))
    sel = Input(Bits(3))
    out = Output(SInt(XLEN))
  
    @generator
    def build(io):

        lookup = ArraySignal.create([
            (io.insn[20:].as_sint().as_sint(XLEN).as_bits() & Bits(XLEN)(-2)).as_sint(),
            io.insn[20:].as_sint().as_sint(XLEN), 
            comb.ConcatOp(io.insn[25:], io.insn[7:12]).as_sint().as_sint(XLEN),
            comb.ConcatOp(io.insn[12:], Bits(12)(0)).as_sint().as_sint(XLEN),
            comb.ConcatOp(io.insn[31], io.insn[12:20], io.insn[20], io.insn[25:31],
                           io.insn[21:25], Bits(1)(0)).as_sint().as_sint(XLEN),
            comb.ConcatOp(io.insn[31], io.insn[7], io.insn[25:31], io.insn[8:12]
                          ).as_sint().as_sint(XLEN),
            io.insn[15:20].as_sint().as_sint(XLEN),
            (io.insn[20:].as_sint().as_sint(XLEN).as_bits() & Bits(XLEN)(-2)).as_sint(),
        ])
        io.out = lookup[io.sel]

if __name__ == '__main__':
    mod = System([Immgen],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
    