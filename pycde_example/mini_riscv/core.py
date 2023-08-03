from pycde import (System, Module, Clock, Reset, InputChannel, OutputChannel, Input, generator, types)  # noqa: F401
from pycde.types import Bits
from pycde.constructs import NamedWire

from .control import Control
from .datapath import Datapath
from .cache import ReqType
from .const import XLEN

class Core(Module):
    clk = Clock()
    rst = Reset()
    dreq = OutputChannel(ReqType)
    dresp = InputChannel(Bits(XLEN))
    ireq = OutputChannel(ReqType)
    iresp = InputChannel(Bits(XLEN))

    @generator
    def build(io):

        insn = NamedWire(Bits(XLEN), "insn")
        ctrl = Control(insn = insn)
        dpath = Datapath(
            clk = io.clk, 
            rst = io.rst, 
            ctrl = ctrl.ctrl, 
            dresp = io.dresp, 
            iresp = io.iresp)
        insn.assign(dpath.insn)
        io.dreq = dpath.dreq
        io.ireq = dpath.ireq


if __name__ == '__main__':
    mod = System([Core],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
