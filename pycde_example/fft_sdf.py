"""The single path delay feedback (SDF) architecture of the FFT.

The transform is folded into a chain of stages which are fed back into
themselves: every stage owns a delay line (a shift register) and a butterfly.
The difference of the butterfly is written back into the delay line of the
stage, the sum is forwarded to the next stage.  The data of a frame is
therefore transformed while it flows through the chain, one butterfly per
cycle.

The architecture is streaming: the samples of a frame are fed into it one by
one, the spectrum leaves it one by one.  The frame based interface of the
transform is built on top of it: the samples are collected in a register
array, the spectrum is read from it in the natural order.

The decimation in frequency (the default) reads the samples in the natural
order and produces the spectrum bit reversed, the decimation in time reads
the samples bit reversed (they are collected in a register array first) and
produces the spectrum in the natural order.

The bit exact reference of the architecture is in ``fft_sdf_model``.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.dialects import comb
from pycde.signals import ArraySignal
from pycde.types import Bits, SInt, UInt

from .fft_butterfly import Butterfly, ComplexMultiplier
from .fft_model import twiddle_table

ORDERINGS = ("dit", "dif")
SCALINGS = ("stage", "none")


@modparams
def FftSdf(width: int = 16, points: int = 16, ordering: str = "dif",
           scaling: str = "stage", stages: int = 1):
    """The delay feedback architecture of the FFT.

    ``stages`` is the number of registers between two stages, they are part
    of the latency of the transform.
    """
    if ordering not in ORDERINGS:
        raise ValueError(f"ordering must be one of {ORDERINGS}, got {ordering!r}")
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if stages < 0:
        raise ValueError(f"stages must not be negative, got {stages}")
    if points < 2 or (points & (points - 1)):
        raise ValueError(f"points must be a power of two, got {points}")

    levels = points.bit_length() - 1
    dit = ordering == "dit"
    count_width = max(1, (points - 1).bit_length())
    # the number of cycles the transform needs: the data has to travel
    # through the whole chain of delay lines
    latency = points - 1 + levels * stages
    # the number of cycles the pipeline is drained after the frame was fed
    drain_length = points - 1 + levels * stages
    adv_width = max(1, (latency + points).bit_length())
    table = twiddle_table(points, width)

    if dit:
        # the decimation in time processes the small butterflies first
        delays = [1 << s for s in range(levels)]
        step_sizes = [1 << (levels - 1 - s) for s in range(levels)]
    else:
        # the decimation in frequency processes the large butterflies first
        delays = [1 << s for s in range(levels)][::-1]
        step_sizes = [1 << s for s in range(levels)]
    # the window of a stage is offset by the delays of the previous stages
    # and by the latency of the registers between them
    offsets = [sum(delays[:i]) + i * stages for i in range(levels)]

    class FftSdf(Module):
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

            def negate(value):
                """The negation of a signed value, in the same width."""
                wide = value.as_sint(width + 1)
                return (SInt(width + 1)(0) - wide).as_sint(width)

            def permute(index: int) -> int:
                """The bit reversed index."""
                return int(f"{index:0{levels}b}"[::-1], 2)

            # ------------------------------------------------------------------
            # the control
            # ------------------------------------------------------------------
            # 0: receiving the frame, 1: feeding the chain (the decimation in
            # time reads the samples bit reversed), 2: draining the pipeline,
            # 3: sending the result
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            in_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="in_count")
            feed_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="feed_count")
            drain_count = Reg(UInt(adv_width), io.clk, io.rst, 0, name="drain_count")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="out_count")
            write_count = Reg(UInt(adv_width), io.clk, io.rst, 0, name="write_count")
            # the number of cycles the chain was advanced
            adv = Reg(UInt(adv_width), io.clk, io.rst, 0, name="adv")

            receiving = (phase == UInt(2)(0)).as_bits()
            feeding = (phase == UInt(2)(1)).as_bits()
            draining = (phase == UInt(2)(2)).as_bits()
            sending = (phase == UInt(2)(3)).as_bits()

            accept = io.in_valid & receiving
            last_input = (in_count == UInt(count_width)(points - 1)).as_bits()
            last_feed = (feed_count == UInt(count_width)(points - 1)).as_bits()
            last_drain = (drain_count == UInt(adv_width)(drain_length - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            # the result of the frame was sent: the next frame can be
            # received
            frame_done = sending & last_output & io.out_ready

            if dit:
                # the samples are collected before they are fed into the
                # chain
                advance = feeding | draining
            else:
                # the samples are fed into the chain while they arrive
                advance = (receiving & io.in_valid) | draining

            # the chain produces the result of the frame after the latency
            # of the architecture
            chain_valid = (adv >= UInt(adv_width)(latency)).as_bits()

            # ------------------------------------------------------------------
            # the samples which are fed into the chain
            # ------------------------------------------------------------------
            value_re = io.in_real.as_sint()
            value_im = io.in_imag.as_sint()
            if dit:
                # the decimation in time reads the samples bit reversed: they
                # are collected in a register array first
                in_addr = in_count.as_bits()
                in_enable = accept
                in_re = []
                in_im = []
                for i in range(points):
                    enable = (in_addr == Bits(count_width)(i)) & in_enable
                    reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"in_re_{i}")
                    reg_re.assign(io.in_real.as_sint())
                    reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"in_im_{i}")
                    reg_im.assign(io.in_imag.as_sint())
                    in_re.append(reg_re)
                    in_im.append(reg_im)
                # the samples are fed in the bit reversed order
                feed_addr = Bits(count_width)(0)
                for i in range(points):
                    feed_addr = mux(feed_count == UInt(count_width)(permute(i)),
                                    Bits(count_width)(i), feed_addr)
                in_array_re = ArraySignal.create([r.as_bits() for r in in_re])
                in_array_im = ArraySignal.create([r.as_bits() for r in in_im])
                value_re = in_array_re[feed_addr].as_sint()
                value_im = in_array_im[feed_addr].as_sint()

            # ------------------------------------------------------------------
            # the chain of the stages
            # ------------------------------------------------------------------
            for s in range(levels):
                delay = delays[s]
                step_size = step_sizes[s]
                offset = offsets[s]
                phase_width = max(1, (2 * delay - 1).bit_length())

                # the window of the stage is 2 * delay cycles long, the first
                # half of it loads the delay line
                stage_phase = Reg(UInt(phase_width), io.clk, io.rst,
                                  (-offset) % (2 * delay), name=f"phase_{s}")
                stage_phase_next = mux(
                    advance,
                    (stage_phase + UInt(phase_width)(1)).as_uint(phase_width),
                    stage_phase)
                # the next frame starts with the initial phase of the stage
                stage_phase_next = mux(
                    frame_done,
                    UInt(phase_width)((-offset) % (2 * delay)),
                    stage_phase_next)
                stage_phase.assign(stage_phase_next)
                # the stage loads its delay line while the phase is below the
                # length of the delay line
                load = (stage_phase < UInt(phase_width)(delay)).as_bits()

                # the delay line of the stage
                delay_re = []
                delay_im = []
                for i in range(delay):
                    reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=advance,
                                 name=f"delay{s}_re_{i}")
                    reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=advance,
                                 name=f"delay{s}_im_{i}")
                    delay_re.append(reg_re)
                    delay_im.append(reg_im)
                delayed_re = delay_re[-1]
                delayed_im = delay_im[-1]

                # the fresh value of the stage, the operands of the butterfly
                # are halved before they are added
                fresh_re = value_re
                fresh_im = value_im
                if scaling == "stage":
                    fresh_re = shift_right(fresh_re, 1)
                    fresh_im = shift_right(fresh_im, 1)

                # the twiddle factor of the stage
                if dit:
                    # the twiddle factor multiplies the fresh value of the
                    # stage, it is used during the second half of the window
                    index = (stage_phase - UInt(phase_width)(delay)).as_uint(
                        phase_width)
                else:
                    # the twiddle factor multiplies the data which leaves the
                    # delay line
                    index = stage_phase
                twiddle_re = None
                twiddle_im = None
                for k in range(delay):
                    select = (index == UInt(phase_width)(k)).as_bits()
                    factor_re = SInt(width)(table[k * step_size][0])
                    factor_im = SInt(width)(table[k * step_size][1])
                    twiddle_re = (factor_re if twiddle_re is None
                                  else mux(select, factor_re, twiddle_re))
                    twiddle_im = (factor_im if twiddle_im is None
                                  else mux(select, factor_im, twiddle_im))

                # the value which is rotated with the twiddle factor
                rotate_re = fresh_re if dit else delayed_re
                rotate_im = fresh_im if dit else delayed_im
                multiplier = ComplexMultiplier(width=width)(
                    a_re=rotate_re.as_bits(), a_im=rotate_im.as_bits(),
                    b_re=twiddle_re.as_bits(), b_im=twiddle_im.as_bits())
                # The trivial factors are applied exactly, as a wire and as a
                # swap with a negation: the table cannot hold +1.0, so
                # multiplying with its first entry would lose a unit of the
                # last bit in every stage which uses W**0.
                # `index` is the position inside the window; the exponent of
                # the factor is that position times the step of the stage, which
                # is what the table lookup uses.  The trivial ones have to be
                # compared as exponents.
                exponent = (index.as_uint(count_width)
                            * UInt(count_width)(step_size)).as_uint(count_width)
                no_twiddle = (exponent == UInt(count_width)(0)).as_bits()
                quarter = (exponent
                           == UInt(count_width)(points // 4)).as_bits()
                rotated_re = mux(no_twiddle, rotate_re,
                                 mux(quarter, rotate_im, multiplier.re.as_sint()))
                rotated_im = mux(no_twiddle, rotate_im,
                                 mux(quarter, negate(rotate_re),
                                     multiplier.im.as_sint()))
                if dit:
                    butterfly_re = rotated_re.as_bits()
                    butterfly_im = rotated_im.as_bits()
                else:
                    butterfly_re = fresh_re.as_bits()
                    butterfly_im = fresh_im.as_bits()

                # the butterfly: the delayed operand and the fresh value of
                # the stage, the twiddle factor is not applied by it
                butterfly = Butterfly(width=width, scaling="none",
                                      twiddle_position="none")(
                                          a_re=delayed_re.as_bits(),
                                          a_im=delayed_im.as_bits(),
                                          b_re=butterfly_re,
                                          b_im=butterfly_im,
                                          w_re=Bits(width)(0),
                                          w_im=Bits(width)(0))

                # the output of the stage: while the delay line is loaded the
                # delayed data is forwarded, afterwards the sum of the
                # butterfly is
                if dit:
                    stage_out_re = mux(load, delayed_re,
                                      butterfly.sum_re.as_sint())
                    stage_out_im = mux(load, delayed_im,
                                      butterfly.sum_im.as_sint())
                else:
                    stage_out_re = mux(load, multiplier.re.as_sint(),
                                      butterfly.sum_re.as_sint())
                    stage_out_im = mux(load, multiplier.im.as_sint(),
                                      butterfly.sum_im.as_sint())

                # the difference of the butterfly is fed back into the delay
                # line of the stage
                shift_in_re = mux(load, fresh_re, butterfly.diff_re.as_sint())
                shift_in_im = mux(load, fresh_im, butterfly.diff_im.as_sint())
                delay_re[0].assign(shift_in_re)
                delay_im[0].assign(shift_in_im)
                for i in range(1, delay):
                    delay_re[i].assign(delay_re[i - 1])
                    delay_im[i].assign(delay_im[i - 1])

                # the registers between two stages
                value_re = stage_out_re
                value_im = stage_out_im
                for i in range(stages):
                    value_re = value_re.reg(io.clk, io.rst, ce=advance,
                                            name=f"stage{s}_re_{i}")
                    value_im = value_im.reg(io.clk, io.rst, ce=advance,
                                            name=f"stage{s}_im_{i}")

            # ------------------------------------------------------------------
            # the spectrum
            # ------------------------------------------------------------------
            # The spectrum is collected in a register array, it is read from
            # it in the natural order.
            write_addr = write_count.as_bits()[:count_width]
            write_enable = (chain_valid & advance
                            & (write_count < UInt(adv_width)(points)).as_bits())
            buf_re = []
            buf_im = []
            for i in range(points):
                enable = (write_addr == Bits(count_width)(i)) & write_enable
                reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"buf_re_{i}")
                reg_re.assign(value_re)
                reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                             name=f"buf_im_{i}")
                reg_im.assign(value_im)
                buf_re.append(reg_re)
                buf_im.append(reg_im)

            if dit:
                # the decimation in time produces the spectrum in the natural
                # order
                read_addr = out_count.as_bits()
            else:
                # the decimation in frequency produces the spectrum bit
                # reversed
                read_addr = Bits(count_width)(0)
                for i in range(points):
                    read_addr = mux(out_count == UInt(count_width)(permute(i)),
                                    Bits(count_width)(i), read_addr)
            buf_array_re = ArraySignal.create([r.as_bits() for r in buf_re])
            buf_array_im = ArraySignal.create([r.as_bits() for r in buf_im])

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            phase_next = phase
            if dit:
                # the frame was received: the samples are fed into the chain
                phase_next = mux(receiving & last_input, UInt(2)(1), phase_next)
                # the samples were fed: the pipeline is drained
                phase_next = mux(feeding & last_feed, UInt(2)(2), phase_next)
            else:
                # the frame was received: the pipeline is drained
                phase_next = mux(receiving & last_input, UInt(2)(2), phase_next)
            # the pipeline is drained: the result is sent
            phase_next = mux(draining & last_drain, UInt(2)(3), phase_next)
            # the result was sent: the next frame is received
            phase_next = mux(frame_done, UInt(2)(0), phase_next)

            in_count_next = mux(accept,
                                (in_count + UInt(count_width)(1)).as_uint(
                                    count_width),
                                in_count)
            feed_count_next = mux(feeding & advance,
                                  (feed_count + UInt(count_width)(1)).as_uint(
                                      count_width),
                                  feed_count)
            drain_count_next = mux(draining,
                                    (drain_count + UInt(adv_width)(1)).as_uint(
                                        adv_width),
                                    drain_count)
            out_count_next = mux(sending & io.out_ready,
                                 (out_count + UInt(count_width)(1)).as_uint(
                                     count_width),
                                 out_count)
            write_count_next = mux(write_enable,
                                   (write_count + UInt(adv_width)(1)).as_uint(
                                       adv_width),
                                   write_count)
            adv_next = mux(advance,
                           (adv + UInt(adv_width)(1)).as_uint(adv_width),
                           adv)

            # the next frame starts at the first sample
            in_count_next = mux(frame_done, UInt(count_width)(0), in_count_next)
            feed_count_next = mux(frame_done, UInt(count_width)(0),
                                  feed_count_next)
            drain_count_next = mux(frame_done, UInt(adv_width)(0),
                                   drain_count_next)
            out_count_next = mux(frame_done, UInt(count_width)(0),
                                 out_count_next)
            write_count_next = mux(frame_done, UInt(adv_width)(0),
                                   write_count_next)
            adv_next = mux(frame_done, UInt(adv_width)(0), adv_next)

            phase.assign(phase_next)
            in_count.assign(in_count_next)
            feed_count.assign(feed_count_next)
            drain_count.assign(drain_count_next)
            out_count.assign(out_count_next)
            write_count.assign(write_count_next)
            adv.assign(adv_next)

            # ------------------------------------------------------------------
            # the interface
            # ------------------------------------------------------------------
            io.in_ready = receiving
            io.out_valid = sending
            io.out_real = buf_array_re[read_addr]
            io.out_imag = buf_array_im[read_addr]

    FftSdf.module_name = f"FftSdf{width}P{points}S{stages}"
    return FftSdf
