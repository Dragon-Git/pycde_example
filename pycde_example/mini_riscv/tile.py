from pycde import (System, Module, Clock, Reset, Input, Output, generator, types)  # noqa: F401
from pycde.types import Bits  # noqa: F401
from pycde.constructs import Wire

from .cache import Cache, ReqType
from .core import Core
from .const import XLEN  # noqa: F401

class Tile(Module):
    clk = Clock()
    rst = Reset()
    # dcache = Output()
    # icache = Output()

    @generator
    def build(io):

        dreq = Wire(types.channel(ReqType))
        ireq = Wire(types.channel(ReqType))
        dcache_out = Cache( "dcache",
             clk = io.clk, 
             rst = io.rst,
             req = dreq,
        )
        icache_out = Cache( "icache",
             clk = io.clk, 
             rst = io.rst, 
             req = ireq,
        )
        core = Core(
            clk = io.clk, 
            rst = io.rst, 
            dresp = dcache_out.resp, 
            iresp = icache_out.resp, 
            # ctrl = ctrl.ctrl, 
            # pc = Bits(XLEN)(0)
        )
        dreq.assign(core.dreq)
        ireq.assign(core.ireq)


if __name__ == '__main__':
    mod = System([Tile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
