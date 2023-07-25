
from pycde import (Clock, Input, Output, Module, System, generator, types, dim)
from pycde.types import Bits, SInt, UInt, Array, List  # noqa: F401
from pycde.common import Clock, Reset
from pycde.constructs import Mux, Reg, Wire
from pycde.signals import ArraySignal

XLEN = 32


class Regfile(Module):
    clk = Clock()
    rst = Reset()
    raddr1 = Input(Bits(5))
    raddr2 = Input(Bits(5))
    rdata1 = Output(Bits(XLEN))
    rdata2 = Output(Bits(XLEN))
    wen    = Input(Bits(1))
    waddr  = Input(Bits(5))
    wdata  = Input(Bits(XLEN))

    @generator
    def build(io):
        regs = Reg(Array(Bits(XLEN), 32), rst_value=[0]*32)
        io.rdata1 = Mux(io.raddr1.or_reduce(), Bits(XLEN)(0), regs[io.raddr1])
        io.rdata2 = Mux(io.raddr2.or_reduce(), Bits(XLEN)(0), regs[io.raddr2])
        datas = [regs[i] for i in range(32)]
        data = Mux(io.wen & io.waddr.or_reduce(), regs[io.waddr], io.wdata)
        datas = ArraySignal.create(datas)
        regs.assign(datas)

if __name__ == '__main__':
    mod = System([Regfile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
