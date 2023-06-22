from pycde import (Output, Input, Clock, Module, generator, System)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import ControlReg, NamedWire, Reg, Wire  # noqa: F401
from pycde.dialects import comb

class Lfsr(Module):
  clk = Clock()
  rst = Input(Bits(1))
  seed = Input(UInt(8))
  cnt = Output(UInt(8))

  @generator
  def construct(ports):
    w1 = Wire(Bits(8))
    r1 = w1.reg(ports.clk, ports.rst)
    r1.name = "Lfsr"
    w2 = r1[7] ^ r1[5] ^ r1[4] ^ r1[3]
    w1.assign(comb.ConcatOp(r1[0:7], w2))
    ports.cnt = r1.as_uint()

if __name__ == '__main__':
  mod = System([Lfsr],name="ip_lfsr_lib", output_directory="build/ip_lfsr_lib")
  mod.compile()