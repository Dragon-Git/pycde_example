"""The multi path delay commutator (MDC) architecture of the FFT.

The first stage of the decimation in frequency pairs ``a[j]`` with
``a[j + points / 2]``::

    u[j] = (a[j] + a[j + points / 2]) / 2
    v[j] = (a[j] - a[j + points / 2]) / 2 * W**j

The two halves of the frame meet there and nowhere else, because from the second
stage on the pairing distance is at most ``points / 4``, which keeps both members
of a pair inside the same half.  The architecture follows from that: a butterfly
of the first stage splits the frame into the two halves and each half is then
transformed by a delay commutator chain of its own.

Relation to the other architectures
-----------------------------------
The name has two parts and both of them say something.  ``multi path`` splits the
frame and transforms the halves side by side; the suffix says how a path is
built: ``feedback`` writes the difference of a butterfly back into the delay line
of its stage, ``commutator`` keeps the data moving forward and reorders it with
multiplexers.  So the four architectures are two independent halves of a table::

                        feedback      commutator
    single path         SDF           SDC
    multi path          MDF           MDC

and this one is the commutator counterpart of the feedback architecture next to
it: the same split, chains of the other kind.  The numbers are the same as well,
the transform does not care which hardware computes it, only the topology and
its timing differ.

Timing
------
A commutator chain is free running: it takes a sample on every cycle and stands
still only while it hands its spectrum over.  The leading butterfly can only feed
it in bursts of ``half`` cycles, because a frame has to be collected before a
sample and its partner are available together, so the chain is given an enable
and is held still for the rest of the frame - it then sees the bursts as one
continuous stream.

The chain de-permutes its spectrum while writing it into its bank, so it hands
out the natural order and the two halves interleave directly into the even and
the odd bins.  It hands the spectrum of a window over one window late, so the
first burst of a frame only fills the chains: the first real spectrum belongs to
the second frame, and the last frame stays inside the chains.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.dialects import comb
from pycde.signals import ArraySignal
from pycde.types import Bits, SInt, UInt

from .fft_butterfly import ComplexMultiplier
from .fft_model import twiddle_table
from .fft_sdc import FftSdc

SCALINGS = ("stage", "none")


@modparams
def FftMdc(width: int = 16, points: int = 16, scaling: str = "stage"):
    """The multi path delay commutator architecture of the FFT."""
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if points < 4 or (points & (points - 1)):
        raise ValueError(f"points must be a power of two and at least 4, "
                         f"got {points}")

    half = points // 2
    count_width = max(1, (points - 1).bit_length())
    half_width = max(1, (half - 1).bit_length())
    table = twiddle_table(points, width)

    class FftMdc(Module):
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
            # 0: collecting the frame, 1: feeding the two chains, 2: sending
            # the spectrum
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            cnt = Reg(UInt(count_width), io.clk, io.rst, 0, name="cnt")
            collect = Reg(UInt(half_width), io.clk, io.rst, 0, name="collect")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                            name="out_count")
            # the chains hand their spectrum over one window late: the first
            # burst of a frame has nothing to send yet
            primed = Reg(Bits(1), io.clk, io.rst, 0, name="primed")

            collecting = (phase == UInt(2)(0)).as_bits()
            feeding = (phase == UInt(2)(1)).as_bits()
            sending = (phase == UInt(2)(2)).as_bits()

            accept = io.in_valid & collecting
            last_input = (cnt == UInt(count_width)(points - 1)).as_bits()
            last_feed = (cnt == UInt(count_width)(half - 1)).as_bits()
            last_capture = (collect == UInt(half_width)(half - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            frame_done = sending & last_output & io.out_ready

            # ------------------------------------------------------------------
            # the frame
            # ------------------------------------------------------------------
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
            feed_valid = feeding & (cnt < UInt(count_width)(half)).as_bits()
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

            # the twiddle factor of the difference, the step of the first stage
            # is one, so the exponent is the position inside the half
            factor_re = SInt(width)(table[0][0])
            factor_im = SInt(width)(table[0][1])
            for k in range(1, half):
                select = (cnt == UInt(count_width)(k)).as_bits()
                factor_re = mux(select, SInt(width)(table[k][0]), factor_re)
                factor_im = mux(select, SInt(width)(table[k][1]), factor_im)

            multiplier = ComplexMultiplier(width=width)(
                a_re=diff_re.as_bits(), a_im=diff_im.as_bits(),
                b_re=factor_re.as_bits(), b_im=factor_im.as_bits())
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
            # The chains are free running, so they are held still outside the
            # burst of the leading butterfly; the bursts then follow each other
            # without a gap as far as a chain is concerned.
            even = FftSdc(width=width, points=half, scaling=scaling,
                          stallable=True)(
                              clk=io.clk, rst=io.rst,
                              in_valid=feed_valid,
                              in_real=sum_re.as_bits(), in_imag=sum_im.as_bits(),
                              in_enable=feed_valid,
                              out_ready=Bits(1)(1))
            odd = FftSdc(width=width, points=half, scaling=scaling,
                         stallable=True)(
                             clk=io.clk, rst=io.rst,
                             in_valid=feed_valid,
                             in_real=odd_re.as_bits(), in_imag=odd_im.as_bits(),
                             in_enable=feed_valid,
                             out_ready=Bits(1)(1))

            # the sample is gone when the chain really took it: a chain stands
            # still while it hands its spectrum over
            feed_accepted = feed_valid & even.in_ready
            burst_done = last_feed & feed_accepted

            # ------------------------------------------------------------------
            # the spectrum
            # ------------------------------------------------------------------
            # The chain de-permutes its spectrum while writing it into its bank,
            # so the two halves interleave directly into the even and the odd
            # bins.
            capture = feeding & even.out_valid
            spec_re = []
            spec_im = []
            for b in range(points):
                slot = b // 2
                enable = (capture
                          & (collect == UInt(half_width)(slot)).as_bits())
                source_re = even.out_real if b % 2 == 0 else odd.out_real
                source_im = even.out_imag if b % 2 == 0 else odd.out_imag
                reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"spec_re_{b}")
                reg_re.assign(source_re.as_sint())
                reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"spec_im_{b}")
                reg_im.assign(source_im.as_sint())
                spec_re.append(reg_re)
                spec_im.append(reg_im)
            spec_array_re = ArraySignal.create([r.as_bits() for r in spec_re])
            spec_array_im = ArraySignal.create([r.as_bits() for r in spec_im])
            read_index = out_count.as_bits()[:count_width]

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            burst_then_send = burst_done & primed
            burst_then_fill = burst_done & ~primed
            last_capture_now = capture & last_capture

            phase_next = phase
            phase_next = mux(collecting & last_input, UInt(2)(1), phase_next)
            phase_next = mux(burst_then_send, UInt(2)(2), phase_next)
            phase_next = mux(burst_then_fill, UInt(2)(0), phase_next)
            phase_next = mux(frame_done, UInt(2)(0), phase_next)
            phase.assign(phase_next)

            cnt_next = mux(accept | feed_accepted,
                           (cnt + UInt(count_width)(1)).as_uint(count_width),
                           cnt)
            cnt.assign(mux(burst_done | frame_done | (collecting & last_input),
                           UInt(count_width)(0), cnt_next))

            collect_next = mux(capture,
                               (collect + UInt(half_width)(1)).as_uint(
                                   half_width),
                               collect)
            collect.assign(mux(last_capture_now | burst_done,
                               UInt(half_width)(0), collect_next))

            primed.assign(mux(burst_then_fill, Bits(1)(1), primed))

            out_count_next = mux(frame_done,
                                 UInt(count_width)(0),
                                 mux(sending & io.out_ready,
                                     (out_count + UInt(count_width)(1)).as_uint(
                                         count_width),
                                     out_count))
            out_count.assign(out_count_next)

            io.in_ready = collecting
            io.out_valid = sending
            io.out_real = spec_array_re[read_index]
            io.out_imag = spec_array_im[read_index]

    FftMdc.module_name = f"FftMdc{width}P{points}"
    return FftMdc
