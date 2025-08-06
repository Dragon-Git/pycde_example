import pycde

from pycde import Clock, Module, Reset, Input, Output, generator,  ir
from pycde.types import Bits
from pycde.circt.dialects import sv
from pycde.circt.ir import IntegerType, IntegerAttr, InsertionPoint
from pycde import support

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
    al = sv.AlwaysCombOp()
    al.body.blocks.append()
    with InsertionPoint(al.body.blocks[0]):
        i6 = IntegerType.get_signless(6)
        case_op = sv.CaseOp(
            cond=ports.data_i.value,
            casePatterns=[
                IntegerAttr.get(i6, 0),  # case 0
                IntegerAttr.get(i6, 1),  # case 1
                IntegerAttr.get(i6, 4),  # case 2
                IntegerAttr.get(i6, 5),  # case 3
                IntegerAttr.get(i6, 16),  # case 4
                IntegerAttr.get(i6, 17),  # case 5
                IntegerAttr.get(i6, 20),  # case 6
                IntegerAttr.get(i6, 21),  # case 7
                ir.UnitAttr.get(),  # default 分支
            ],
            num_caseRegions=9,
        )
        for i in range(len(case_op.caseRegions)):
            case_op.caseRegions[i].blocks.append()
            with InsertionPoint(case_op.caseRegions[i].blocks[0]):
                sv.VerbatimOp(ir.StringAttr.get(f"// value = 32'h{i};\n"), [])
    ports.data_o = Bits(32)(0)

if __name__ == "__main__":

    s = pycde.System(CaseExample,
                   name="case_example",
                   output_directory="build/case_example",)
    s.compile()