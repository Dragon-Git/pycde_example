from pycde import (System, Module, Clock, Reset, Input, Output, generator, types)  # noqa: F401
from pycde.types import Bits  # noqa: F401
from pycde.constructs import Wire

from .cache import Cache, ReqType
from .const import XLEN  # noqa: F401
from .core import Core

class Tile(Module):
    clk = Clock()
    rst = Reset()
    # dcache = Output()
    # icache = Output()

    @generator
    def build(io):
        dreq = Wire(types.channel(ReqType))
        ireq = Wire(types.channel(ReqType))
        dcache = Cache("dcache", clk=io.clk, rst=io.rst, req=dreq)
        icache = Cache("icache", clk=io.clk, rst=io.rst, req=ireq)
        core = Core(clk=io.clk, rst=io.rst, dresp=dcache.resp, iresp=icache.resp)
        dreq.assign(core.dreq)
        ireq.assign(core.ireq)


if __name__ == "__main__":
    mod = System([Tile], name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
