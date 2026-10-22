"""The pipelined architecture of the FFT.

The whole transform is unrolled: every radix-2 stage has its own butterflies
and the stages are separated by registers, the number of registers is the
number of pipeline stages.  The architecture needs ``log2(points)`` stages with
their butterflies, it trades the area for the throughput.

The frame is received into a register array, the transform is computed and the
result is read out of the last stage.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.dialects import comb
from pycde.signals import ArraySignal
from pycde.types import Bits, SInt, UInt

from .fft_model import twiddle_table


@modparams
def FftPipelined(width: int = 16, points: int = 16, ordering: str = "dit",
                 stages: int = 1, scaling: str = "stage"):
    """The pipelined (unrolled) architecture of the FFT."""
    levels = points.bit_length() - 1
    count_width = max(1, (points - 1).bit_length())
    table = twiddle_table(points, width)
    dit = ordering == "dit"
    # the number of cycles the transform needs
    latency = max(1, levels * stages)
    delay_width = max(1, latency.bit_length())

    def permute(index: int) -> int:
        """The bit reversed index."""
        return int(f"{index:0{levels}b}"[::-1], 2)

    class FftPipelined(Module):
        clk = Clock()
        rst = Reset()
        # the input frame
        in_valid = Input(Bits(1))
        in_real = Input(Bits(width))
        in_imag = Input(Bits(width))
        in_ready = Output(Bits(1))
        # the output frame
        out_valid = Output(Bits(1))
        out_real = Output(Bits(width))
        out_imag = Output(Bits(width))
        out_ready = Input(Bits(1))

        @generator
        def construct(io):
            def mux(sel, when_true, when_false):
                """A two input multiplexer.

                ``pycde.constructs.Mux(sel, a, b)`` returns ``b`` when ``sel``
                is high, this helper uses the intuitive order.
                """
                return Mux(sel, when_false, when_true)

            def shift_right(value, amount):
                """An arithmetic shift right by a constant."""
                shift = Bits(value.type.width)(amount)
                return comb.ShrSOp(value.as_bits(), shift).as_sint()

            def complex_multiply(a_re, a_im, b_re, b_im):
                """The complex product, the fractional bits are truncated."""
                prod_re = a_re * b_re - a_im * b_im
                prod_im = a_re * b_im + a_im * b_re
                amount = width - 1
                return (shift_right(prod_re, amount).as_sint(width),
                        shift_right(prod_im, amount).as_sint(width))

            # ------------------------------------------------------------------
            # the control
            # ------------------------------------------------------------------
            # 0: receiving the frame, 1: computing, 2: sending the result
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            in_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="in_count")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="out_count")
            delay_count = Reg(UInt(delay_width), io.clk, io.rst, 0, name="delay_count")

            receiving = (phase == UInt(2)(0)).as_bits()
            computing = (phase == UInt(2)(1)).as_bits()
            sending = (phase == UInt(2)(2)).as_bits()

            accept = io.in_valid & receiving
            last_input = (in_count == UInt(count_width)(points - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            # the transform is finished when the delay has expired
            finished = (delay_count == UInt(delay_width)(0)).as_bits()

            # ------------------------------------------------------------------
            # the input register array
            # ------------------------------------------------------------------
            in_re = []
            in_im = []
            for i in range(points):
                # every register of the frame is written when the input
                # counter reaches it
                enable = (in_count == UInt(count_width)(i)).as_bits()
                reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"in_re_{i}")
                reg_re.assign(io.in_real.as_sint())
                reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"in_im_{i}")
                reg_im.assign(io.in_imag.as_sint())
                in_re.append(reg_re)
                in_im.append(reg_im)

            # the decimation in time reads the frame bit reversed, the
            # decimation in frequency writes it bit reversed
            values_re = [in_re[permute(i) if dit else i] for i in range(points)]
            values_im = [in_im[permute(i) if dit else i] for i in range(points)]

            # ------------------------------------------------------------------
            # the transform
            # ------------------------------------------------------------------
            # the decimation in frequency processes the large butterflies first
            stage_order = range(levels) if dit else reversed(range(levels))
            for s in stage_order:
                half = 1 << s
                step = points >> (s + 1)
                new_re = []
                new_im = []
                for i in range(points):
                    # the partner of the sample i is the sample i + half
                    first = (i % (2 * half)) < half
                    partner = i + half if first else i - half
                    a_re = values_re[i]
                    a_im = values_im[i]
                    b_re = values_re[partner]
                    b_im = values_im[partner]
                    # u is the first element of the pair, v the second one
                    u_re, u_im = (a_re, a_im) if first else (b_re, b_im)
                    v_re, v_im = (b_re, b_im) if first else (a_re, a_im)
                    if scaling == "stage":
                        # the operands are halved before they are added
                        u_re = shift_right(u_re, 1)
                        u_im = shift_right(u_im, 1)
                        v_re = shift_right(v_re, 1)
                        v_im = shift_right(v_im, 1)
                    if dit:
                        # the twiddle multiplies the second element of the pair
                        (t_re, t_im) = complex_multiply(
                            SInt(width)(table[(i % half) * step][0]),
                            SInt(width)(table[(i % half) * step][1]), v_re, v_im)
                        sum_re = (u_re + t_re).as_sint(width)
                        sum_im = (u_im + t_im).as_sint(width)
                        diff_re = (u_re - t_re).as_sint(width)
                        diff_im = (u_im - t_im).as_sint(width)
                    else:
                        # the twiddle multiplies the output of the butterfly
                        sum_re = (u_re + v_re).as_sint(width)
                        sum_im = (u_im + v_im).as_sint(width)
                        diff_re = (u_re - v_re).as_sint(width)
                        diff_im = (u_im - v_im).as_sint(width)
                        (diff_re, diff_im) = complex_multiply(
                            SInt(width)(table[(i % half) * step][0]),
                            SInt(width)(table[(i % half) * step][1]),
                            diff_re, diff_im)
                    if first:
                        new_re.append(sum_re)
                        new_im.append(sum_im)
                    else:
                        new_re.append(diff_re)
                        new_im.append(diff_im)

                # the pipeline registers between the stages
                for _ in range(stages):
                    for i in range(points):
                        new_re[i] = new_re[i].reg(io.clk, io.rst, ce=computing,
                                                  name=f"stage{s}_re_{i}")
                        new_im[i] = new_im[i].reg(io.clk, io.rst, ce=computing,
                                                  name=f"stage{s}_im_{i}")
                values_re = new_re
                values_im = new_im

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            phase_next = phase
            in_count_next = in_count
            out_count_next = out_count
            delay_count_next = delay_count

            # receiving: the samples are counted, the last one starts the
            # computation
            phase_next = mux(receiving & last_input, UInt(2)(1), phase_next)
            in_count_next = mux(accept,
                                (in_count + UInt(count_width)(1)).as_uint(count_width),
                                in_count_next)
            # computing: the transform needs `latency` cycles
            phase_next = mux(computing & finished, UInt(2)(2), phase_next)
            delay_count_next = mux(receiving & last_input, UInt(delay_width)(latency - 1),
                                   mux(computing,
                                       (delay_count - UInt(delay_width)(1)).as_uint(delay_width),
                                       delay_count_next))
            # sending: the result is read out of the last stage
            phase_next = mux(sending & last_output & io.out_ready, UInt(2)(0),
                             phase_next)
            out_count_next = mux(sending & io.out_ready,
                                 (out_count + UInt(count_width)(1)).as_uint(count_width),
                                 out_count_next)
            in_count_next = mux(sending & last_output & io.out_ready,
                                UInt(count_width)(0), in_count_next)

            phase.assign(phase_next)
            in_count.assign(in_count_next)
            out_count.assign(out_count_next)
            delay_count.assign(delay_count_next)

            # ------------------------------------------------------------------
            # the interface
            # ------------------------------------------------------------------
            # the decimation in frequency produces the spectrum bit reversed
            out_index = out_count.as_uint()
            if not dit:
                out_index = UInt(count_width)(0)
                for i in range(points):
                    out_index = mux(out_count == UInt(count_width)(permute(i)),
                                    UInt(count_width)(i), out_index)
            # the spectrum is read out of the last stage
            out_array_re = ArraySignal.create(values_re)
            out_array_im = ArraySignal.create(values_im)
            io.in_ready = receiving
            io.out_valid = sending
            io.out_real = out_array_re[out_index].as_bits()
            io.out_imag = out_array_im[out_index].as_bits()

    FftPipelined.module_name = f"FftPipelined{width}P{points}S{stages}"
    return FftPipelined
