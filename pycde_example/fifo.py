from pycde import (System, Module, Input, Output, Clock, Reset, generator)
from pycde.types import Bits, UInt
from pycde.seq import FIFO

class SimpleFIFO(Module):
    clk = Clock()
    rst = Reset()
    data_in = Input(UInt(32))
    data_out = Output(UInt(32))
    @generator
    def construct(ports):
        c0 = Bits(1)(1)

        fifo = FIFO(type=UInt(32),
                depth=14,
                clk=ports.clk,
                rst=ports.rst,
                rd_latency=1)
        fifo.push(ports.data_in, c0)
        ports.data_out = fifo.pop(c0)

if __name__ == '__main__':
    mod = System([SimpleFIFO],name="ip_fifo_lib", output_directory="build/ip_fifo_lib")
    mod.compile()
