import pycde

from pycde import Clock, Module, Reset, Input, Output, generator, ir
from pycde.types import Bits
from pycde.circt.dialects import sv, hw
from pycde import support
from pycde.signals import _FromCirctValue

def unknown_location():
    return ir.Location.unknown()
support.get_user_loc.__code__ = unknown_location.__code__

# 替换support模块中的函数对象

class IfElseExample(Module):
  """ A simple example of using CaseOp in PyCDE."""

  module_name = "ifelse_example"
  clk = Clock()
  rst = Reset()

  sel = Input(Bits(1))
  data_i0 = Input(Bits(32))
  data_i1 = Input(Bits(32))
  data_o = Output(Bits(32))

  @generator
  def construct(ports):
    i32_type = ir.IntegerType.get_signless(32)
    result_reg = sv.RegOp(hw.InOutType.get(i32_type), name="result_reg")
    
    al = sv.AlwaysCombOp()
    al.body.blocks.append()
    with ir.InsertionPoint(al.body.blocks[0]):        
        if_op = sv.IfOp(ports.sel.value)
        # 为每个if分支赋值
        if_op.thenRegion.blocks.append()
        with ir.InsertionPoint(if_op.thenRegion.blocks[0]):
            sv.VerbatimOp(ir.StringAttr.get(f"// value = 32'h{0};\n"), [])
            sv.BPAssignOp(result_reg, ports.data_i0.value)
        if_op.elseRegion.blocks.append()
        with ir.InsertionPoint(if_op.elseRegion.blocks[0]):
            sv.VerbatimOp(ir.StringAttr.get(f"// value = 32'h{1};\n"), [])
            sv.BPAssignOp(result_reg, ports.data_i1.value)

    # 从寄存器读取值并赋给输出端口
    ports.data_o = _FromCirctValue(sv.ReadInOutOp(result_reg).result)

if __name__ == "__main__":

    s = pycde.System(IfElseExample,
                   name="ifelse_example",
                   output_directory="build/ifelse_example",)
    s.compile()