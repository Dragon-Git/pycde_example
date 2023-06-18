from pycde import (System, Module, Clock, Input, Output, generator)
from pycde.types import SInt,Bits

class Test_hwarith(Module):
    clk = Clock()
    rst = Input(Bits(1))
    a,b = map(Input,[SInt(32)]*2)
    c,d,e,f = map(Output,[Bits(32)]*4)

    @generator
    def construct(ports) -> None:
        ports.c = (ports.a + ports.b).as_bits(32).reg(ports.clk, ports.rst)
        ports.d = (ports.a - ports.b).as_bits(32).reg(ports.clk, ports.rst)
        ports.e = (ports.a * ports.b).as_bits(32).reg(ports.clk, ports.rst)
        ports.f = (ports.a / ports.b).as_bits(32).reg(ports.clk, ports.rst)

mod = System([Test_hwarith], name="test_lib")
mod.compile()