import pycde

from pycde import Clock, Module, Reset, Input, Output, generator, ir
from pycde.types import Bits
from pycde.circt.dialects import seq
from pycde import support
from pycde.signals import _FromCirctValue

def unknown_location():
    return ir.Location.unknown()
support.get_user_loc.__code__ = unknown_location.__code__

# 替换support模块中的函数对象

class CaseExample(Module):
  """ A simple example of using CaseOp in PyCDE."""

  module_name = "case_example"
  clk = Clock()
  rst = Reset()

  data_i = Input(Bits(32))
  data_o = Output(Bits(32))

  @generator
  def construct(ports):
    re = seq.FirRegOp(
        ports.data_i.value,
        clk=ports.clk.value,
        name="result_reg",
        preset=ir.IntegerAttr.get(ir.IntegerType.get_signless(32), 0x12345678),
        reset=ports.rst.value,
        resetValue=Bits(32)(0).value,
        isAsync=True
    )
    ports.data_o = _FromCirctValue(re.data)

if __name__ == "__main__":

    s = pycde.System(CaseExample,
                   name="case_example",
                   output_directory="build/case_example",)
    s.compile()