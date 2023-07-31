from pycde import (System, Module, Clock, Reset, Input, Output, generator)
from pycde.types import SInt

class Test_hwarith(Module):
    clk = Clock()
    rst = Reset()
    a,b = map(Input,[SInt(32)]*2)
    c,d,e,f = map(Output,[SInt(32)]*4)

    @generator
    def construct(ports) -> None:
        ports.c = (ports.a + ports.b).as_sint(32).reg(ports.clk, ports.rst)
        ports.d = (ports.a - ports.b).as_sint(32).reg(ports.clk, ports.rst)
        ports.e = (ports.a * ports.b).as_sint(32).reg(ports.clk, ports.rst)
        ports.f = (ports.a / ports.b).as_sint(32).reg(ports.clk, ports.rst)

mod = System([Test_hwarith], name="test_lib", output_directory="build/test_lib")
mod.compile()