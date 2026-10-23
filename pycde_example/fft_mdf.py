"""The multi path delay feedback (MDF) architecture of the FFT.

The first stage of the decimation in frequency pairs ``a[j]`` with
``a[j + points / 2]``::

    u[j] = (a[j] + a[j + points / 2]) / 2
    v[j] = (a[j] - a[j + points / 2]) / 2 * W**j

The two halves of the frame meet there and nowhere else, because from the second
stage on the pairing distance is at most ``points / 4``, which keeps both members
of a pair inside the same half.  The architecture follows from that: a butterfly
of the first stage splits the frame into the two halves and each half is then
transformed by a delay feedback chain of its own.  Several paths, each of them
fed back - that is the name, and the two chains working side by side are where
the throughput comes from.

The chains are the stages of the single path architecture, so this module
instantiates that architecture twice, over ``points / 2`` points.  A chain of
the decimation in frequency hands its spectrum out in the natural order, so the
two half spectra only have to be interleaved: the first path carries the even
bins and the second one the odd bins.

The result appears ``points`` cycles after the frame was collected, and the
buffer which holds it is filled while the chains drain, so a frame can be
collected again as soon as it was sent.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.dialects import comb
from pycde.signals import ArraySignal
from pycde.types import Bits, SInt, UInt

from .fft_butterfly import ComplexMultiplier
from .fft_model import twiddle_table
from .fft_radix_model import expand_radices
from .fft_sdf import FftSdf
from .fft_sdf_radix import FftSdfRadix

SCALINGS = ("stage", "none")


@modparams
def FftMdf(width: int = 16, points: int = 16, scaling: str = "stage",
           stages: int = 0, radices: str = "2"):
    """The multi path delay feedback architecture of the FFT.

    It decimates in frequency: the first stage is the one which needs both
    halves at the same time, and it is the butterfly which this module adds.
    """
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if stages < 0:
        raise ValueError(f"stages must not be negative, got {stages}")
    if points < 4 or (points & (points - 1)):
        raise ValueError(f"points must be a power of two and at least 4, "
                         f"got {points}")

    # The decomposition starts with the stage which splits the frame - a radix 2
    # one, since it is the butterfly of the first stage of the decimation in
    # frequency - and the rest belongs to the chains, which work on half of the
    # frame each.
    stage_list = expand_radices(radices, points)
    if stage_list[0] != 2:
        raise ValueError(f"the first stage of this architecture splits the "
                         f"frame and is a radix 2 one, got {radices!r}")
    chain_list = stage_list[1:]
    chain_radices = ",".join(str(r) for r in chain_list)
    has_big_radix = any(radix != 2 for radix in chain_list)

    half = points // 2
    count_width = max(1, (points - 1).bit_length())
    half_width = max(1, (half - 1).bit_length())
    table = twiddle_table(points, width)

    class FftMdf(Module):
        clk = Clock()
        rst = Reset()
        in_valid = Input(Bits(1))
        in_real = Input(Bits(width))
        in_imag = Input(Bits(width))
        in_ready = Output(Bits(1))
        out_valid = Output(Bits(1))
        out_real = Output(Bits(width))
        out_imag = Output(Bits(width))
        out_ready = Input(Bits(1))

        @generator
        def construct(io):
            def mux(sel, when_true, when_false):
                """A two input multiplexer, ``when_true`` is selected by 1."""
                return Mux(sel, when_false, when_true)

            def shift_right(value, amount):
                """An arithmetic shift right by a constant."""
                shift = Bits(value.type.width)(amount)
                return comb.ShrSOp(value.as_bits(), shift).as_sint()

            def negate(value):
                """The negation of a signed value, in the same width."""
                wide = value.as_sint(width + 1)
                return (SInt(width + 1)(0) - wide).as_sint(width)

            # ------------------------------------------------------------------
            # the control
            # ------------------------------------------------------------------
            # 0: collecting the frame, 1: feeding the two chains, 2: waiting
            # for the chains, 3: sending the spectrum
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            cnt = Reg(UInt(count_width), io.clk, io.rst, 0, name="cnt")
            collect = Reg(UInt(half_width), io.clk, io.rst, 0, name="collect")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                            name="out_count")

            collecting = (phase == UInt(2)(0)).as_bits()
            feeding = (phase == UInt(2)(1)).as_bits()
            waiting = (phase == UInt(2)(2)).as_bits()
            sending = (phase == UInt(2)(3)).as_bits()

            accept = io.in_valid & collecting
            last_input = (cnt == UInt(count_width)(points - 1)).as_bits()
            last_feed = (cnt == UInt(count_width)(half - 1)).as_bits()
            last_collect = (collect == UInt(half_width)(half - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            frame_done = sending & last_output & io.out_ready

            # ------------------------------------------------------------------
            # the frame
            # ------------------------------------------------------------------
            # A sample and its partner are ``points / 2`` apart in the frame, so
            # the frame is collected before the leading butterfly runs.
            buf_re = []
            buf_im = []
            for i in range(points):
                enable = accept & (cnt == UInt(count_width)(i)).as_bits()
                reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"frame_re_{i}")
                reg_re.assign(io.in_real.as_sint())
                reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"frame_im_{i}")
                reg_im.assign(io.in_imag.as_sint())
                buf_re.append(reg_re)
                buf_im.append(reg_im)
            frame_re = ArraySignal.create([r.as_bits() for r in buf_re])
            frame_im = ArraySignal.create([r.as_bits() for r in buf_im])

            # ------------------------------------------------------------------
            # the leading butterfly
            # ------------------------------------------------------------------
            # The operand of the first path is the sum, the operand of the
            # second one the difference; both are halved, which is the scaling
            # of this stage.
            low_index = cnt.as_bits()[:count_width]
            high_index = (cnt + UInt(count_width)(half)).as_uint(
                count_width).as_bits()[:count_width]
            a_re = frame_re[low_index].as_sint()
            a_im = frame_im[low_index].as_sint()
            b_re = frame_re[high_index].as_sint()
            b_im = frame_im[high_index].as_sint()
            if scaling == "stage":
                a_re = shift_right(a_re, 1)
                a_im = shift_right(a_im, 1)
                b_re = shift_right(b_re, 1)
                b_im = shift_right(b_im, 1)

            sum_re = (a_re + b_re).as_sint(width)
            sum_im = (a_im + b_im).as_sint(width)
            diff_re = (a_re - b_re).as_sint(width)
            diff_im = (a_im - b_im).as_sint(width)

            # the twiddle factor of the difference: the step of the first stage
            # is one, so the exponent is the position in the half of the frame
            factor_re = SInt(width)(table[0][0])
            factor_im = SInt(width)(table[0][1])
            for k in range(1, half):
                select = (cnt == UInt(count_width)(k)).as_bits()
                factor_re = mux(select, SInt(width)(table[k][0]), factor_re)
                factor_im = mux(select, SInt(width)(table[k][1]), factor_im)

            multiplier = ComplexMultiplier(width=width)(
                a_re=diff_re.as_bits(), a_im=diff_im.as_bits(),
                b_re=factor_re.as_bits(), b_im=factor_im.as_bits())
            # the trivial factors are applied exactly: the table cannot hold
            # +1.0, and W**(points/4) is -j, a swap with a negation
            no_twiddle = (cnt == UInt(count_width)(0)).as_bits()
            quarter = (cnt == UInt(count_width)(points // 4)).as_bits()
            odd_re = mux(no_twiddle, diff_re,
                         mux(quarter, diff_im, multiplier.re.as_sint()))
            odd_im = mux(no_twiddle, diff_im,
                         mux(quarter, negate(diff_re),
                             multiplier.im.as_sint()))

            # ------------------------------------------------------------------
            # the two chains
            # ------------------------------------------------------------------
            # Each half is transformed by the single path delay feedback
            # architecture over half of the points.  The two chains are driven
            # with the same signals, so they stay in step and their spectra can
            # be interleaved cycle by cycle.  ``stages`` is the number of
            # registers between two stages of a chain, it adds to the latency
            # without changing the values.
            even_valid = feeding & (cnt < UInt(count_width)(half)).as_bits()
            if has_big_radix:
                # a chain whose stages carry a butterfly of their own radix
                even = FftSdfRadix(width=width, points=half,
                                   radices=chain_radices, scaling=scaling)(
                                       clk=io.clk, rst=io.rst,
                                       in_valid=even_valid,
                                       in_real=sum_re.as_bits(),
                                       in_imag=sum_im.as_bits(),
                                       out_ready=Bits(1)(1))
                odd = FftSdfRadix(width=width, points=half,
                                  radices=chain_radices, scaling=scaling)(
                                      clk=io.clk, rst=io.rst,
                                      in_valid=even_valid,
                                      in_real=odd_re.as_bits(),
                                      in_imag=odd_im.as_bits(),
                                      out_ready=Bits(1)(1))
            else:
                even = FftSdf(width=width, points=half, ordering="dif",
                              scaling=scaling, stages=stages)(
                                  clk=io.clk, rst=io.rst,
                                  in_valid=even_valid,
                                  in_real=sum_re.as_bits(),
                                  in_imag=sum_im.as_bits(),
                                  out_ready=Bits(1)(1))
                odd = FftSdf(width=width, points=half, ordering="dif",
                             scaling=scaling, stages=stages)(
                                 clk=io.clk, rst=io.rst,
                                 in_valid=even_valid,
                                 in_real=odd_re.as_bits(),
                                 in_imag=odd_im.as_bits(),
                                 out_ready=Bits(1)(1))

            # the feeding position moves on when the chains took the sample
            feed_accepted = even_valid & even.in_ready

            # ------------------------------------------------------------------
            # the spectrum
            # ------------------------------------------------------------------
            # The first path carries the even bins and the second one the odd
            # bins, both in the natural order, so they interleave directly.
            collecting_now = (waiting | feeding) & even.out_valid
            buf_out_re = []
            buf_out_im = []
            for b in range(points):
                slot = b // 2
                enable = (collecting_now
                          & (collect == UInt(half_width)(slot)).as_bits())
                reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"spec_re_{b}")
                source_re = even.out_real if b % 2 == 0 else odd.out_real
                source_im = even.out_imag if b % 2 == 0 else odd.out_imag
                reg_re.assign(source_re.as_sint())
                reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"spec_im_{b}")
                reg_im.assign(source_im.as_sint())
                buf_out_re.append(reg_re)
                buf_out_im.append(reg_im)
            spec_re = ArraySignal.create([r.as_bits() for r in buf_out_re])
            spec_im = ArraySignal.create([r.as_bits() for r in buf_out_im])
            read_index = out_count.as_bits()[:count_width]

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            phase_next = phase
            phase_next = mux(collecting & last_input, UInt(2)(1), phase_next)
            phase_next = mux(feeding & last_feed & feed_accepted,
                             UInt(2)(2), phase_next)
            phase_next = mux(waiting & collecting_now & last_collect,
                             UInt(2)(3), phase_next)
            phase_next = mux(frame_done, UInt(2)(0), phase_next)
            phase.assign(phase_next)

            cnt_next = mux(accept,
                           (cnt + UInt(count_width)(1)).as_uint(count_width),
                           cnt)
            cnt_next = mux(feeding & feed_accepted,
                           (cnt + UInt(count_width)(1)).as_uint(count_width),
                           cnt_next)
            cnt.assign(mux(frame_done, UInt(count_width)(0), cnt_next))

            collect_next = mux(collecting_now,
                               (collect + UInt(half_width)(1)).as_uint(
                                   half_width),
                               collect)
            collect.assign(mux(waiting & collecting_now & last_collect,
                               UInt(half_width)(0), collect_next))

            out_count_next = mux(frame_done,
                                 UInt(count_width)(0),
                                 mux(sending & io.out_ready,
                                     (out_count + UInt(count_width)(1)).as_uint(
                                         count_width),
                                     out_count))
            out_count.assign(out_count_next)

            io.in_ready = collecting
            io.out_valid = sending
            io.out_real = spec_re[read_index]
            io.out_imag = spec_im[read_index]

    FftMdf.module_name = f"FftMdf{width}P{points}"
    return FftMdf
