"""The in place frame memory of the memory based FFT architecture.

The memory holds the complete spectrum while the transform is computed: the
butterflies read their two operands and write the results back to the same
places.  The read ports are combinational, the write ports are registered.

Three write ports are needed: one for the samples of the input frame and two
for the results of a butterfly (the sum and the difference).  Three read
ports are needed as well: the two operands of the butterfly and the result
which is sent out.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux
from pycde.signals import ArraySignal
from pycde.types import Bits


@modparams
def FrameMemory(width: int = 16, points: int = 16):
    """A frame memory with three write and three read ports."""
    addr_width = max(1, (points - 1).bit_length())

    class FrameMemory(Module):
        clk = Clock()
        rst = Reset()
        # the three write ports
        w0_addr = Input(Bits(addr_width))
        w0_re = Input(Bits(width))
        w0_im = Input(Bits(width))
        w0_en = Input(Bits(1))
        w1_addr = Input(Bits(addr_width))
        w1_re = Input(Bits(width))
        w1_im = Input(Bits(width))
        w1_en = Input(Bits(1))
        w2_addr = Input(Bits(addr_width))
        w2_re = Input(Bits(width))
        w2_im = Input(Bits(width))
        w2_en = Input(Bits(1))
        # the three read ports
        r0_addr = Input(Bits(addr_width))
        r0_re = Output(Bits(width))
        r0_im = Output(Bits(width))
        r1_addr = Input(Bits(addr_width))
        r1_re = Output(Bits(width))
        r1_im = Output(Bits(width))
        r2_addr = Input(Bits(addr_width))
        r2_re = Output(Bits(width))
        r2_im = Output(Bits(width))

        @generator
        def construct(io):
            def mux(sel, when_true, when_false):
                """A two input multiplexer.

                ``pycde.constructs.Mux(sel, a, b)`` returns ``b`` when ``sel``
                is high, this helper uses the intuitive order.
                """
                return Mux(sel, when_false, when_true)

            re_entries = []
            im_entries = []
            for i in range(points):
                hit0 = io.w0_en & (io.w0_addr == Bits(addr_width)(i)).as_bits()
                hit1 = io.w1_en & (io.w1_addr == Bits(addr_width)(i)).as_bits()
                hit2 = io.w2_en & (io.w2_addr == Bits(addr_width)(i)).as_bits()
                enable = hit0 | hit1 | hit2
                re_value = mux(hit0, io.w0_re.as_sint(),
                               mux(hit1, io.w1_re.as_sint(), io.w2_re.as_sint()))
                im_value = mux(hit0, io.w0_im.as_sint(),
                               mux(hit1, io.w1_im.as_sint(), io.w2_im.as_sint()))
                re_entries.append(re_value.reg(io.clk, io.rst, rst_value=0,
                                               ce=enable, name=f"mem_re_{i}"))
                im_entries.append(im_value.reg(io.clk, io.rst, rst_value=0,
                                               ce=enable, name=f"mem_im_{i}"))

            re_array = ArraySignal.create(re_entries)
            im_array = ArraySignal.create(im_entries)

            io.r0_re = re_array[io.r0_addr].as_bits()
            io.r0_im = im_array[io.r0_addr].as_bits()
            io.r1_re = re_array[io.r1_addr].as_bits()
            io.r1_im = im_array[io.r1_addr].as_bits()
            io.r2_re = re_array[io.r2_addr].as_bits()
            io.r2_im = im_array[io.r2_addr].as_bits()

    return FrameMemory
