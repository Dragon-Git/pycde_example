"""A configurable CORDIC (rotation / vectoring mode) written in PyCDE.

The module can be configured along four independent axes:

``width``
    Datapath width in bits (two's complement, the sign bit included).

``iterations``
    Number of CORDIC iterations.  The angular resolution is
    ``atan(2**-(iterations-1))`` and the gain is ``prod(sqrt(1 + 2**-2i))``
    (about 1.6468 for 16 iterations).  The gain is *not* compensated.

``mode``
    ``"rotation"`` rotates the input vector ``(x, y)`` by the angle ``z``,
    ``"vectoring"`` computes the magnitude and the angle of the input vector.

``arch``
    * ``"comb"``: fully combinational, all iterations are unrolled, the result
      is available in the very same cycle (latency 0).
    * ``"pipelined"``: all iterations are unrolled, one register per iteration
      (latency ``iterations``, one result per cycle).
    * ``"loop"``: a single iteration is implemented and reused ``iterations``
      times (latency ``iterations + 1``, one result every ``iterations + 1``
      cycles).
    * ``"loop_pipelined"``: like ``"loop"`` but the single iteration is
      registered as well, so every iteration takes two cycles
      (latency ``2 * iterations + 1``).

All four architectures share the same ready/valid interface::

    in_valid/in_ready   input handshake
    out_valid/out_ready output handshake

The angles use the fixed point format of ``cordic_model``: ``pi`` is
represented by ``1 << (width - 2)``.  Note that a CORDIC can only process
angles within ``+-sum(atan(2**-i))`` (about +-1.74 radian), because that is
the sum of all the rotations it is able to perform.

Running this file generates the SystemVerilog of every configuration listed in
``cordic_configs.CORDIC_CONFIGS``::

    python -m pycde_example.cordic
"""

from __future__ import annotations

import os

from pycde import Clock, Input, Module, Output, Reset, System, generator, modparams
from pycde.constructs import Mux, Reg, Wire
from pycde.dialects import comb
from pycde.types import Bits, SInt, UInt

try:
    from pycde_example.cordic_configs import ARCHES, CORDIC_CONFIGS, MODES, cordic_name
    from pycde_example.cordic_model import atan_table
except ImportError:  # executed as a plain script ("python pycde_example/cordic.py")
    from cordic_configs import ARCHES, CORDIC_CONFIGS, MODES, cordic_name
    from cordic_model import atan_table


@modparams
def Cordic(width: int = 32,
           iterations: int = 16,
           mode: str = "rotation",
           arch: str = "comb"):
    """Create a configurable CORDIC module.

    See the module documentation for a description of the parameters.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if arch not in ARCHES:
        raise ValueError(f"arch must be one of {ARCHES}, got {arch!r}")
    if width < 8:
        raise ValueError(f"width must be at least 8, got {width}")
    if iterations < 1:
        raise ValueError(f"iterations must be positive, got {iterations}")

    table: list[int] = atan_table(width, iterations)
    # width of the iteration counter (used by the loop architectures)
    cnt_width = max(1, (iterations - 1).bit_length())

    def mux(sel, when_true, when_false):
        """A two input multiplexer.

        ``pycde.constructs.Mux(sel, a, b)`` returns ``b`` when ``sel`` is
        high, this helper uses the intuitive order.
        """
        return Mux(sel, when_false, when_true)

    def iteration(x, y, z, shift, atan_value) -> tuple:
        """One CORDIC iteration.

        ``x``, ``y`` and ``z`` are signed ``width`` bit signals.  ``shift`` is
        either a constant (the iteration index) or a signal holding the shift
        amount, ``atan_value`` is the fixed point ``atan(2**-i)`` of the
        current iteration.
        """
        amount = Bits(width)(shift) if isinstance(shift, int) else shift
        x_sh = comb.ShrSOp(x.as_bits(), amount).as_sint()
        y_sh = comb.ShrSOp(y.as_bits(), amount).as_sint()

        x_plus = (x + y_sh).as_sint(width)
        x_minus = (x - y_sh).as_sint(width)
        y_plus = (y + x_sh).as_sint(width)
        y_minus = (y - x_sh).as_sint(width)
        z_plus = (z + atan_value).as_sint(width)
        z_minus = (z - atan_value).as_sint(width)

        if mode == "rotation":
            # While z is positive the vector is rotated counter clockwise, so
            # that the accumulated rotation ends up being z and z itself is
            # driven towards zero.
            q = z.as_bits()[width - 1]
            x_next = mux(q, x_plus, x_minus)
            y_next = mux(q, y_minus, y_plus)
            z_next = mux(q, z_plus, z_minus)
        else:
            # Vectoring rotates the vector onto the x axis: while y is
            # positive the vector is rotated clockwise.
            q = y.as_bits()[width - 1]
            x_next = mux(q, x_minus, x_plus)
            y_next = mux(q, y_plus, y_minus)
            z_next = mux(q, z_minus, z_plus)

        return x_next, y_next, z_next

    class Cordic(Module):
        clk = Clock()
        rst = Reset()
        x_i = Input(Bits(width))
        y_i = Input(Bits(width))
        z_i = Input(Bits(width))
        in_valid = Input(Bits(1))
        in_ready = Output(Bits(1))
        out_valid = Output(Bits(1))
        out_ready = Input(Bits(1))
        x_o = Output(Bits(width))
        y_o = Output(Bits(width))
        z_o = Output(Bits(width))

        @generator
        def construct(io):
            one = Bits(1)(1)
            zero = Bits(1)(0)
            x_in = io.x_i.as_sint()
            y_in = io.y_i.as_sint()
            z_in = io.z_i.as_sint()

            if arch == "comb":
                # Fully combinational: every iteration is unrolled.
                x, y, z = x_in, y_in, z_in
                for i in range(iterations):
                    x, y, z = iteration(x, y, z, i, SInt(width)(table[i]))
                io.x_o = x.as_bits()
                io.y_o = y.as_bits()
                io.z_o = z.as_bits()
                io.out_valid = io.in_valid
                io.in_ready = one
                return

            if arch == "pipelined":
                # Every iteration is unrolled and separated by a register.  The
                # pipeline moves as long as the output stage is empty or the
                # output is accepted, so a result is held until it is consumed.
                advance = Wire(Bits(1), "advance")
                x, y, z = x_in, y_in, z_in
                valid = io.in_valid
                for i in range(iterations):
                    x, y, z = iteration(x, y, z, i, SInt(width)(table[i]))
                    x = x.reg(io.clk, io.rst, ce=advance)
                    y = y.reg(io.clk, io.rst, ce=advance)
                    z = z.reg(io.clk, io.rst, ce=advance)
                    valid = valid.reg(io.clk, io.rst, ce=advance)
                advance.assign(io.out_ready | (valid ^ one))
                io.x_o = x.as_bits()
                io.y_o = y.as_bits()
                io.z_o = z.as_bits()
                io.out_valid = valid
                io.in_ready = advance
                return

            # The loop architectures reuse a single iteration.
            x_state = Reg(SInt(width), io.clk, io.rst, 0, name="x_state")
            y_state = Reg(SInt(width), io.clk, io.rst, 0, name="y_state")
            z_state = Reg(SInt(width), io.clk, io.rst, 0, name="z_state")
            cnt = Reg(UInt(cnt_width), io.clk, io.rst, 0, name="iter_cnt")
            busy = Reg(Bits(1), io.clk, io.rst, 0, name="busy")
            done = Reg(Bits(1), io.clk, io.rst, 0, name="done")

            accept = io.in_valid & (busy ^ one) & (done ^ one)
            # The shift amount and the arctangent depend on the iteration
            # counter, so they have to be selected at runtime.
            amount = cnt.as_bits().pad_or_truncate(width)
            atan_value = Mux(cnt.as_bits(), *[SInt(width)(a) for a in table])
            x_stage, y_stage, z_stage = iteration(x_state, y_state, z_state,
                                                   amount, atan_value)
            last = (cnt == UInt(cnt_width)(iterations - 1)).as_bits()
            not_last = last ^ one

            if arch == "loop":
                x_next = mux(accept, x_in, mux(busy, x_stage, x_state))
                y_next = mux(accept, y_in, mux(busy, y_stage, y_state))
                z_next = mux(accept, z_in, mux(busy, z_stage, z_state))
                cnt_next = mux(accept, UInt(cnt_width)(0),
                               mux(busy & not_last,
                                   (cnt + UInt(cnt_width)(1)).as_uint(cnt_width),
                                   cnt))
                busy_next = mux(accept, one, mux(busy & not_last, one, zero))
                done_next = mux(accept, zero,
                               mux(busy & last, one,
                                   mux(done & io.out_ready, zero, done)))
            else:
                # "loop_pipelined": the single iteration is registered as
                # well, so every iteration takes two cycles (compute, commit).
                x_pipe = Reg(SInt(width), io.clk, io.rst, 0, name="x_pipe")
                y_pipe = Reg(SInt(width), io.clk, io.rst, 0, name="y_pipe")
                z_pipe = Reg(SInt(width), io.clk, io.rst, 0, name="z_pipe")
                phase = Reg(Bits(1), io.clk, io.rst, 0, name="phase")
                phase0 = phase ^ one

                x_next = mux(accept, x_in, mux(busy & phase, x_pipe, x_state))
                y_next = mux(accept, y_in, mux(busy & phase, y_pipe, y_state))
                z_next = mux(accept, z_in, mux(busy & phase, z_pipe, z_state))
                x_pipe_next = mux(busy & phase0, x_stage, x_pipe)
                y_pipe_next = mux(busy & phase0, y_stage, y_pipe)
                z_pipe_next = mux(busy & phase0, z_stage, z_pipe)
                cnt_next = mux(accept, UInt(cnt_width)(0),
                               mux(busy & phase & not_last,
                                   (cnt + UInt(cnt_width)(1)).as_uint(cnt_width),
                                   cnt))
                phase_next = mux(accept, zero, mux(busy, phase ^ one, phase))
                busy_next = mux(accept, one,
                                mux(busy & ((phase & last) ^ one), one, zero))
                done_next = mux(accept, zero,
                               mux(busy & phase & last, one,
                                   mux(done & io.out_ready, zero, done)))
                x_pipe.assign(x_pipe_next)
                y_pipe.assign(y_pipe_next)
                z_pipe.assign(z_pipe_next)
                phase.assign(phase_next)

            x_state.assign(x_next)
            y_state.assign(y_next)
            z_state.assign(z_next)
            cnt.assign(cnt_next)
            busy.assign(busy_next)
            done.assign(done_next)

            io.x_o = x_state.as_bits()
            io.y_o = y_state.as_bits()
            io.z_o = z_state.as_bits()
            io.out_valid = done
            io.in_ready = (busy ^ one) & (done ^ one)

    Cordic.module_name = cordic_name(arch, mode, width, iterations)
    return Cordic


def build_cordic_system(configs=None, output_directory: str = "build/ip_cordic_lib"):
    """Generate the SystemVerilog of the given CORDIC configurations.

    A PyCDE system may only have a single top level module (the ESI manifest
    pass looks up exactly one top module), so every configuration is built
    into its own system and its own directory.
    """
    configs = CORDIC_CONFIGS if configs is None else configs
    os.makedirs(output_directory, exist_ok=True)
    systems = []
    for cfg in configs:
        module = Cordic(width=cfg["width"], iterations=cfg["iterations"],
                        mode=cfg["mode"], arch=cfg["arch"])
        system = System([module], name=cfg["name"],
                        output_directory=os.path.join(output_directory, cfg["name"]))
        system.compile()
        systems.append(system)
    return systems


if __name__ == "__main__":
    build_cordic_system()
