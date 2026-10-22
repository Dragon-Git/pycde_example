"""The single path delay commutator (SDC) architecture of the FFT.

Relation to the delay feedback architecture
-------------------------------------------
``fft_sdf`` and this module are two hardware mappings of the same transform
(the radix-2 decimation in frequency).  They share the butterfly arithmetic
and the mathematical definition of the twiddle factors, but the pipelines are
not two variants of one structure - they are two different pipeline
organisations:

* the delay feedback chain is a **feedback** structure: the sum of a butterfly
  is forwarded to the next stage and the difference is written back into the
  shift register of the *same* stage, from which it returns to the same
  butterfly a few cycles later.  The butterfly is time shared between the two
  roles, its utilisation is about one half, and the storage is ``points - 1``
  registers.
* the delay commutator chain is a **feed forward, commutating** structure:
  there is no loop at all.  A commutator - a multiplexer together with a delay
  line - rearranges the stream, so that one word per cycle leaves every stage.
  The storage is ``2 * points - 2`` registers, roughly twice the one of the
  delay feedback chain, and the control is a commutator schedule rather than
  write enables of a feedback register.

The arithmetic core is shared, the pipeline organisation is not.

The structure of a stage
------------------------
* the stage 0 pairs the input with the input delayed by ``points / 2``; it has
  no commutator, because both of its outputs are consumed by the next stage,
* every other stage multiplies the difference of the previous stage with the
  twiddle factor of the stage, delays it and hands it to the commutator, which
  swaps it with the sum of the previous stage; the commutator is driven by one
  bit of the frame counter,
* the butterfly of the stage combines the delayed first output of the
  commutator with its second output, the operands are halved before they are
  added,
* the last stage rotates with a trivial rotator, its factor is ``-j``.

The output stage
----------------
The sum of the last stage and its difference delayed by ``points / 2`` are
interleaved by a multiplexer whose selection is the valid signal of the
architecture, delayed by the whole latency ``points - 1``.  The window of the
multiplexer is therefore **rotated by ``points - 1``** with respect to the frame
counter.

The architecture is a streaming pipeline: the frames are fed back to back, the
delay lines hold the data of the previous frame while the current one is
processed, so a frame must not be followed by zeros.  That is why the input is
accepted on every cycle.

The spectrum of a frame leaves the chain in the ``points`` cycles of its
rotated window.  Two banks of registers hold the spectra: the chain writes into
one while the other one is read out, which is what allows the transform to run
without pauses.  The output stream inside a window is bit reversed and
interleaved, the banks let the interface present the spectrum in the natural
order.

The bit exact reference of the architecture is in ``fft_sdc_model``.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.signals import ArraySignal, BitsSignal
from pycde.types import Bits, SInt, UInt

from .fft_butterfly import Butterfly, ComplexMultiplier
from .fft_model import twiddle_table
from .fft_sdc_model import output_order

SCALINGS = ("stage", "none")


@modparams
def CommutatorSchedule(period: int = 4):
    """The control of a commutator: the selection of its two multiplexers.

    A commutator is a pair of multiplexers driven by a periodic selection: in
    the first half of its window it passes the sum of the previous stage
    through and hands the delayed difference to the delay line, in the second
    half it swaps them.  Every stage owns its own schedule, derived from the
    position of the stage inside the frame.

    The schedule is a module of its own because the delay feedback chain has no
    counterpart of it: there a stage needs nothing but the write enable of a
    register.

    The multiplexers themselves sit in the data path of the stage, where the
    rotated and delayed difference exists; this module only produces their
    selection.
    """
    period_width = max(1, (period - 1).bit_length())
    half = max(1, period // 2)

    class CommutatorSchedule(Module):
        # the position inside the window of the stage
        position = Input(Bits(period_width))
        # the selection of the two multiplexers of the stage
        select = Output(Bits(1))

        @generator
        def construct(io):
            io.select = (io.position >= Bits(period_width)(half)).as_bits()

    return CommutatorSchedule


@modparams
def FftSdc(width: int = 16, points: int = 16, scaling: str = "stage"):
    """The delay commutator architecture of the FFT."""
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if points < 4 or (points & (points - 1)):
        raise ValueError(f"points must be a power of two and at least 4, "
                         f"got {points}")

    levels = points.bit_length() - 1
    half = points // 2
    index_width = max(1, levels - 1)
    table = twiddle_table(points, width)
    count_width = max(1, (points - 1).bit_length())
    order = output_order(points)

    class FftSdc(Module):
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

            # ------------------------------------------------------------------
            # the control of the chain
            # ------------------------------------------------------------------
            # The chain is free running, the frames follow each other without
            # a gap.  `cnt` is the position inside the frame; it drives the
            # commutators and the indices of the twiddle factors.
            cnt = Reg(UInt(count_width), io.clk, io.rst, 0, name="cnt")
            # the index of the completed window, its lowest bit is the bank
            window = Reg(Bits(1), io.clk, io.rst, 0, name="window")
            # the number of cycles the chain ran, saturating: the first window
            # is only meaningful when the chain is filled
            fill = Reg(UInt(count_width), io.clk, io.rst, 0, name="fill")
            # set when the first window was completed: from then on the bank
            # of the previous window holds a complete spectrum
            started = Reg(Bits(1), io.clk, io.rst, 0, name="started")

            # ------------------------------------------------------------------
            # the chain of the stages
            # ------------------------------------------------------------------
            def delay_line(name, depth, value_re, value_im):
                """A shift register of `depth` entries (the chain advances
                every cycle)."""
                regs_re = []
                regs_im = []
                for i in range(depth):
                    reg_re = Reg(SInt(width), io.clk, io.rst, 0,
                                 name=f"{name}_re_{i}")
                    reg_im = Reg(SInt(width), io.clk, io.rst, 0,
                                 name=f"{name}_im_{i}")
                    regs_re.append(reg_re)
                    regs_im.append(reg_im)
                regs_re[0].assign(value_re)
                regs_im[0].assign(value_im)
                for i in range(1, depth):
                    regs_re[i].assign(regs_re[i - 1])
                    regs_im[i].assign(regs_im[i - 1])
                return regs_re[-1], regs_im[-1]

            def butterfly_of(a_re, a_im, b_re, b_im):
                unit = Butterfly(width=width, scaling=scaling,
                                 twiddle_position="none")(
                                     a_re=a_re.as_bits(), a_im=a_im.as_bits(),
                                     b_re=b_re.as_bits(), b_im=b_im.as_bits(),
                                     w_re=Bits(width)(0), w_im=Bits(width)(0))
                return (unit.sum_re.as_sint(), unit.sum_im.as_sint(),
                        unit.diff_re.as_sint(), unit.diff_im.as_sint())

            # the stage 0 pairs the input with the input delayed by points / 2
            value_re = io.in_real.as_sint()
            value_im = io.in_imag.as_sint()
            delayed_re, delayed_im = delay_line("line0", half, value_re,
                                                value_im)
            e_re, e_im, o_re, o_im = butterfly_of(delayed_re, delayed_im,
                                                  value_re, value_im)

            for s in range(1, levels):
                depth = max(1, points >> (s + 1))
                # the twiddle factor of the stage: the index is a slice of the
                # frame position, the exponent advances by 2**(s - 1)
                low_bits = cnt.as_bits()[:levels - s]
                if s == 1:
                    tw_index = low_bits
                else:
                    tw_index = BitsSignal.concat([low_bits, Bits(s - 1)(0)])
                tw_re = None
                tw_im = None
                for k in range(half):
                    hit = (tw_index == Bits(index_width)(k)).as_bits()
                    factor_re = SInt(width)(table[k][0])
                    factor_im = SInt(width)(table[k][1])
                    tw_re = (factor_re if tw_re is None
                             else mux(hit, factor_re, tw_re))
                    tw_im = (factor_im if tw_im is None
                             else mux(hit, factor_im, tw_im))

                # the commutator of the stage, driven by the position inside
                # its own window
                # The window of the stage is a power of two, so the position
                # inside it is a slice of the counter: PyCDE has no modulo
                # operator for signals.
                period = 2 * depth
                period_width = max(1, (period - 1).bit_length())
                position = cnt.as_bits()[:period_width]
                schedule = CommutatorSchedule(period=period)(position=position)
                sel_bit = schedule.select

                if s == levels - 1:
                    # the last stage rotates with a trivial rotator: -j
                    rot_re = mux(sel_bit, o_im, o_re)
                    rot_im = mux(sel_bit, -o_re, o_im)
                else:
                    multiplier = ComplexMultiplier(width=width)(
                        a_re=o_re.as_bits(), a_im=o_im.as_bits(),
                        b_re=tw_re.as_bits(), b_im=tw_im.as_bits())
                    rot_re = multiplier.re.as_sint()
                    rot_im = multiplier.im.as_sint()

                # the delay line of the rotated difference: it is what the
                # commutator swaps in
                rotated_re, rotated_im = delay_line(f"rot{s}", depth, rot_re,
                                                    rot_im)
                m0_re = mux(sel_bit, rotated_re, e_re)
                m0_im = mux(sel_bit, rotated_im, e_im)
                m1_re = mux(sel_bit, e_re, rotated_re)
                m1_im = mux(sel_bit, e_im, rotated_im)
                # the first operand of the butterfly is itself delayed
                m0d_re, m0d_im = delay_line(f"line{s}", depth, m0_re, m0_im)

                e_re, e_im, o_re, o_im = butterfly_of(m0d_re, m0d_im, m1_re,
                                                      m1_im)

            # ------------------------------------------------------------------
            # the output multiplexer of the chain
            # ------------------------------------------------------------------
            # Its selection is the valid signal of the architecture, delayed by
            # the latency points - 1, so the window is rotated by that amount.
            delayed_o_re, delayed_o_im = delay_line("line_out", half, o_re, o_im)
            # (cnt - (points - 1)) modulo points, and a subtraction of
            # points - 1 is an addition of one modulo points.  The number of
            # points is a power of two, so the modulo is a bit slice.
            rotated_count = ((cnt + UInt(count_width)(1)).as_uint(count_width)
                             .as_bits()[:count_width]).as_uint(count_width)
            first_half = (rotated_count < UInt(count_width)(half)).as_bits()
            chain_re = mux(first_half, e_re, delayed_o_re)
            chain_im = mux(first_half, e_im, delayed_o_im)

            # ------------------------------------------------------------------
            # the two banks of spectra
            # ------------------------------------------------------------------
            # The window of the output multiplexer is `points` cycles long.
            # The frame writes into the bank of its window while the other
            # bank - the one of the previous window - is read out at the same
            # position.  Both are aligned with the window, so no handshake is
            # needed between the capture and the readout.
            filled = (fill == UInt(count_width)(points - 1)).as_bits()
            write_bank = window
            read_bank = ~write_bank
            buf_re = [[], []]
            buf_im = [[], []]
            for bank_index in range(2):
                for bin_index in range(points):
                    slot = order.index(bin_index)
                    enable = (write_bank == Bits(1)(bank_index)).as_bits() \
                        & (rotated_count
                           == UInt(count_width)(slot)).as_bits() \
                        & filled
                    reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"buf{bank_index}_re_{bin_index}")
                    reg_re.assign(chain_re)
                    reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"buf{bank_index}_im_{bin_index}")
                    reg_im.assign(chain_im)
                    buf_re[bank_index].append(reg_re)
                    buf_im[bank_index].append(reg_im)

            array_re = [ArraySignal.create([r.as_bits() for r in buf_re[b]])
                        for b in range(2)]
            array_im = [ArraySignal.create([r.as_bits() for r in buf_im[b]])
                        for b in range(2)]
            out_real = mux(read_bank, array_re[1][rotated_count.as_bits()],
                           array_re[0][rotated_count.as_bits()])
            out_imag = mux(read_bank, array_im[1][rotated_count.as_bits()],
                           array_im[0][rotated_count.as_bits()])

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            last_input = (cnt == UInt(count_width)(points - 1)).as_bits()
            last_in_window = (rotated_count
                              == UInt(count_width)(points - 1)).as_bits()
            cnt_next = mux(last_input, UInt(count_width)(0),
                           (cnt + UInt(count_width)(1)).as_uint(count_width))
            # the window index counts the completed windows, its lowest bit is
            # the bank
            window_next = mux(filled & last_in_window, ~window, window)
            fill_next = mux(filled, fill,
                            (fill + UInt(count_width)(1)).as_uint(count_width))
            started_next = mux(filled & last_in_window, Bits(1)(1), started)

            cnt.assign(cnt_next)
            window.assign(window_next)
            fill.assign(fill_next)
            started.assign(started_next)

            # ------------------------------------------------------------------
            # the interface
            # ------------------------------------------------------------------
            # The chain is free running, so a sample is accepted on every
            # cycle: the frames have to be supplied back to back.
            io.in_ready = Bits(1)(1)
            # the spectrum of the previous window is complete from the end of
            # the first window on (the window bit alone is not enough: it
            # selects the bank, it does not mark the first window)
            io.out_valid = filled & started
            io.out_real = out_real
            io.out_imag = out_imag

    FftSdc.module_name = f"FftSdc{width}P{points}"
    return FftSdc
