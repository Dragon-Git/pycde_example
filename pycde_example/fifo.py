from pycde import (System, Module, Input, Output, Clock, Reset, generator)
from pycde.types import UInt
from pycde.seq import FIFO

class SimpleFIFO(Module):
    clk = Clock()
    rst = Reset()
    data_in = Input(UInt(32))
    data_out = Output(UInt(32))
    @generator
    def construct(ports):
        # c0 = Bits(1)(1)
        # push 和 pop需要有条件
        fifo = FIFO(type=UInt(32),
                depth=14,
                clk=ports.clk,
                rst=ports.rst,
                rd_latency=1)
        can_push = ~fifo.full
        fifo.push(ports.data_in, can_push)
        can_pop = ~fifo.empty
        ports.data_out = fifo.pop(can_pop)

if __name__ == '__main__':
    mod = System([SimpleFIFO],name="ip_fifo_lib", output_directory="build/ip_fifo_lib")
    mod.compile()
