from pycde import (Output, Input, Clock, Module, generator, System)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import ControlReg, NamedWire, Reg, Wire  # noqa: F401

class Counter(Module):
  clk = Clock()
  rst = Input(Bits(1))
  cnt = Output(UInt(32))

  @generator
  def construct(ports):
    r1 = Reg(UInt(32), ports.clk, ports.rst)
    r1.name = "counter"
    ports.cnt = r1
    r1.assign((r1 + 1).as_uint(32))
    #  An alternative implementation
    # w1 = Wire(UInt(32))
    # r1 = w1.reg(ports.clk, ports.rst)
    # w1.assign((r1 + 1).as_uint(32)) # increment the internal counter
    # ports.cnt = r1

if __name__ == '__main__':
  mod = System([Counter],name="ip_cnt_lib")
  mod.compile()