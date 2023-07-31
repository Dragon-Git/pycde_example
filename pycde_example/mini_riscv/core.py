from pycde import (System, Module, Clock, Reset, Input, Output, generator, types)  # noqa: F401
from pycde.types import Bits
from pycde.constructs import NamedWire

from .control import Control
from .datapath import Datapath

XLEN = 32

class Core(Module):
    clk = Clock()
    rst = Reset()
    # dcache = Output()
    # icache = Output()

    @generator
    def build(io):

        insn = NamedWire(Bits(XLEN), "insn")
        ctrl = Control(insn = insn)
        dpath = Datapath(
            clk = io.clk, 
            rst = io.rst, 
            dcache = Bits(1)(0), 
            icache = Bits(1)(0), 
            ctrl = ctrl.ctrl, 
            pc = Bits(XLEN)(0))
        insn.assign(dpath.insn)
        # io.dcache = dpath.dcache
        # io.icache = dpath.icache


if __name__ == '__main__':
    mod = System([Core],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
