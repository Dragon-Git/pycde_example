"""The butterfly unit of the configurable FFT.

The butterfly is a separate module: the top level instantiates it
according to the configured radix.  It is a purely combinational block.
"""

from __future__ import annotations

from pycde import Input, Module, Output, generator, modparams
from pycde.constructs import Mux
from pycde.dialects import comb
from pycde.types import Bits, SInt

SCALINGS = ("stage", "none")
TWIDDLE_POSITIONS = ("input", "output", "none")


@modparams
def ComplexMultiplier(width: int = 16):
    """The complex multiplier of the FFT.

    The product of two complex numbers with ``width`` bits has ``2 * width``
    bits, the fractional bits are dropped: the result is truncated to the
    most significant ``width`` bits, exactly like a fixed point multiplier.
    """

    class ComplexMultiplier(Module):
        a_re = Input(Bits(width))
        a_im = Input(Bits(width))
        b_re = Input(Bits(width))
        b_im = Input(Bits(width))
        re = Output(Bits(width))
        im = Output(Bits(width))

        @generator
        def construct(io):
            def shift_right(value, amount):
                """An arithmetic shift right by a constant."""
                shift = Bits(value.type.width)(amount)
                return comb.ShrSOp(value.as_bits(), shift).as_sint()

            a_re = io.a_re.as_sint()
            a_im = io.a_im.as_sint()
            b_re = io.b_re.as_sint()
            b_im = io.b_im.as_sint()

            prod_re = a_re * b_re - a_im * b_im
            prod_im = a_re * b_im + a_im * b_re
            amount = width - 1
            io.re = shift_right(prod_re, amount).as_sint(width).as_bits()
            io.im = shift_right(prod_im, amount).as_sint(width).as_bits()

    return ComplexMultiplier


@modparams
def Butterfly(width: int = 16, scaling: str = "stage",
              twiddle_position: str = "input"):
    """A radix-2 butterfly.

    ``a`` and ``b`` are the two complex operands, ``w`` is the twiddle
    factor.  The outputs are the sum and the difference of the operands.

    ``twiddle_position`` selects where the twiddle factor is applied: with
    ``"input"`` it multiplies the second operand before the butterfly (the
    decimation in time), with ``"output"`` it multiplies the difference (the
    decimation in frequency) and with ``"none"`` the twiddle factor is
    ignored (the delay feedback architecture applies it to the data which
    leaves the delay line).

    ``scaling`` selects the scaling of the stage: with ``"stage"`` the
    operands are halved before they are added, so that the magnitude of the
    datapath does not grow from stage to stage.
    """
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if twiddle_position not in TWIDDLE_POSITIONS:
        raise ValueError(f"twiddle_position must be one of {TWIDDLE_POSITIONS}, "
                         f"got {twiddle_position!r}")

    class Butterfly(Module):
        a_re = Input(Bits(width))
        a_im = Input(Bits(width))
        b_re = Input(Bits(width))
        b_im = Input(Bits(width))
        w_re = Input(Bits(width))
        w_im = Input(Bits(width))
        # the factor is trivial: a wire (w_is_one) or the rotation by -j
        # (w_is_minus_j).  Those are not multiplied, which is what the hardware
        # does - and what keeps the datapath exact, since the table cannot hold
        # +1.0.
        w_is_one = Input(Bits(1))
        w_is_minus_j = Input(Bits(1))
        sum_re = Output(Bits(width))
        sum_im = Output(Bits(width))
        diff_re = Output(Bits(width))
        diff_im = Output(Bits(width))

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

            a_re = io.a_re.as_sint()
            a_im = io.a_im.as_sint()
            b_re = io.b_re.as_sint()
            b_im = io.b_im.as_sint()
            w_re = io.w_re.as_sint()
            w_im = io.w_im.as_sint()

            def negate(value):
                """The negation of a signed value, in the same width."""
                wide = value.as_sint(width + 1)
                return (SInt(width + 1)(0) - wide).as_sint(width)

            def apply_w(re, im):
                """Multiply with the twiddle factor, exactly if it is trivial."""
                prod_re, prod_im = complex_multiply(w_re, w_im, re, im)
                prod_re = mux(io.w_is_one, re, mux(io.w_is_minus_j, im, prod_re))
                prod_im = mux(io.w_is_one, im,
                              mux(io.w_is_minus_j, negate(re), prod_im))
                return prod_re, prod_im


            if scaling == "stage":
                # the operands are halved before they are added
                a_re = shift_right(a_re, 1)
                a_im = shift_right(a_im, 1)
                b_re = shift_right(b_re, 1)
                b_im = shift_right(b_im, 1)

            if twiddle_position == "input":
                # the twiddle multiplies the second operand
                t_re, t_im = apply_w(b_re, b_im)
                u_re, u_im = a_re, a_im
            elif twiddle_position == "none":
                # the twiddle factor is not applied by the butterfly
                u_re, u_im = a_re, a_im
                t_re, t_im = b_re, b_im
            else:
                # the twiddle multiplies the difference
                u_re, u_im = a_re, a_im
                t_re, t_im = b_re, b_im

            sum_re = (u_re + t_re).as_sint(width)
            sum_im = (u_im + t_im).as_sint(width)
            diff_re = (u_re - t_re).as_sint(width)
            diff_im = (u_im - t_im).as_sint(width)

            if twiddle_position == "output":
                diff_re, diff_im = apply_w(diff_re, diff_im)

            io.sum_re = sum_re.as_bits()
            io.sum_im = sum_im.as_bits()
            io.diff_re = diff_re.as_bits()
            io.diff_im = diff_im.as_bits()

    return Butterfly
