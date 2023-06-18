from pycde import (System, Module, Input, Output, generator, types, dim)
from pycde.dialects import comb, hw

class Fir(Module):
  clk = Input(types.i1)
  rst = Input(types.i1)
  coeff = Input(dim(32, 16))
  data_in = Input(types.i32)
  data_out = Output(types.i32)

  @generator
  def build(ports):
    taps = [ports.data_in]
    mul_list = [hw.ConstantOp(types.i32, 0)]
    for i in range(16):
        taps.append(taps[-1].reg(ports.clk))
        mul_term = comb.MulOp(taps[-1],ports.coeff[i])
        ps = comb.AddOp(mul_term, mul_list[-1])
        mul_list.append(ps)
    ports.data_out = ps


mod = System([Fir],name="ip_fir_lib")
mod.compile()
