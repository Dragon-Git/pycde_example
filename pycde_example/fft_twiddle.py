"""The twiddle factor generator of the configurable FFT.

The twiddle factors can be produced in different ways:

``rom``
    The factors are stored in a read only memory (a register array).  The
    table holds the first ``points / 2`` factors of the unit circle, the
    other ones are the conjugates of the first ones.

``cordic``
    The factors are generated on the fly by a CORDIC rotator.  The CORDIC of
    the ``cordic`` example is reused, its gain is compensated by the
    magnitude of its input and the quarter wave symmetry keeps the angle
    inside the rotation range of the CORDIC.

    .. warning::
       The handshake between the CORDIC and the transform is not verified
       yet, the mode is not part of the tested configurations.

``hybrid``
    A coarse CORDIC and a correction table.  The CORDIC turns the vector most
    of the way, the table holds the cosine and the sine of the angle it leaves
    over, so the correction is exact for that angle.  The table has
    ``1 << HYBRID_TABLE_BITS`` entries whatever the number of points is, which
    is the trade the mode makes - a plain table holds ``points / 2`` entries -
    and it pays off from a couple of hundred points on.  The CORDIC carries
    ``HYBRID_GUARD`` bits on top of the datapath; without them the truncation
    of its shift-add steps would dominate the result and the correction could
    not recover it.  What is left is a few units of the last bit.

The generator has a ready/valid interface: the index of the factor is
accepted while ``ready`` is high, the factor is valid while ``valid`` is
high.  The read only memory is combinational, the CORDIC needs a couple of
cycles.
"""

from __future__ import annotations

from pycde import Clock, Input, Module, Output, Reset, generator, modparams
from pycde.constructs import Mux
from pycde.dialects import comb
from pycde.signals import BitsSignal
from pycde.types import Bits, SInt, UInt

from .cordic import Cordic
from .cordic_model import cordic_gain
from .fft_model import HYBRID_GUARD, HYBRID_TABLE_BITS, cordic_iterations, hybrid_table, twiddle_table
from .fft_no_mem_model import GUARD, LOGIC_LIMIT, constant

TWIDDLE_MODES = ("rom", "cordic", "hybrid", "no_mem_cascade",
                 "no_mem_logic")


@modparams
def Twiddle(width: int = 16, points: int = 16, mode: str = "rom",
            inverse: bool = False):
    """A twiddle factor generator.

    ``inverse`` conjugates the factors, which turns the transform into the
    inverse one.
    """
    if mode not in TWIDDLE_MODES:
        raise ValueError(f"twiddle mode must be one of {TWIDDLE_MODES}, got {mode!r}")
    if mode == "no_mem_logic" and points > LOGIC_LIMIT:
        raise NotImplementedError(
            f"the logic structure is meant for a small transform, {points} "
            f"points is past the {LOGIC_LIMIT} this implementation supports; "
            f"the cascade ('no_mem_cascade') scales to any number of points")

    # the index has the same width as the address of the frame memory
    index_width = max(1, (points - 1).bit_length())
    # The CORDIC can only rotate by about +-1.74 radian, the factors of the
    # second quadrant are built from the first one: W**(k + N/4) = -j * W**k.
    quarter = max(1, points // 4)
    # the number of bits of the index inside a quadrant
    quarter_width = max(0, quarter.bit_length() - 1)
    # the CORDIC needs enough iterations to resolve the angle down to the
    # least significant bit of the angle format
    iterations = cordic_iterations(width)
    # the gain of the CORDIC is compensated by the magnitude of its input
    gain = cordic_gain(iterations)
    scale = 1 << (width - 1)
    # the input has to be small enough that the gain of the CORDIC does
    # not overflow the datapath
    real_input = int((scale - 1) / gain)
    # the angle of the twiddle factor in the format of the CORDIC (pi is
    # represented by 1 << (width - 2))
    angle_shift = width - 1 - (points.bit_length() - 1)

    class Twiddle(Module):
        clk = Clock()
        rst = Reset()
        index = Input(Bits(index_width))
        index_valid = Input(Bits(1))
        out_ready = Input(Bits(1))
        re = Output(Bits(width))
        im = Output(Bits(width))
        ready = Output(Bits(1))
        valid = Output(Bits(1))

        @generator
        def construct(io):
            def negate(value):
                """The negation of a signed value."""
                return (SInt(width + 1)(0) - value.as_sint(width + 1)).as_sint(width)

            def mux(sel, when_true, when_false):
                """A two input multiplexer.

                ``pycde.constructs.Mux(sel, a, b)`` returns ``b`` when ``sel``
                is high, this helper uses the intuitive order.
                """
                return Mux(sel, when_false, when_true)

            def inner_constant(index, size):
                """The factor `W**index` as a constant of `size` bits.

                It is the value the table holds at that width, computed here at
                elaboration time and baked into the wiring.
                """
                return constant(index, size, points)

            def saturate_from(value, size):
                """Clamp a wide value into `size` bits.

                The comparison is made in the width the value already has:
                narrowing first would throw the overflow away before it could
                be seen, and the clamp would never fire.
                """
                wide = value.type.width
                high = SInt(wide)((1 << (size - 1)) - 1)
                low = SInt(wide)(-((1 << (size - 1)) - 1))
                clipped = mux((value > high).as_bits(), high,
                              mux((value < low).as_bits(), low, value))
                return clipped.as_sint(size)

            def saturate(value, size):
                """Clamp a value into the range of a signed `size` bit number.

                The value is narrowed first, which is what the callers of a
                wider arithmetic expect: the bound is then applied to the
                number the datapath would hold.
                """
                narrow = value.as_sint(size)
                high = SInt(size)((1 << (size - 1)) - 1)
                low = SInt(size)(-((1 << (size - 1)) - 1))
                return mux((narrow > high).as_bits(), high,
                           mux((narrow < low).as_bits(), low, narrow))

            def hybrid_core(io):
                """The coarse CORDIC with the correction table."""
                inner = width + HYBRID_GUARD
                turns = inner - HYBRID_TABLE_BITS + 1
                shift = inner - 1 - (points.bit_length() - 1)
                quarter = max(1, points // 4)
                quarter_width = max(0, quarter.bit_length() - 1)

                if quarter == 1:
                    reduced = UInt(max(1, quarter_width))(0)
                else:
                    reduced = io.index[:quarter_width].as_uint()
                second = (io.index.as_uint()
                          >= UInt(index_width)(quarter)).as_bits()
                # the angle of the reduced index, in the format of the CORDIC
                angle = reduced.as_sint(inner + 1) * SInt(inner + 1)(1 << shift)
                if not inverse:
                    angle = angle * SInt(inner + 1)(-1)
                angle = angle.as_sint(inner)

                start = int(((1 << (inner - 1)) - 1) / cordic_gain(turns))
                rotator = Cordic(width=inner, iterations=turns,
                                 mode="rotation", arch="comb")(
                                     clk=io.clk, rst=io.rst,
                                     x_i=Bits(inner)(start), y_i=Bits(inner)(0),
                                     z_i=angle.as_bits(),
                                     in_valid=io.index_valid,
                                     out_ready=io.out_ready)

                # the correction table, read with the angle left over
                # the table is of the inner width, whatever the datapath is
                correction = hybrid_table(width)
                cos_values = [SInt(inner)(re) for re, _ in correction]
                sin_values = [SInt(inner)(im) for _, im in correction]
                offset = (rotator.z_o.as_sint(inner)
                          + SInt(inner)(1 << (HYBRID_TABLE_BITS - 1))).as_sint(inner)
                cos = cos_values[0]
                sin = sin_values[0]
                for i in range(1, len(cos_values)):
                    hit = (offset == SInt(inner)(i)).as_bits()
                    cos = mux(hit, cos_values[i], cos)
                    sin = mux(hit, sin_values[i], sin)

                # the correction rotation; the vector and the table entries both
                # carry the scale of the inner datapath
                x = rotator.x_o.as_sint(inner)
                y = rotator.y_o.as_sint(inner)
                shift_back = 2 * (inner - 1) - (width - 1)
                # the product of two `inner` bit numbers needs `2 * inner`
                # bits, and the sum of two of them one more
                wide = 2 * inner + 1
                prod_re = (x * cos).as_sint(wide) - (y * sin).as_sint(wide)
                prod_im = (x * sin).as_sint(wide) + (y * cos).as_sint(wide)
                re = saturate(shift_down(prod_re, shift_back), width)
                im = saturate(shift_down(prod_im, shift_back), width)

                # W**(k + points/4) = -j * W**k, and +j * conj(W**k) for the
                # inverse transform
                # the operands are cast to the datapath width so that the two
                # inputs of every multiplexer have the same type
                rotated_re = saturate(-im, width) if inverse else im
                rotated_im = re if inverse else saturate(-re, width)
                io.re = mux(second, rotated_re, re).as_bits()
                io.im = mux(second, rotated_im, im).as_bits()
                io.ready = Bits(1)(1)
                io.valid = Bits(1)(1)

            def shift_down(value, amount):
                """An arithmetic shift right by a constant."""
                shift = Bits(value.type.width)(amount)
                return comb.ShrSOp(value.as_bits(), shift).as_sint()

            def constant_multiply(a_re, a_im, factor_re, factor_im, size):
                """Multiply with a constant, saturated to `size` bits.

                The factor is a compile time constant, so this is a shift and
                add chain and not a multiplier - which is what makes the
                cascade multiplier free.
                """
                product_re = a_re * SInt(size)(factor_re) \
                    - a_im * SInt(size)(factor_im)
                product_im = a_re * SInt(size)(factor_im) \
                    + a_im * SInt(size)(factor_re)
                shift_bits = Bits(product_re.type.width)(size - 1)
                wide_re = comb.ShrSOp(product_re.as_bits(),
                                      shift_bits).as_sint(
                                          product_re.type.width)
                wide_im = comb.ShrSOp(product_im.as_bits(),
                                      shift_bits).as_sint(
                                          product_im.type.width)
                # saturate, do not truncate: a product whose magnitude is
                # exactly one is one unit past what the format holds, and
                # wrapping it would flip the sign of the factor
                return saturate_from(wide_re, size), saturate_from(wide_im, size)

            def cascade_core(io):
                """The multiplier free cascade of rotator cells.

                Cell `i` rotates by the constant factor `W**(2**i)` when bit `i`
                of the index is set, and passes through when it is not.  The
                chain starts at the cell of the highest bit which is set: the
                format cannot hold `+1.0`, so starting from it would cost a unit
                of the last bit before the chain began.  The cells work in
                `GUARD` extra bits and saturate, because a product of magnitude
                exactly one is one unit past what the format holds.
                """
                inner = width + GUARD
                levels = points.bit_length() - 1

                # nothing set: the factor is `+1.0`, taken from the constant,
                # not from an arithmetic identity
                result_re = SInt(inner)(inner_constant(0, inner)[0])
                result_im = SInt(inner)(inner_constant(0, inner)[1])

                # the highest bit which is set, as a one hot mask
                higher = Bits(1)(0)
                for bit in reversed(range(levels)):
                    set_now = io.index[bit]
                    highest = set_now & ~higher
                    higher = higher | set_now
                    factor_re, factor_im = inner_constant(1 << bit, inner)
                    # the chain starts here
                    start_re = SInt(inner)(factor_re)
                    start_im = SInt(inner)(factor_im)
                    # the lower bits multiply their factor in
                    rotated_re, rotated_im = constant_multiply(
                        result_re, result_im, factor_re, factor_im, inner)
                    result_re = mux(highest, start_re,
                                    mux(set_now, rotated_re, result_re))
                    result_im = mux(highest, start_im,
                                    mux(set_now, rotated_im, result_im))

                # the chain worked in the extra bits, the factor is the high
                # part of it; the inverse transform conjugates it after the
                # truncation, since a shift is not symmetric about zero
                truncate = Bits(inner)(GUARD)
                final_re = comb.ShrSOp(
                    result_re.as_bits(), truncate).as_sint(inner)
                final_im = comb.ShrSOp(
                    result_im.as_bits(), truncate).as_sint(inner)
                narrowed_re = saturate_from(final_re, width)
                narrowed_im = saturate_from(final_im, width)
                if inverse:
                    narrowed_im = negate(narrowed_im)
                io.re = narrowed_re.as_bits()
                io.im = narrowed_im.as_bits()
                io.ready = Bits(1)(1)
                io.valid = Bits(1)(1)

            def logic_core(io):
                """The table as gates: a sum of products from the truth table.

                Every output bit is a boolean function of the index bits, built
                at elaboration time from the entries the table would hold.  The
                values are therefore the entries themselves - there is nothing
                to approximate - and there is no array for a synthesis tool to
                infer a memory from.
                """
                table_bits = max(1, (points - 1).bit_length())
                values = [inner_constant(k, width) for k in range(points)]
                if inverse:
                    values = [(re, -im) for (re, im) in values]

                # the minterm select of every index
                terms = []
                for k in range(points):
                    term = Bits(1)(1)
                    for bit in range(table_bits):
                        wanted = (k >> bit) & 1
                        term = term & (io.index[bit] if wanted
                                       else ~io.index[bit])
                    terms.append(term)

                for component in range(2):
                    output_bits = []
                    for bit in range(width):
                        value = Bits(1)(0)
                        for k in range(points):
                            if (values[k][component] >> bit) & 1:
                                value = value | terms[k]
                        output_bits.append(value)
                    if component == 0:
                        re_bits = output_bits
                    else:
                        im_bits = output_bits
                io.re = BitsSignal.concat(list(reversed(re_bits)))
                io.im = BitsSignal.concat(list(reversed(im_bits)))
                io.ready = Bits(1)(1)
                io.valid = Bits(1)(1)

            use_cordic = mode == "cordic"
            if mode == "hybrid":
                # A coarse CORDIC turns the vector most of the way and a small
                # table holds the cosine and the sine of the angle it leaves
                # over.  The table has `1 << HYBRID_TABLE_BITS` entries whatever
                # the number of points is, which is the trade the mode makes:
                # a plain table holds `points / 2`.
                hybrid_core(io)
                return
            if mode == "no_mem_cascade":
                cascade_core(io)
                return
            if mode == "no_mem_logic":
                logic_core(io)
                return
            if not use_cordic:
                # the factors are stored in a read only memory
                table = twiddle_table(points, width)
                re_values = [SInt(width)(t[0]) for t in table]
                im_values = [SInt(width)(t[1]) for t in table]
                re_value = re_values[0]
                im_value = im_values[0]
                for i in range(1, len(re_values)):
                    hit = (io.index == Bits(index_width)(i)).as_bits()
                    re_value = mux(hit, re_values[i], re_value)
                    im_value = mux(hit, im_values[i], im_value)
                if inverse:
                    im_value = negate(im_value)
                io.re = re_value.as_bits()
                io.im = im_value.as_bits()
                io.ready = Bits(1)(1)
                io.valid = Bits(1)(1)
                return

            # the factors are generated by a CORDIC rotator
            # The CORDIC is combinational, the factor is always the one of the
            # current index.  The index must not be registered, otherwise the
            # factor would lag one cycle behind the transform.
            # The index of the first quadrant and the flag of the second one.
            # The quarter is a power of two, so the reduction is a bit slice.
            if quarter == 1:
                reduced = UInt(quarter_width)(0)
            else:
                # the index inside the quadrant are the lowest bits
                reduced = io.index[:quarter_width].as_uint()
            second = (io.index.as_uint() >= UInt(index_width)(quarter)).as_bits()
            # The twiddle factor is exp(-2j*pi*k/N), the CORDIC rotates by a
            # positive angle.
            angle = reduced.as_sint(width + 1) * SInt(width + 1)(1 << angle_shift)
            if not inverse:
                angle = angle * SInt(width + 1)(-1)
            angle = angle.as_sint(width)
            rotator = Cordic(width=width, iterations=iterations,
                             mode="rotation", arch="comb")(
                                 clk=io.clk, rst=io.rst,
                                 x_i=Bits(width)(real_input), y_i=Bits(width)(0),
                                 z_i=angle.as_bits(),
                                 in_valid=io.index_valid,
                                 out_ready=io.out_ready)
            # the factors of the second quadrant are the first ones rotated
            # by -90 degrees
            re = rotator.x_o.as_sint(width)
            im = rotator.y_o.as_sint(width)
            io.re = mux(second, im, re).as_bits()
            io.im = mux(second, negate(re), im).as_bits()
            io.ready = Bits(1)(1)
            # the factor is combinational, it is always valid
            io.valid = Bits(1)(1)

    Twiddle.module_name = f"Twiddle{mode.capitalize()}{points}W{width}"
    return Twiddle
