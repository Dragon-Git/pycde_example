import math
from pycde import System, Module, Clock, Input, Output, generator
from pycde.behavioral import If, Else, EndIf
from pycde.dialects import comb
from pycde.types import Bits, SInt, StructType

Coord_sint = StructType({"x": SInt(32), "y": SInt(32), "theta": SInt(32)})
Coord_port = StructType({"x": Bits(32), "y": Bits(32), "theta": Bits(32)})
theta_list = [round(math.atan(2 ** (-i)) * 2**30 / math.pi) for i in range(16)]

def st_m_op(st, func, conv_st = Coord_sint):
    return conv_st({field[0]: func(st[field[0]]) for field in st.type.fields})

class Cordic(Module):
    clk = Clock()
    rst = Input(Bits(1))
    coord_i = Input(Coord_port)
    coord_o = Output(Coord_port)

    @generator
    def build_comb(ports) -> None:
        taps = [st_m_op(ports.coord_i, lambda x : x.as_sint())]
        for i in range(16):
            dirc = taps[-1].theta.as_bits(32).slice(Bits(32)(31), 1)
            x_sh = comb.ShrSOp(taps[-1].x.as_bits(), Bits(32)(i)).as_sint()
            y_sh = comb.ShrSOp(taps[-1].y.as_bits(), Bits(32)(i)).as_sint()
            with If(dirc):
                coord_t = Coord_sint({
                    "x": (taps[-1].x - y_sh).as_sint(32),
                    "y": (taps[-1].y + x_sh).as_sint(32),
                    "theta": (taps[-1].theta - SInt(32)(theta_list[i])).as_sint(32),
                })
            with Else():
                coord_t = Coord_sint({
                    "x": (taps[-1].x + y_sh).as_sint(32),
                    "y": (taps[-1].y - x_sh).as_sint(32),
                    "theta": (taps[-1].theta + SInt(32)(theta_list[i])).as_sint(32),
                })
            EndIf()
            taps.append(coord_t)
        ports.coord_o = st_m_op(taps[-1], lambda x : x.as_bits(32).reg(ports.clk, ports.rst), Coord_port)
        # TODO: overflow process


if __name__ == "__main__":
    mod = System([Cordic], name="ip_codic_lib")
    mod.compile()
