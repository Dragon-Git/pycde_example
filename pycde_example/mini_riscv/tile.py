from pycde import (System, Module, Clock, Reset, Input, Output, generator, types)  # noqa: F401
from pycde.types import Bits  # noqa: F401
from pycde.constructs import NamedWire  # noqa: F401

from .cache import Cache
from .core import Core
from .const import XLEN  # noqa: F401

class Tile(Module):
    clk = Clock()
    rst = Reset()
    # dcache = Output()
    # icache = Output()

    @generator
    def build(io):

        dcache = Cache( "dcache",
             clk = io.clk, 
             rst = io.rst,
        )
        print(dcache.inst, dir(dcache.inst))
        icache = Cache( "icache",
             clk = io.clk, 
             rst = io.rst, 
        )
        print(icache.inst, dir(icache.inst))
        core = Core(
            clk = io.clk, 
            rst = io.rst, 
            # dcache = Bits(1)(0), 
            # icache = Bits(1)(0), 
            # ctrl = ctrl.ctrl, 
            # pc = Bits(XLEN)(0)
        )
        print(core.inst, dir(core.inst))


if __name__ == '__main__':
    mod = System([Tile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
