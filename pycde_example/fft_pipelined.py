"""The pipelined architecture of the FFT.

The whole transform is unrolled: every stage has its own butterflies and the
stages are separated by registers, the number of registers is the number of
pipeline stages.  The architecture needs one stage per radix, it trades the area
for the throughput.

A stage of radix ``R`` combines ``R`` samples which are ``length / R`` apart,
applies an ``R`` point transform to them and rotates the result, which is the
mixed radix decomposition of :mod:`fft_radix_model`.  With ``radices="2"`` this
is the radix 2 pipeline, and the arithmetic is the same as before.

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
from .fft_radix_model import mixed_reverse, parse_radices, radix_size


@modparams
def FftPipelined(width: int = 16, points: int = 16, ordering: str = "dit",
                 stages: int = 1, scaling: str = "stage", radices: str = "2"):
    """The pipelined (unrolled) architecture of the FFT."""
    radix_list = parse_radices(radices)
    if radix_size(radix_list) != points:
        raise ValueError(f"the radices {radices!r} describe "
                         f"{radix_size(radix_list)} points, not {points}")
    count_width = max(1, (points - 1).bit_length())
    table = twiddle_table(points, width)
    dit = ordering == "dit"
    # the number of cycles the transform needs, one per stage and register
    latency = max(1, len(radix_list) * stages)
    delay_width = max(1, latency.bit_length())

    # The permutation of a mixed radix transform follows the order the stages
    # run in: the decimation in time reads the samples in it, the decimation in
    # frequency writes the result in it.
    read_radices = list(reversed(radix_list)) if dit else list(radix_list)

    def permute_read(index: int) -> int:
        """The position the sample of index ``index`` is read from."""
        return mixed_reverse(index, read_radices)

    def permute_write(index: int) -> int:
        """The position the result of index ``index`` is written to."""
        return mixed_reverse(index, radix_list)

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

            def negate(value):
                """The negation of a signed value, in the same width."""
                wide = value.as_sint(width + 1)
                return (SInt(width + 1)(0) - wide).as_sint(width)

            def rotate(index, re, im):
                """Multiply with the twiddle factor of `index`.

                The index is a constant of the stage, so the trivial factors
                are resolved here: W**0 is a wire and W**(points/4) is a swap
                with a negation.  A multiplier is only built for the rest.  The
                table cannot hold +1.0, so multiplying with its first entry
                would cost a unit of the last bit.
                """
                index %= points
                if index == 0:
                    return (re, im)
                if index == points // 4:
                    # the factor is -j (the pipelined architectures compute the
                    # forward transform only)
                    return (im, negate(re))
                return complex_multiply(SInt(width)(table[index % (points // 2)][0]),
                                        SInt(width)(table[index % (points // 2)][1]),
                                        re, im)

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
            values_re = [in_re[permute_read(i) if dit else i] for i in range(points)]
            values_im = [in_im[permute_read(i) if dit else i] for i in range(points)]

            # ------------------------------------------------------------------
            # the transform
            # ------------------------------------------------------------------
            def radix_dft(values):
                """The ``R`` point transform inside a stage of radix ``R``.

                The roots of unity which are trivial are applied exactly: a
                table cannot hold +1.0 or -1.0 in the fixed point format, so
                multiplying with an entry a unit short of them would cost a
                unit of the last bit inside every butterfly.
                """
                size = len(values)
                if size == 2:
                    (a_re, a_im), (b_re, b_im) = values
                    return [((a_re + b_re).as_sint(width),
                             (a_im + b_im).as_sint(width)),
                            ((a_re - b_re).as_sint(width),
                             (a_im - b_im).as_sint(width))]
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
                        elif exponent == size // 4:
                            # -j: a swap with a negation
                            term_re, term_im = im, negate(re)
                        elif exponent == size // 2:
                            # -1: a negation
                            term_re, term_im = negate(re), negate(im)
                        else:
                            # W**(size - k) is the conjugate of W**k, so the
                            # table only has to hold the first half
                            folded = (exponent if exponent <= size // 2
                                      else size - exponent)
                            w_re = SInt(width)(roots[folded % (size // 2)][0])
                            w_im = SInt(width)(roots[folded % (size // 2)][1])
                            if exponent > size // 2:
                                w_im = negate(w_im)
                            term_re, term_im = complex_multiply(w_re, w_im,
                                                                re, im)
                        if acc_re is None:
                            acc_re, acc_im = term_re, term_im
                        else:
                            acc_re = (acc_re + term_re).as_sint(width)
                            acc_im = (acc_im + term_im).as_sint(width)
                    results.append((acc_re, acc_im))
                return results

            # The decimation in frequency works the large butterflies first, the
            # decimation in time the small ones; `length` is the size of the
            # block a stage works on.
            stage_list = list(reversed(radix_list)) if dit else list(radix_list)
            length = 1 if dit else points
            for stage_index, radix in enumerate(stage_list):
                if dit:
                    length *= radix
                sub = length // radix
                scale_shift = radix.bit_length() - 1
                new_re = []
                new_im = []
                for i in range(points):
                    local = i % length
                    base = i - local
                    j = local % sub
                    r = local // sub
                    values = []
                    for l in range(radix):
                        re = values_re[base + j + l * sub]
                        im = values_im[base + j + l * sub]
                        if scaling == "stage":
                            # the operands are scaled by 1 / R, which is what
                            # the stage costs in bit width
                            re = shift_right(re, scale_shift)
                            im = shift_right(im, scale_shift)
                        if dit and l:
                            # the twiddle belongs to the input of the butterfly
                            re, im = rotate((j * l * (points // length))
                                            % points, re, im)
                        values.append((re, im))
                    transformed = radix_dft(values)
                    re, im = transformed[r]
                    if not dit and r:
                        # the twiddle belongs to the result of the butterfly
                        re, im = rotate((j * r * (points // length)) % points,
                                        re, im)
                    new_re.append(re)
                    new_im.append(im)

                # the pipeline registers between the stages
                for _ in range(stages):
                    for i in range(points):
                        new_re[i] = new_re[i].reg(io.clk, io.rst, ce=computing,
                                                  name=f"stage{stage_index}_re_{i}")
                        new_im[i] = new_im[i].reg(io.clk, io.rst, ce=computing,
                                                  name=f"stage{stage_index}_im_{i}")
                values_re = new_re
                values_im = new_im
                if not dit:
                    length = sub

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
                # the result of the decimation in frequency is read from the
                # permuted position; the permutation is looked up directly,
                # since a mixed radix one is not its own inverse
                out_index = UInt(count_width)(0)
                for i in range(points):
                    out_index = mux(out_count == UInt(count_width)(i),
                                    UInt(count_width)(permute_write(i)),
                                    out_index)
            # the spectrum is read out of the last stage
            out_array_re = ArraySignal.create(values_re)
            out_array_im = ArraySignal.create(values_im)
            io.in_ready = receiving
            io.out_valid = sending
            io.out_real = out_array_re[out_index].as_bits()
            io.out_imag = out_array_im[out_index].as_bits()

    FftPipelined.module_name = f"FftPipelined{width}P{points}S{stages}"
    return FftPipelined
