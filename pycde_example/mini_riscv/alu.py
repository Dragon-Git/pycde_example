from pycde import (System, Module, Clock, Input, Output, generator, types)  # noqa: F401
from pycde.dialects import comb, hw  # noqa: F401
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import Mux

from .const import XLEN

class ALU(Module):
    A = Input(SInt(XLEN))
    B = Input(SInt(XLEN))
    alu_op = Input(Bits(4))
    out = Output(SInt(XLEN))
    sum = Output(SInt(XLEN))
  
    @generator
    def build(io):

        shamt = io.B.as_bits()

        io.out = Mux(io.alu_op, *[
            (io.A + io.B).as_sint(XLEN),
            (io.A - io.B).as_sint(XLEN),
            (io.A.as_bits() & io.B.as_bits()).as_sint(XLEN),
            (io.A.as_bits() | io.B.as_bits()).as_sint(XLEN),
            (io.A.as_bits() ^ io.B.as_bits()).as_sint(XLEN),
            (io.A < io.B).as_sint().as_sint(XLEN),
            comb.ShlOp(io.A.as_bits(), shamt).as_sint(XLEN),
            (io.A.as_uint() < io.B.as_uint()).as_sint().as_sint(XLEN),
            comb.ShrUOp(io.A.as_bits(), shamt).as_sint(XLEN),
            comb.ShrSOp(io.A.as_bits(), shamt).as_sint(XLEN),
            io.A,
            io.B,
            io.B,
            io.B,
            io.B,
            io.B,
        ])
        io.sum = Mux(io.alu_op[0], io.A + io.B, io.A - io.B).as_sint(XLEN)

if __name__ == '__main__':
    mod = System([ALU],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()