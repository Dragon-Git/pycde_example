import math
import pycde
from pycde import (Output, Input, Module, generator, System)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.common import Clock, Reset
from pycde.constructs import ControlReg, NamedWire, Reg, Wire, Mux  # noqa: F401
from pycde.behavioral import If, Else, EndIf

@pycde.modparams
def counter(limit, inc = 1):
  width = math.ceil(math.log2(limit))
  class Counter(Module):
    clk = Clock()
    rst = Reset()
    cnt = Output(UInt(width))

    @generator
    def construct(ports):
      counter = Reg(UInt(width), rst = ports.rst)
      counter.name = "count"
      ports.cnt = counter
      # counter.assign(Mux((counter == UInt(width)(limit)).as_bits(1), (counter + inc).as_uint(width), UInt(width)(0)))
      cnt = (counter + inc).as_uint(width)
      with If((counter == UInt(width)(limit)).as_bits(1)):
        cnt = UInt(width)(0)
      EndIf()
      counter.assign(cnt)
      #  An alternative implementation
      # w1 = Wire(UInt(32))
      # r1 = w1.reg(ports.clk, ports.rst)
      # w1.assign((r1 + 1).as_uint(32)) # increment the internal counter
      # ports.cnt = r1
  return Counter


if __name__ == '__main__':
  mod = System([counter(58642)],name="ip_cnt_lib", output_directory="build/ip_cnt_lib")
  mod.compile()