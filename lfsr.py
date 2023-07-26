from pycde import (Output, Input, Clock, Module, generator, System)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import ControlReg, NamedWire, Reg, Wire  # noqa: F401
from pycde.dialects import comb

POLY = [7, 5, 4, 3]
WIDTH = max(POLY) +1

class Lfsr(Module):
  clk = Clock()
  rst = Input(Bits(1))
  seed = Input(UInt(WIDTH))
  cnt = Output(UInt(WIDTH))

  @generator
  def construct(io):
    r1 = Reg(Bits(WIDTH), io.clk, io.rst, io.seed)
    r1.name = "Lfsr"
    w2 = comb.XorOp(*[r1[i] for i in POLY])
    w1.assign(comb.ConcatOp(r1[0:-1], w2))
    io.cnt = r1.as_uint()

if __name__ == '__main__':
  mod = System([Lfsr],name="ip_lfsr_lib", output_directory="build/ip_lfsr_lib")
  mod.compile()