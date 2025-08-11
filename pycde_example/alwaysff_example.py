import pycde

from pycde import Module, Input, Output, generator, ir
from pycde.types import Bits
from pycde.circt.dialects import sv, hw, comb
from pycde.circt import ir as circt_ir
from pycde import support
from pycde.signals import _FromCirctValue

def unknown_location():
    return ir.Location.unknown()
support.get_user_loc.__code__ = unknown_location.__code__


class AsyncLowResetSyncReleaseCounter(Module):
    """异步低电平复位同步释放计数器示例。
    
    这个模块展示了如何使用sv.AlwaysFFOp创建带异步低电平复位的计数器，
    并实现复位的同步释放。这是数字电路设计中常用的复位策略。
    """

    module_name = "async_low_reset_sync_release_counter"
    clk = Input(Bits(1))
    # 异步复位输入，低电平有效
    rst_n = Input(Bits(1))
    
    # 控制计数器是否计数的输入信号
    enable = Input(Bits(1))
    # 计数器输出
    count = Output(Bits(8))

    @generator
    def construct(ports):
        # 创建一个8位寄存器来存储计数值
        i8_type = circt_ir.IntegerType.get_signless(8)
        count_reg = sv.RegOp(hw.InOutType.get(i8_type), name="count_reg")
        
        clock_edge = circt_ir.IntegerAttr.get(circt_ir.IntegerType.get_signless(32), 0) # 0:AtPosEdge, 1:AtNegEdge, 2:AtBothEdges
        reset_style = circt_ir.IntegerAttr.get(circt_ir.IntegerType.get_signless(32), 2) # 0:NoReset, 1:SyncReset, 2:AsyncReset
        reset_edge = circt_ir.IntegerAttr.get(circt_ir.IntegerType.get_signless(32), 1) # 0:AtPosEdge, 1:AtNegEdge, 2:AtBothEdges
        
        # 这对应于SystemVerilog中的always_ff @(posedge clk, negedge rst_n)
        # 使用AlwaysFFOp创建带异步复位的时序逻辑块
        always_blk = sv.AlwaysFFOp(
            clockEdge=clock_edge,
            clock=ports.clk.value,
            resetStyle=reset_style,
            resetEdge=reset_edge,
            reset=ports.rst_n.value,
        )
        always_blk.bodyBlk.blocks.append()
        always_blk.resetBlk.blocks.append()
        # 复位逻辑：异步低电平复位，同步释放
        with circt_ir.InsertionPoint(always_blk.resetBlk.blocks[0]):
            sv.PAssignOp(count_reg, hw.ConstantOp.create(i8_type, 1))
            
        with circt_ir.InsertionPoint(always_blk.bodyBlk.blocks[0]):

            # 读取计数寄存器的当前值
            current_count = sv.ReadInOutOp(count_reg)
            
            with_cond = sv.IfOp(ports.enable.value)
            with_cond.thenRegion.blocks.append()
            
            with circt_ir.InsertionPoint(with_cond.thenRegion.blocks[0]):
                # 计算下一个计数值 (current_count + 1)
                next_count = hw.ConstantOp.create(i8_type, 1)
                add_op = comb.AddOp.create(current_count, next_count)
                # 将新值赋给寄存器
                sv.PAssignOp(count_reg, add_op)
        
        # 将计数寄存器值连接到输出端口
        ports.count = _FromCirctValue(sv.ReadInOutOp(count_reg).result)


if __name__ == "__main__":
    # 创建系统并编译模块
    s = pycde.System(
        [AsyncLowResetSyncReleaseCounter],
        name="alwaysff_example",
        output_directory="build/alwaysff_example"
    )
    s.compile()
