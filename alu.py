from pycde import (System, Module, Clock, Input, Output, generator, types, dim)
from pycde.dialects import comb, hw
from pycde.types import Bits, SInt, UInt
from pycde.constructs import Mux
from pycde.dialects import comb
from pycde.signals import ArraySignal

width = 32

class ALU(Module):
    A = Input(SInt(width))
    B = Input(SInt(width))
    alu_op = Input(Bits(4))
    out = Output(SInt(width))
    sum = Output(SInt(width))
  
    @generator
    def build(io):

        shamt = io.B.as_bits()

        lookup = ArraySignal.create([
            (io.A + io.B).as_sint(width),
            (io.A - io.B).as_sint(width),
            (io.A.as_bits() & io.B.as_bits()).as_sint(width),
            (io.A.as_bits() | io.B.as_bits()).as_sint(width),
            (io.A.as_bits() ^ io.B.as_bits()).as_sint(width),
            io.A, # (io.A < io.B).as_sint(width),
            comb.ShlOp(io.A.as_bits(), shamt).as_sint(width),
            io.A, # (io.A.as_uint() < io.B.as_uint()).as_sint(width),
            comb.ShrUOp(io.A.as_bits(), shamt).as_sint(width),
            comb.ShrSOp(io.A.as_bits(), shamt).as_sint(width),
            io.A,
            io.B,
            io.B,
            io.B,
            io.B,
            io.B,
        ])
        io.out = lookup[io.alu_op]
        io.sum = Mux(io.alu_op.as_bits(1), io.A + io.B, io.A - io.B).as_sint(width)

if __name__ == '__main__':
    mod = System([ALU],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()