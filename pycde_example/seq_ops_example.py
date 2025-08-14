import pycde
from pycde import Clock, Input, Output, Module, generator
from pycde.types import Bits
from pycde.dialects import seq
from pycde.signals import _FromCirctValue


class SeqOpsExample(Module):
    """演示seq方言中各种时钟操作符的使用"""

    module_name = "seq_ops_example"

    # 输入信号
    clk = Clock()
    rst = Input(Bits(1))
    enable = Input(Bits(1))
    data_in = Input(Bits(8))
    mux_select = Input(Bits(1))

    # 输出信号
    clock_div_out = Output(Bits(1))
    clock_gate_out = Output(Bits(1))
    clock_inv_out = Output(Bits(1))
    clock_mux_out = Output(Bits(1))
    data_out = Output(Bits(8))

    @generator
    def construct(ports):
        # 1. 演示 ClockDividerOp - 时钟分频器
        # 将输入时钟分频2^4=16倍
        clk_as_clock = ports.clk.value
        clock_div = seq.clock_div(clk_as_clock, 4)
        # 时钟类型不能直接连接到位输出，需要转换
        clock_div_bit = seq.FromClockOp(clock_div)
        ports.clock_div_out = _FromCirctValue(clock_div_bit.value)

        # 2. 演示 ClockGateOp - 时钟门控
        # 根据enable信号控制时钟的传递
        clock_gated = seq.clock_gate(clk_as_clock, ports.enable.value)
        clock_gated_bit = seq.FromClockOp(clock_gated)
        ports.clock_gate_out = _FromCirctValue(clock_gated_bit.value)

        # 3. 演示 ClockInverterOp - 时钟反相器
        # 将时钟信号反相
        clock_inverted = seq.clock_inv(clk_as_clock)
        clock_inv_bit = seq.FromClockOp(clock_inverted)
        ports.clock_inv_out = _FromCirctValue(clock_inv_bit.value)

        # 4. 演示 ClockMuxOp - 时钟多路选择器
        # 在两个时钟源之间选择
        clock_muxed = seq.clock_mux(ports.mux_select.value, 
                                   clk_as_clock, 
                                   clock_div)
        clock_muxed_bit = seq.FromClockOp(clock_muxed)
        ports.clock_mux_out = _FromCirctValue(clock_muxed_bit.value)

        # 5. 演示带使能的寄存器
        # 使用时钟门控的时钟作为寄存器时钟
        reg_with_ce = seq.CompRegClockEnabledOp(
            Bits(8),                     # result_type
            input=ports.data_in.value,   # input
            clk=clock_gated,             # clk
            clockEnable=ports.enable.value,  # clockEnable
            reset=ports.rst.value,
            reset_value=Bits(8)(0).value,
            name="reg_with_ce"           # 直接使用字符串而不是StringAttr
        )
        ports.data_out = _FromCirctValue(reg_with_ce.value)


if __name__ == "__main__":
    # 创建系统并编译模块
    s = pycde.System([SeqOpsExample],
                     name="seq_ops_example",
                     output_directory="build/seq_ops_example")
    s.compile()