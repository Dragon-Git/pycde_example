from pycde import (System, Module, Input, Output, Clock, generator, dim)
from pycde.types import Bits, SInt

class Fir(Module):
  clk = Input(Clock())
  rst = Input(Bits(1))
  coeff = Input(dim(32, 16))
  data_in = Input(SInt(32))
  data_out = Output(SInt(32))

  @generator
  def build(ports):
    taps = [ports.data_in]
    mul_list = [SInt(32)(0)]
    for i in range(16):
        taps.append(taps[-1].reg(ports.clk))
        mul_term = taps[-1] * ports.coeff[i]
        ps = mul_term + mul_list[-1]
        mul_list.append(ps)
    ports.data_out = ps


mod = System([Fir],name="ip_fir_lib", output_directory="build/ip_fir_lib")
mod.compile()
