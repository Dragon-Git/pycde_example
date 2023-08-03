from pycde import (System, Module, Clock, Reset, InputChannel, OutputChannel, Input, Output, generator, types)  # noqa: F401
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
            dcache = Bits(1)(0), 
            icache = Bits(1)(0), 
            ctrl = ctrl.ctrl, 
            pc = Bits(XLEN)(0))
        insn.assign(dpath.insn)
        io.dreq, _ = types.channel(ReqType).wrap(ReqType({"addr": 123, "data": 456, "mask": 15})
        io.ireq, _ = types.channel(ReqType).wrap(ReqType({"addr": 123, "data": 456, "mask": 15})
        data, valid = io.dresp.unwrap(readyOrRden=1)
        data, valid = io.iresp.unwrap(readyOrRden=1)


if __name__ == '__main__':
    mod = System([Core],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
