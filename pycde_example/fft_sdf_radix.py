"""The radix R delay feedback architecture of the FFT.

The radix 2 stage keeps one shift register of ``sub = L/2`` and works in a window
of ``L`` cycles: in the first half the samples enter the register and it hands
out the ones the previous window left, in the second half the butterfly adds them
and the difference goes back into the register.

A shift register of depth ``d`` hands out what was pushed into it ``d`` cycles
ago, so ``d`` is the time a value has to be held.  A stage of radix ``R`` has
``R`` quarters of ``sub = L/R`` cycles, and two kinds of value need holding: the
sample of quarter ``q`` takes part in the butterfly of quarter ``R - 1`` and
waits ``(R-1-q)*sub`` cycles, the difference of arm ``r`` is produced at quarter
``R - 1`` and handed out at quarter ``r - 1`` of the next window and waits
``r*sub`` cycles.  Both are the same set of durations, so the stage keeps
``R - 1`` registers, register ``k`` of depth ``k*sub``, and each carries the
sample of one quarter and the difference of one arm - what the single register of
the radix 2 stage carries in the two halves of its window.

Every register moves on every cycle, with a zero when it is not its turn, because
a shift register has to keep moving for its depth to mean a time.

One cycle of a stage: the position inside the window chooses which register is
handed out and which factor rotates it; on the last quarter of the window the
butterfly runs on the registers plus the fresh sample, its sum is handed out and
its differences go back into the registers.

The storage is ``L*(R-1)/2`` per stage against ``L/2`` at radix 2, so a uniform
radix ``R`` transform needs about ``N*R/2`` registers: a larger butterfly trades
storage for fewer stages.  The latency is ``points - 1`` for every radix.

Only the decimation in frequency is built here, which is the direction the
control of this architecture does naturally: the samples are read in the natural
order and the spectrum comes out in the mixed radix permuted one.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux, Reg
from pycde.dialects import comb
from pycde.signals import ArraySignal
from pycde.types import Bits, SInt, UInt

from .fft_butterfly import ComplexMultiplier
from .fft_model import twiddle_table
from .fft_radix_model import expand_radices, log2, mixed_reverse

SCALINGS = ("stage", "none")


@modparams
def FftSdfRadix(width: int = 16, points: int = 16, radices: str = "4",
                scaling: str = "stage"):
    """The delay feedback architecture, with a butterfly of any radix."""
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    radix_list = expand_radices(radices, points)
    if not any(radix != 2 for radix in radix_list):
        raise ValueError("the radix 2 chain is built by FftSdf; the radices "
                         f"here are {radices!r}")

    count_width = max(1, (points - 1).bit_length())
    latency = points - 1
    # the chain is fed for `points` cycles and drains for as many again
    drain_length = points
    adv_width = max(1, (latency + 2 * points).bit_length())
    table = twiddle_table(points, width)
    maximum = (1 << (width - 1)) - 1

    # the stages, each with its block, its radix and the quarter length
    stage_specs = []
    block = points
    for radix in radix_list:
        stage_specs.append((block, radix, block // radix))
        block //= radix

    def factor_of(block: int, sub: int, phase: int) -> tuple[int, int]:
        """The twiddle factor which belongs to a phase of a window."""
        quarter = phase // sub
        position = phase % sub
        exponent = (position * (quarter + 1) * (points // block)) % points
        if exponent == 0:
            return maximum, 0
        if exponent == points // 2:
            # -1, which the table cannot hold
            return -maximum, 0
        folded = exponent if exponent < points // 2 else points - exponent
        re_value, im_value = table[folded]
        if exponent > points // 2:
            # the conjugate
            im_value = -im_value
        return re_value, im_value

    class FftSdfRadix(Module):
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

            def rotate_constant(factor_re: int, factor_im: int, re, im):
                """Multiply with a factor which is known at elaboration time.

                The trivial ones are resolved here, in Python: the table cannot
                hold ``+1.0``, ``-1`` or ``-j``, and multiplying with an entry a
                unit short of them would cost a unit of the last bit.  The
                arguments have to be integers - a factor which is a signal needs
                `rotate_signal`, which decides the same three cases in hardware.
                """
                if factor_re == maximum and factor_im == 0:
                    return re, im
                if factor_re == 0 and factor_im == -maximum:
                    return im, negate(re)
                if factor_re == 0 and factor_im == maximum:
                    return negate(im), re
                if factor_re == -maximum and factor_im == 0:
                    return negate(re), negate(im)
                product = ComplexMultiplier(width=width)(
                    a_re=re.as_bits(), a_im=im.as_bits(),
                    b_re=SInt(width)(factor_re).as_bits(),
                    b_im=SInt(width)(factor_im).as_bits())
                return product.re.as_sint(), product.im.as_sint()

            def rotate_signal(factor_re, factor_im, re, im):
                """Multiply with a factor which is a signal.

                The factor is chosen by a multiplexer, so the trivial cases have
                to be decided by the hardware: the same three values the
                constant version recognises, compared here rather than in
                Python.  Reading them off the signal the multiplier uses cannot
                go out of step with it.
                """
                product = ComplexMultiplier(width=width)(
                    a_re=re.as_bits(), a_im=im.as_bits(),
                    b_re=factor_re.as_bits(), b_im=factor_im.as_bits())
                top = SInt(width)(maximum)
                zero = SInt(width)(0)
                is_one = ((factor_re == top) & (factor_im == zero)).as_bits()
                is_minus_j = ((factor_re == zero)
                              & (factor_im == -top)).as_bits()
                is_plus_j = ((factor_re == zero)
                             & (factor_im == top)).as_bits()
                is_minus_one = ((factor_re == -top)
                                & (factor_im == zero)).as_bits()
                quarter = is_minus_j | is_plus_j
                quarter_re = mux(is_minus_j, im, negate(im))
                quarter_im = mux(is_minus_j, negate(re), re)
                turned_re = mux(is_one, re,
                                mux(is_minus_one, negate(re),
                                    mux(quarter, quarter_re,
                                        product.re.as_sint())))
                turned_im = mux(is_one, im,
                                mux(is_minus_one, negate(im),
                                    mux(quarter, quarter_im,
                                        product.im.as_sint())))
                return turned_re, turned_im

            def radix_dft(values):
                """The ``R`` point transform inside a stage of radix ``R``."""
                size = len(values)
                roots = twiddle_table(size, width)
                results = []
                for out_index in range(size):
                    acc_re = None
                    acc_im = None
                    for in_index in range(size):
                        exponent = (in_index * out_index) % size
                        re, im = values[in_index]
                        if exponent == 0:
                            term_re, term_im = re, im
                        elif exponent == size // 2:
                            term_re, term_im = negate(re), negate(im)
                        elif exponent == size // 4:
                            term_re, term_im = im, negate(re)
                        elif exponent == 3 * size // 4:
                            # +j: the conjugate of -j, a swap the other way
                            # round.  A radix 2 butterfly never reaches it, so
                            # it went unnoticed until a radix 4 one did - and
                            # falling through to the table multiplies by
                            # 32767/32768, which costs a unit of the last bit.
                            term_re, term_im = negate(im), re
                        else:
                            folded = (exponent if exponent < size // 2
                                      else size - exponent)
                            w_re = roots[folded][0]
                            w_im = (roots[folded][1] if exponent < size // 2
                                    else -roots[folded][1])
                            term_re, term_im = rotate_constant(
                                w_re, w_im, re, im)
                        if acc_re is None:
                            acc_re, acc_im = term_re, term_im
                        else:
                            acc_re = (acc_re + term_re).as_sint(width)
                            acc_im = (acc_im + term_im).as_sint(width)
                    results.append((acc_re, acc_im))
                return results

            # ------------------------------------------------------------------
            # the control
            # ------------------------------------------------------------------
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            in_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                           name="in_count")
            drain_count = Reg(UInt(adv_width), io.clk, io.rst, 0,
                              name="drain_count")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                            name="out_count")
            write_count = Reg(UInt(adv_width), io.clk, io.rst, 0,
                              name="write_count")
            adv = Reg(UInt(adv_width), io.clk, io.rst, 0, name="adv")

            receiving = (phase == UInt(2)(0)).as_bits()
            draining = (phase == UInt(2)(1)).as_bits()
            sending = (phase == UInt(2)(2)).as_bits()

            accept = io.in_valid & receiving
            last_input = (in_count == UInt(count_width)(points - 1)).as_bits()
            # The chain hands a result out on every cycle once it is filled, so
            # the drain lasts `points` cycles and not `latency`: the first
            # result appears after `latency` cycles and the last one `points`
            # cycles later.
            last_drain = (drain_count
                          == UInt(adv_width)(drain_length - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            frame_done = sending & last_output & io.out_ready

            advance = accept | draining
            chain_valid = (adv >= UInt(adv_width)(latency)).as_bits()

            # ------------------------------------------------------------------
            # the chain of the stages
            # ------------------------------------------------------------------
            value_re = io.in_real.as_sint()
            value_im = io.in_imag.as_sint()

            for s, (block, radix, sub) in enumerate(stage_specs):
                sub_bits = log2(sub)
                quarter_bits = max(1, log2(radix))
                phase_width = max(1, (block - 1).bit_length())

                stage_phase = Reg(UInt(phase_width), io.clk, io.rst, 0,
                                  name=f"phase{s}")
                phase_next = mux(
                    advance,
                    (stage_phase + UInt(phase_width)(1)).as_uint(phase_width),
                    stage_phase)
                stage_phase.assign(mux(frame_done, UInt(phase_width)(0),
                                       phase_next))

                # the position inside the window is a bit slice, since a
                # quarter is a power of two long
                if sub_bits:
                    quarter = stage_phase.as_bits()[sub_bits:].as_uint(
                        quarter_bits)
                else:
                    # a quarter is a single cycle long, so the phase inside
                    # the window is the quarter itself
                    quarter = stage_phase.as_uint(quarter_bits)
                last_quarter = (quarter == UInt(quarter_bits)(radix - 1))
                last_quarter_bit = last_quarter.as_bits()

                fresh_re = value_re
                fresh_im = value_im
                if scaling == "stage":
                    fresh_re = shift_right(fresh_re, log2(radix))
                    fresh_im = shift_right(fresh_im, log2(radix))

                # the registers of the arms, declared before anything reads
                # them; register k has depth k * sub
                lines = []
                taps = []
                for k in range(1, radix):
                    depth = k * sub
                    line_re = []
                    line_im = []
                    for i in range(depth):
                        reg_re = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance, name=f"arm{s}_{k}_re_{i}")
                        reg_im = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance, name=f"arm{s}_{k}_im_{i}")
                        line_re.append(reg_re)
                        line_im.append(reg_im)
                    lines.append((line_re, line_im))
                    taps.append((line_re[-1], line_im[-1]))

                # the butterfly on the last quarter
                operands = [taps[k - 1] for k in range(radix - 1, 0, -1)]
                operands.append((fresh_re, fresh_im))
                transformed = radix_dft(operands)

                # the register which is handed out, chosen by the quarter
                handed_re, handed_im = taps[0]
                for q in range(2, radix):
                    hit = (quarter == UInt(quarter_bits)(q - 1)).as_bits()
                    handed_re = mux(hit, taps[q - 1][0], handed_re)
                    handed_im = mux(hit, taps[q - 1][1], handed_im)

                # the factor of this phase, chosen by the phase itself
                factor_re, factor_im = factor_of(block, sub, 0)
                for p in range(1, block):
                    hit = (stage_phase == UInt(phase_width)(p)).as_bits()
                    choice_re, choice_im = factor_of(block, sub, p)
                    factor_re = mux(hit, SInt(width)(choice_re),
                                    SInt(width)(factor_re))
                    factor_im = mux(hit, SInt(width)(choice_im),
                                    SInt(width)(factor_im))
                rotated_re, rotated_im = rotate_signal(
                    factor_re, factor_im, handed_re, handed_im)

                stage_out_re = mux(last_quarter_bit, transformed[0][0],
                                   rotated_re)
                stage_out_im = mux(last_quarter_bit, transformed[0][1],
                                   rotated_im)

                # the write back, after everything which reads the registers
                for k in range(1, radix):
                    line_re, line_im = lines[k - 1]
                    carries = (quarter
                               == UInt(quarter_bits)(radix - 1 - k)).as_bits()
                    keep_re = mux(carries, fresh_re, SInt(width)(0))
                    keep_im = mux(carries, fresh_im, SInt(width)(0))
                    head_re = mux(last_quarter_bit, transformed[k][0], keep_re)
                    head_im = mux(last_quarter_bit, transformed[k][1], keep_im)
                    line_re[0].assign(head_re)
                    line_im[0].assign(head_im)
                    for i in range(1, len(line_re)):
                        line_re[i].assign(line_re[i - 1])
                        line_im[i].assign(line_im[i - 1])

                value_re = stage_out_re
                value_im = stage_out_im

            # ------------------------------------------------------------------
            # the spectrum
            # ------------------------------------------------------------------
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

            # the chain hands its spectrum out permuted, the buffer is read in
            # the natural order
            read_addr = Bits(count_width)(0)
            for i in range(points):
                target = mixed_reverse(i, radix_list)
                read_addr = mux(out_count == UInt(count_width)(target),
                                Bits(count_width)(i), read_addr)
            buf_array_re = ArraySignal.create([r.as_bits() for r in buf_re])
            buf_array_im = ArraySignal.create([r.as_bits() for r in buf_im])

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            phase_next = phase
            phase_next = mux(receiving & last_input, UInt(2)(1), phase_next)
            phase_next = mux(draining & last_drain, UInt(2)(2), phase_next)
            phase_next = mux(frame_done, UInt(2)(0), phase_next)
            phase.assign(phase_next)

            in_count_next = mux(accept,
                                (in_count + UInt(count_width)(1)).as_uint(
                                    count_width),
                                in_count)
            in_count.assign(mux(frame_done, UInt(count_width)(0),
                                in_count_next))

            drain_count_next = mux(draining,
                                   (drain_count + UInt(adv_width)(1)).as_uint(
                                       adv_width),
                                   drain_count)
            drain_count.assign(mux(frame_done, UInt(adv_width)(0),
                                   drain_count_next))

            out_count_next = mux(sending & io.out_ready,
                                 (out_count + UInt(count_width)(1)).as_uint(
                                     count_width),
                                 out_count)
            out_count.assign(mux(frame_done, UInt(count_width)(0),
                                 out_count_next))

            write_count_next = mux(write_enable,
                                   (write_count + UInt(adv_width)(1)).as_uint(
                                       adv_width),
                                   write_count)
            write_count.assign(mux(frame_done, UInt(adv_width)(0),
                                   write_count_next))

            adv.assign(mux(frame_done, UInt(adv_width)(0),
                           mux(advance,
                               (adv + UInt(adv_width)(1)).as_uint(adv_width),
                               adv)))

            io.in_ready = receiving
            io.out_valid = sending
            io.out_real = buf_array_re[read_addr]
            io.out_imag = buf_array_im[read_addr]

    FftSdfRadix.module_name = f"FftSdfRadix{width}P{points}"
    return FftSdfRadix
