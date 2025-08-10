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

class CaseExample(Module):
  """ A simple example of using CaseOp in PyCDE."""

  module_name = "case_example"
  clk = Clock()
  rst = Reset()

  data_i = Input(Bits(32))
  data_o = Output(Bits(32))

  @generator
  def construct(ports):
    i32_type = ir.IntegerType.get_signless(32)
    result_reg = sv.RegOp(hw.InOutType.get(i32_type), name="result_reg")
    
    al = sv.AlwaysCombOp()
    al.body.blocks.append()
    with ir.InsertionPoint(al.body.blocks[0]):
        case_conditions = [sum( ((n >> i) & 1) << (2*i) for i in range(n.bit_length()) )  for n in range(80)]
        case_values = list(range(81))[::-1]
        
        # 创建case patterns
        i6 = ir.IntegerType.get_signless(max(case_conditions).bit_length() + 1)
        case_patterns = [ir.IntegerAttr.get(i6, cond) for cond in case_conditions]
        case_patterns.append(ir.UnitAttr.get())  # default 分支
        
        case_op = sv.CaseOp(
            cond=ports.data_i.value,
            casePatterns=case_patterns,
            num_caseRegions=len(case_patterns),
        )
        
        # 为每个case分支赋值
        for i in range(len(case_op.caseRegions)):
            case_op.caseRegions[i].blocks.append()
            with ir.InsertionPoint(case_op.caseRegions[i].blocks[0]):
                sv.VerbatimOp(ir.StringAttr.get(f"// value = 32'h{i};\n"), [])
                sv.BPAssignOp(result_reg, Bits(32)(case_values[i]).value)
    
    # 从寄存器读取值并赋给输出端口
    ports.data_o = _FromCirctValue(sv.ReadInOutOp(result_reg).result)

if __name__ == "__main__":

    s = pycde.System(CaseExample,
                   name="case_example",
                   output_directory="build/case_example",)
    s.compile()