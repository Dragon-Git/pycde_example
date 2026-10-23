"""The radix R delay commutator architecture of the FFT.

The radix 2 commutator stage differs from the feedback one in a single thing: the
difference of the butterfly is not written back into a delay line, it is
forwarded.  The stage therefore keeps two kinds of line - the ones which hold the
samples until the butterfly can run, and the ones which delay the results until
it is their turn to leave - and a multiplexer puts them in order.  Nothing is fed
back, so the chain is a pipeline of the same depth with no loop in it.

The timing is the one of the feedback stage: a stage of radix `R` has `R` quarters
of `sub = L/R` cycles, the sample of quarter `q` waits `(R-1-q)*sub` cycles for
the butterfly, and the result of arm `r` leaves at quarter `r` of the next
window.  The number of registers is `L*(R-1)/2` per stage and the latency is
`points - 1`, the same as the feedback chain - what differs is the shape of the
datapath, not its arithmetic.

The chain is a free running pipeline: it takes a sample on every cycle and only
stands still while it hands its spectrum over.  The `stallable` input lets an
outer control hold it still, which is what an architecture built out of several
chains needs.

The two banks of spectra are written in the permuted order the chain produces and
read in the natural one, so a frame can be filled while the previous one is sent.
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
def FftSdcRadix(width: int = 16, points: int = 16, radices: str = "4",
                scaling: str = "stage", stallable: bool = False):
    """The delay commutator architecture, with a butterfly of any radix."""
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    radix_list = expand_radices(radices, points)
    if not any(radix != 2 for radix in radix_list):
        raise ValueError("the radix 2 chain is built by FftSdc; the radices "
                         f"here are {radices!r}")

    count_width = max(1, (points - 1).bit_length())
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
            im_value = -im_value
        return re_value, im_value

    class FftSdcRadix(Module):
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
        if stallable:
            in_enable = Input(Bits(1))

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
                """Multiply with a factor which is known at elaboration time."""
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

                The factor is chosen by a multiplexer, so the trivial cases are
                decided by the hardware - the same three values the constant
                version recognises.
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
                        else:
                            folded = (exponent if exponent < size // 2
                                      else size - exponent)
                            w_re = roots[folded][0]
                            w_im = (roots[folded][1] if exponent < size // 2
                                    else -roots[folded][1])
                            term_re, term_im = rotate_constant(w_re, w_im,
                                                               re, im)
                        if acc_re is None:
                            acc_re, acc_im = term_re, term_im
                        else:
                            acc_re = (acc_re + term_re).as_sint(width)
                            acc_im = (acc_im + term_im).as_sint(width)
                    results.append((acc_re, acc_im))
                return results

            # ------------------------------------------------------------------
            # the advance of the chain
            # ------------------------------------------------------------------
            cnt = Reg(UInt(count_width), io.clk, io.rst, 0, name="cnt")
            sending = Reg(Bits(1), io.clk, io.rst, 0, name="sending")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                            name="out_count")
            write_bank = Reg(Bits(1), io.clk, io.rst, 0, name="write_bank")
            fill = Reg(UInt(count_width), io.clk, io.rst, 0, name="fill")
            running = Reg(Bits(1), io.clk, io.rst, 0, name="running")

            advance = ~sending
            if stallable:
                advance = advance & io.in_enable
            counting = (running | io.in_valid) & advance

            # ------------------------------------------------------------------
            # the chain of the stages
            # ------------------------------------------------------------------
            value_re = io.in_real.as_sint()
            value_im = io.in_imag.as_sint()

            for s, (block, radix, sub) in enumerate(stage_specs):
                sub_bits = log2(sub)
                quarter_bits = max(1, log2(radix))
                block_width = max(1, (block - 1).bit_length())

                # the position inside the window of the stage comes from the
                # frame counter, so a stall does not shift it
                window_bits = block_width
                stage_position = cnt.as_bits()[:window_bits]
                if sub_bits:
                    quarter = stage_position[sub_bits:].as_uint(quarter_bits)
                else:
                    # a quarter is a single cycle long, so the phase inside
                    # the window is the quarter itself
                    quarter = stage_position.as_uint(quarter_bits)
                last_quarter_bit = (quarter
                                    == UInt(quarter_bits)(radix - 1)).as_bits()

                fresh_re = value_re
                fresh_im = value_im
                if scaling == "stage":
                    fresh_re = shift_right(fresh_re, log2(radix))
                    fresh_im = shift_right(fresh_im, log2(radix))

                # the lines which hold the samples and the ones which hold the
                # results, register k of depth k * sub
                sample_lines = []
                result_lines = []
                for k in range(1, radix):
                    depth = k * sub
                    line_re = []
                    line_im = []
                    for i in range(depth):
                        reg_re = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance,
                                     name=f"samp{s}_{k}_re_{i}")
                        reg_im = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance,
                                     name=f"samp{s}_{k}_im_{i}")
                        line_re.append(reg_re)
                        line_im.append(reg_im)
                    sample_lines.append((line_re, line_im))
                    line_re = []
                    line_im = []
                    for i in range(depth):
                        reg_re = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance,
                                     name=f"res{s}_{k}_re_{i}")
                        reg_im = Reg(SInt(width), io.clk, io.rst, 0,
                                     ce=advance,
                                     name=f"res{s}_{k}_im_{i}")
                        line_re.append(reg_re)
                        line_im.append(reg_im)
                    result_lines.append((line_re, line_im))

                sample_taps = [(line_re[-1], line_im[-1])
                               for line_re, line_im in sample_lines]
                result_taps = [(line_re[-1], line_im[-1])
                               for line_re, line_im in result_lines]

                # the butterfly on the last quarter
                operands = [sample_taps[k - 1] for k in range(radix - 1, 0, -1)]
                operands.append((fresh_re, fresh_im))
                transformed = radix_dft(operands)

                # the result which is handed out: the one of this quarter
                handed_re, handed_im = result_taps[0]
                for q in range(1, radix - 1):
                    hit = (quarter == UInt(quarter_bits)(q)).as_bits()
                    handed_re = mux(hit, result_taps[q][0], handed_re)
                    handed_im = mux(hit, result_taps[q][1], handed_im)

                # the factor of this phase, chosen by the phase itself
                factor_re, factor_im = factor_of(block, sub, 0)
                window_phase = stage_position.as_uint(block_width)
                for p in range(1, block):
                    hit = (window_phase == UInt(block_width)(p)).as_bits()
                    choice_re, choice_im = factor_of(block, sub, p)
                    factor_re = mux(hit, SInt(width)(choice_re),
                                    SInt(width)(factor_re))
                    factor_im = mux(hit, SInt(width)(choice_im),
                                    SInt(width)(factor_im))
                rotated_re, rotated_im = rotate_signal(factor_re, factor_im,
                                                       handed_re, handed_im)

                stage_out_re = mux(last_quarter_bit, transformed[0][0],
                                   rotated_re)
                stage_out_im = mux(last_quarter_bit, transformed[0][1],
                                   rotated_im)

                # what the lines take in
                for k in range(1, radix):
                    # the sample enters the line of its own quarter
                    takes = (quarter
                             == UInt(quarter_bits)(radix - 1 - k)).as_bits()
                    kept_re = mux(takes & ~last_quarter_bit, fresh_re,
                                  SInt(width)(0))
                    kept_im = mux(takes & ~last_quarter_bit, fresh_im,
                                  SInt(width)(0))
                    samp_re, samp_im = sample_lines[k - 1]
                    samp_re[0].assign(kept_re)
                    samp_im[0].assign(kept_im)
                    for i in range(1, len(samp_re)):
                        samp_re[i].assign(samp_re[i - 1])
                        samp_im[i].assign(samp_im[i - 1])
                    # the difference enters the result line on the last quarter
                    res_re, res_im = result_lines[k - 1]
                    res_re[0].assign(mux(last_quarter_bit, transformed[k][0],
                                         SInt(width)(0)))
                    res_im[0].assign(mux(last_quarter_bit, transformed[k][1],
                                         SInt(width)(0)))
                    for i in range(1, len(res_re)):
                        res_re[i].assign(res_re[i - 1])
                        res_im[i].assign(res_im[i - 1])

                value_re = stage_out_re
                value_im = stage_out_im

            # ------------------------------------------------------------------
            # the two banks of spectra
            # ------------------------------------------------------------------
            # The window is `points` cycles long.  The frame writes into the bank
            # of its window while the other one is read out at the same
            # position, so no handshake is needed between capture and readout.
            filled = (fill == UInt(count_width)(points - 1)).as_bits()
            window_done = (counting & filled
                           & (cnt == UInt(count_width)(points - 1)).as_bits())
            read_bank = ~write_bank
            buf_re = [[], []]
            buf_im = [[], []]
            for bank_index in range(2):
                for bin_index in range(points):
                    slot = mixed_reverse(bin_index, radix_list)
                    enable = (write_bank == Bits(1)(bank_index)).as_bits() \
                        & (cnt == UInt(count_width)(slot)).as_bits() \
                        & filled & counting.as_bits()
                    reg_re = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"buf{bank_index}_re_{bin_index}")
                    reg_re.assign(value_re)
                    reg_im = Reg(SInt(width), io.clk, io.rst, 0, ce=enable,
                                 name=f"buf{bank_index}_im_{bin_index}")
                    reg_im.assign(value_im)
                    buf_re[bank_index].append(reg_re)
                    buf_im[bank_index].append(reg_im)

            array_re = [ArraySignal.create([r.as_bits() for r in buf_re[b]])
                        for b in range(2)]
            array_im = [ArraySignal.create([r.as_bits() for r in buf_im[b]])
                        for b in range(2)]
            out_real = mux(read_bank, array_re[1][out_count.as_bits()],
                           array_re[0][out_count.as_bits()])
            out_imag = mux(read_bank, array_im[1][out_count.as_bits()],
                           array_im[0][out_count.as_bits()])

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            spectrum_sent = sending & last_output & io.out_ready

            cnt_next = mux(counting,
                           mux(cnt == UInt(count_width)(points - 1),
                               UInt(count_width)(0),
                               (cnt + UInt(count_width)(1)).as_uint(
                                   count_width)),
                           cnt)
            fill_next = mux(counting,
                            mux(filled, fill,
                                (fill + UInt(count_width)(1)).as_uint(
                                    count_width)),
                            fill)
            write_bank_next = mux(window_done, ~write_bank, write_bank)
            sending_next = mux(spectrum_sent, Bits(1)(0), sending)
            # the second assignment wins, so `window_done` takes precedence
            sending_next = mux(window_done, Bits(1)(1), sending_next)
            out_count_next = mux(sending & io.out_ready,
                                 (out_count + UInt(count_width)(1)).as_uint(
                                     count_width),
                                 out_count)
            out_count_next = mux(spectrum_sent, UInt(count_width)(0),
                                 out_count_next)
            running_next = mux(io.in_valid, Bits(1)(1), running)

            cnt.assign(cnt_next)
            fill.assign(fill_next)
            write_bank.assign(write_bank_next)
            sending.assign(sending_next)
            out_count.assign(out_count_next)
            running.assign(running_next)

            io.in_ready = advance
            io.out_valid = sending
            io.out_real = out_real
            io.out_imag = out_imag

    FftSdcRadix.module_name = f"FftSdcRadix{width}P{points}"
    return FftSdcRadix
