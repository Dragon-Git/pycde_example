"""A configurable FFT written in PyCDE.

The transform is built from independent submodules which the top level
instantiates according to the configuration:

* :func:`fft_butterfly.Butterfly` - the butterfly unit (the complex
  multiplier and the adders).
* :func:`fft_twiddle.Twiddle` - the twiddle factor generator (a read only
  memory or a CORDIC rotator).
* :func:`fft_memory.FrameMemory` - the in place frame memory.
* :func:`fft_pipelined.FftPipelined` - the unrolled pipeline.
* :func:`fft_sdf.FftSdf` - the single path delay feedback architecture.

The configuration of the transform:

``width``
    Datapath width in bits (two's complement, the sign bit included).  A real
    number ``v`` is represented by ``round(v * 2**(width - 1))``.

``points``
    The number of points of the transform, a power of two.

``radices``
    The radices of the transform as a comma separated list, e.g. ``"2"`` or
    ``"4,2"``.  Only radix 2 is implemented so far.

``eval_mode``
    ``"memory_based"``: the transform is computed iteratively, one butterfly
    at a time, the intermediate results are kept in the frame memory.  The
    frame is processed in ``log2(points)`` passes of ``points / 2``
    butterflies.

    ``"pipelined"``: the transform is unrolled into a dataflow pipeline.

``pipeline_style``
    The sub topology of the pipelined architecture: ``"sdf"`` (single path
    delay feedback), ``"mdc"`` (multi path delay commutator), ``"sdc"``
    (single path delay commutator) or ``"mdf"`` (multi path delay feedback).
    The single path delay feedback folds the transform into a chain of
    stages which is fed back into itself (see :mod:`fft_sdf`), the multi path
    one unrolls it (see :mod:`fft_pipelined`).

``twiddle_mode``
    ``"rom"``, ``"cordic"``, ``"hybrid"`` or ``"no_mem"`` - see
    :func:`fft_twiddle.Twiddle`.

``data_format``
    ``"fixed"``: the datapath has a fixed width, the stages are scaled to
    avoid an overflow.  ``"block_float"``: the stages share an exponent.

``scaling``
    The scaling of the stages: ``"stage"`` halves the operands of every
    butterfly, ``"none"`` does not scale at all (the datapath has to be wide
    enough to hold the whole spectrum).

``inverse``
    The inverse transform: the twiddle factors, the input and the output are
    conjugated.

``ordering``
    ``"dit"`` (decimation in time) or ``"dif"`` (decimation in frequency).
    The two differ in the order in which the samples are read from (and
    written to) the frame memory and in the position of the twiddle
    multiplier - the spectrum itself is the same.

``parallel``
    The number of butterflies which are computed in parallel.

The interface is frame based: the module accepts ``points`` samples and
produces ``points`` samples.  The samples of a frame are counted, the first
sample of a frame is the first one which is accepted while the module is
idle.

The fixed point format and the reference model are described in
``fft_model``.
"""

from __future__ import annotations

import os

from pycde import Clock, Input, Module, Output, Reset, System, generator, modparams
from pycde.constructs import Mux, Reg, Wire
from pycde.signals import BitsSignal
from pycde.types import Bits, UInt

try:
    from pycde_example.fft_butterfly import Butterfly
    from pycde_example.fft_configs import (
        ARCHES,
        DATA_FORMATS,
        FFT_CONFIGS,
        ORDERINGS,
        PIPELINE_STYLES,
        RADICES,
        SCALINGS,
        TWIDDLE_MODES,
        fft_name,
    )
    from pycde_example.fft_memory import FrameMemory
    from pycde_example.fft_pipelined import FftPipelined
    from pycde_example.fft_sdf import FftSdf
    from pycde_example.fft_twiddle import Twiddle
except ImportError:  # executed as a plain script ("python pycde_example/fft.py")
    from fft_butterfly import Butterfly
    from fft_configs import (
        ARCHES,
        DATA_FORMATS,
        FFT_CONFIGS,
        ORDERINGS,
        PIPELINE_STYLES,
        SCALINGS,
        TWIDDLE_MODES,
        fft_name,
    )
    from fft_memory import FrameMemory
    from fft_pipelined import FftPipelined
    from fft_sdf import FftSdf
    from fft_twiddle import Twiddle


@modparams
def Fft(width: int = 16,
        points: int = 16,
        radices: str = "2",
        eval_mode: str = "memory_based",
        pipeline_style: str = "sdf",
        twiddle_mode: str = "rom",
        data_format: str = "fixed",
        scaling: str = "stage",
        stages: int = 1,
        inverse: bool = False,
        ordering: str = "dit",
        parallel: int = 1):
    """Create a configurable FFT module."""
    if eval_mode not in ARCHES:
        raise ValueError(f"eval_mode must be one of {ARCHES}, got {eval_mode!r}")
    if pipeline_style not in PIPELINE_STYLES:
        raise ValueError(f"pipeline_style must be one of {PIPELINE_STYLES}, "
                         f"got {pipeline_style!r}")
    if twiddle_mode not in TWIDDLE_MODES:
        raise ValueError(f"twiddle_mode must be one of {TWIDDLE_MODES}, "
                         f"got {twiddle_mode!r}")
    if data_format not in DATA_FORMATS:
        raise ValueError(f"data_format must be one of {DATA_FORMATS}, "
                         f"got {data_format!r}")
    if scaling not in SCALINGS:
        raise ValueError(f"scaling must be one of {SCALINGS}, got {scaling!r}")
    if ordering not in ORDERINGS:
        raise ValueError(f"ordering must be one of {ORDERINGS}, got {ordering!r}")
    if points < 2 or (points & (points - 1)):
        raise ValueError(f"points must be a power of two, got {points}")
    if width < 8:
        raise ValueError(f"width must be at least 8, got {width}")
    if radices not in RADICES:
        raise NotImplementedError(f"the radices {radices!r} are not implemented yet")
    if data_format == "block_float":
        raise NotImplementedError("the block floating point format is not "
                                  "implemented yet")
    if eval_mode == "pipelined" and pipeline_style not in ("mdc", "sdf"):
        raise NotImplementedError("only the multi path ('mdc') and the single "
                                  "path delay feedback ('sdf') pipelined "
                                  "architectures are implemented so far")
    if eval_mode == "pipelined" and inverse:
        raise NotImplementedError("the inverse transform is only implemented "
                                  "for the memory based architecture")
    if stages < 0:
        raise ValueError(f"stages must not be negative, got {stages}")
    if parallel != 1:
        raise NotImplementedError("only a single butterfly per cycle is "
                                  "implemented so far")

    levels = points.bit_length() - 1  # the number of radix-2 stages
    count_width = max(1, (points - 1).bit_length())
    pass_width = max(1, levels)
    dit = ordering == "dit"

    class Fft(Module):
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
            if eval_mode == "pipelined":
                if pipeline_style == "sdf":
                    # the single path delay feedback architecture
                    core = FftSdf(width=width, points=points,
                                  ordering=ordering, stages=stages,
                                  scaling=scaling)(
                                      clk=io.clk, rst=io.rst,
                                      in_valid=io.in_valid,
                                      in_real=io.in_real, in_imag=io.in_imag,
                                      out_ready=io.out_ready)
                else:
                    core = FftPipelined(width=width, points=points,
                                        ordering=ordering, stages=stages,
                                        scaling=scaling)(
                                            clk=io.clk, rst=io.rst,
                                            in_valid=io.in_valid,
                                            in_real=io.in_real,
                                            in_imag=io.in_imag,
                                            out_ready=io.out_ready)
                io.in_ready = core.in_ready
                io.out_valid = core.out_valid
                io.out_real = core.out_real
                io.out_imag = core.out_imag
                return

            def mux(sel, when_true, when_false):
                """A two input multiplexer.

                ``pycde.constructs.Mux(sel, a, b)`` returns ``b`` when ``sel``
                is high, this helper uses the intuitive order.
                """
                return Mux(sel, when_false, when_true)

            # ------------------------------------------------------------------
            # the control
            # ------------------------------------------------------------------
            # 0: receiving the frame, 1: computing, 2: sending the result
            phase = Reg(UInt(2), io.clk, io.rst, 0, name="phase")
            in_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="in_count")
            out_count = Reg(UInt(count_width), io.clk, io.rst, 0, name="out_count")
            # the radix-2 stage which is currently processed
            pass_count = Reg(UInt(pass_width), io.clk, io.rst, 0, name="pass_count")
            # the butterfly inside the stage
            butterfly_count = Reg(UInt(count_width), io.clk, io.rst, 0,
                                  name="butterfly_count")
            # the index inside a group of butterflies
            group_count = Reg(UInt(pass_width), io.clk, io.rst, 0, name="group_count")
            # the address of the first operand of the butterfly
            addr = Reg(UInt(count_width), io.clk, io.rst, 0, name="addr")
            # the index of the twiddle factor
            twiddle_index = Reg(UInt(count_width), io.clk, io.rst, 0, name="twiddle_index")

            receiving = (phase == UInt(2)(0)).as_bits()
            computing = (phase == UInt(2)(1)).as_bits()
            sending = (phase == UInt(2)(2)).as_bits()

            # ------------------------------------------------------------------
            # the butterflies of a pass
            # ------------------------------------------------------------------
            # The size of a group of butterflies doubles from pass to pass, the
            # twiddle factors of a group are spaced by points / (2 * size).
            group_size = UInt(pass_width)(1)
            step = UInt(count_width)(points // 2)
            for s in range(levels):
                group_size = mux((pass_count == UInt(pass_width)(s)).as_bits(),
                                 UInt(pass_width)(1 << s), group_size)
                step = mux((pass_count == UInt(pass_width)(s)).as_bits(),
                           UInt(count_width)(points >> (s + 1)), step)

            # the end of a group of butterflies
            group_end = (group_count == (group_size - UInt(pass_width)(1))).as_bits()
            # inside a group the address increases by one, at the end of a
            # group it skips the second half of the group
            addr_next = mux(
                group_end,
                (addr + group_size + UInt(count_width)(1)).as_uint(count_width),
                (addr + UInt(count_width)(1)).as_uint(count_width))
            # the twiddle index increases by the step inside a group
            twiddle_next = mux(group_end, UInt(count_width)(0),
                                (twiddle_index + step).as_uint(count_width))
            group_next = mux(group_end, UInt(pass_width)(0),
                             (group_count + UInt(pass_width)(1)).as_uint(pass_width))

            # the address of the second operand of the butterfly
            addr2 = (addr + group_size).as_uint(count_width)

            # the address the result is read from
            output_address = out_count
            if not dit:
                # the output of the decimation in frequency is bit reversed
                bits = out_count.as_bits()
                output_address = BitsSignal.concat(
                    [bits[i] for i in range(count_width)]).as_uint()

            # ------------------------------------------------------------------
            # the memory write
            # ------------------------------------------------------------------
            # While the frame is received the samples are written, while the
            # transform is computed the butterflies are written back.
            input_address = in_count
            if dit:
                # the bit reversal of the address is free: it is just a
                # permutation of the address bits
                bits = in_count.as_bits()
                input_address = BitsSignal.concat(
                    [bits[i] for i in range(count_width)]).as_uint()
            write0 = mux(computing, addr, input_address)

            # ------------------------------------------------------------------
            # the frame memory
            # ------------------------------------------------------------------
            # the results of the butterfly are written back into the memory
            sum_re = Wire(Bits(width), "butterfly_sum_re")
            sum_im = Wire(Bits(width), "butterfly_sum_im")
            diff_re = Wire(Bits(width), "butterfly_diff_re")
            diff_im = Wire(Bits(width), "butterfly_diff_im")

            memory = FrameMemory(width=width, points=points)(
                clk=io.clk, rst=io.rst,
                w0_addr=write0.as_bits(), w0_re=io.in_real, w0_im=io.in_imag,
                w0_en=receiving,
                w1_addr=addr.as_bits(), w1_re=sum_re, w1_im=sum_im,
                w1_en=computing,
                w2_addr=addr2.as_bits(), w2_re=diff_re, w2_im=diff_im,
                w2_en=computing,
                r0_addr=addr.as_bits(), r1_addr=addr2.as_bits(),
                r2_addr=output_address.as_bits())

            # ------------------------------------------------------------------
            # the twiddle factor
            # ------------------------------------------------------------------
            # The twiddle generator is consumed as soon as the butterfly is
            # computed, the ready signal is a backedge of the control flow.
            twiddle_ready = Wire(Bits(1), "twiddle_ready")
            # A new twiddle factor is requested when the previous one was
            # consumed by the butterfly.
            twiddle_strobe = Reg(Bits(1), io.clk, io.rst, 0,
                                 name="twiddle_index_valid")
            twiddle = Twiddle(width=width, points=points, mode=twiddle_mode,
                              inverse=inverse)(
                                  clk=io.clk, rst=io.rst,
                                  index=twiddle_index.as_bits(),
                                  index_valid=twiddle_strobe,
                                  out_ready=twiddle_ready)

            # ------------------------------------------------------------------
            # the butterfly
            # ------------------------------------------------------------------
            butterfly = Butterfly(width=width, scaling=scaling,
                                  twiddle_position="input" if dit else "output")(
                                      a_re=memory.r0_re, a_im=memory.r0_im,
                                      b_re=memory.r1_re, b_im=memory.r1_im,
                                      w_re=twiddle.re, w_im=twiddle.im)
            sum_re.assign(butterfly.sum_re)
            sum_im.assign(butterfly.sum_im)
            diff_re.assign(butterfly.diff_re)
            diff_im.assign(butterfly.diff_im)

            # ------------------------------------------------------------------
            # the control flow
            # ------------------------------------------------------------------
            accept = io.in_valid & receiving
            last_butterfly = (butterfly_count ==
                              UInt(count_width)(points // 2 - 1)).as_bits()
            last_input = (in_count == UInt(count_width)(points - 1)).as_bits()
            last_output = (out_count == UInt(count_width)(points - 1)).as_bits()
            # the decimation in time processes the small butterflies first, the
            # decimation in frequency the large ones
            last_pass = (pass_count ==
                         UInt(pass_width)(levels - 1 if dit else 0)).as_bits()
            # the butterfly is computed as soon as the twiddle factor is ready
            butterfly_done = computing & twiddle.valid
            # the twiddle factor is consumed by the butterfly
            twiddle_ready.assign(butterfly_done)
            # the next twiddle factor is requested in the next cycle, the
            # first one is requested when the computation starts
            twiddle_strobe.assign(butterfly_done | (receiving & last_input))

            phase_next = phase
            in_count_next = in_count
            out_count_next = out_count
            pass_count_next = pass_count
            butterfly_count_next = butterfly_count
            group_count_next = group_count
            addr_next_reg = addr
            twiddle_next_reg = twiddle_index

            # receiving: the samples are counted, the last one starts the
            # computation
            phase_next = mux(receiving & last_input, UInt(2)(1), phase_next)
            in_count_next = mux(accept,
                                (in_count + UInt(count_width)(1)).as_uint(count_width),
                                in_count_next)
            # the first pass starts with the first radix-2 stage
            pass_count_next = mux(receiving & last_input,
                                  UInt(pass_width)(0 if dit else levels - 1),
                                  pass_count_next)
            # computing: the butterflies of the pass are computed
            phase_next = mux(butterfly_done & last_butterfly & last_pass, UInt(2)(2),
                             phase_next)
            pass_count_next = mux(
                butterfly_done & last_butterfly,
                (pass_count + UInt(pass_width)(1)).as_uint(pass_width) if dit
                else (pass_count - UInt(pass_width)(1)).as_uint(pass_width),
                pass_count_next)
            butterfly_count_next = mux(
                butterfly_done & last_butterfly, UInt(count_width)(0),
                (butterfly_count + UInt(count_width)(1)).as_uint(count_width))
            # the result is read from the memory, the counter starts at zero
            out_count_next = mux(butterfly_done & last_butterfly & last_pass,
                                 UInt(count_width)(0), out_count_next)
            # the address, the group and the twiddle index start over with
            # every pass
            group_count_next = mux(butterfly_done & last_butterfly,
                                   UInt(pass_width)(0),
                                   mux(butterfly_done, group_next, group_count_next))
            addr_next_reg = mux(butterfly_done & last_butterfly, UInt(count_width)(0),
                                mux(butterfly_done, addr_next, addr_next_reg))
            twiddle_next_reg = mux(butterfly_done & last_butterfly,
                                   UInt(count_width)(0),
                                   mux(butterfly_done, twiddle_next, twiddle_next_reg))
            # sending: the result is read from the memory
            phase_next = mux(sending & last_output & io.out_ready, UInt(2)(0),
                             phase_next)
            out_count_next = mux(
                sending & io.out_ready,
                (out_count + UInt(count_width)(1)).as_uint(count_width),
                out_count_next)
            # the next frame starts at the first sample
            in_count_next = mux(sending & last_output & io.out_ready,
                                UInt(count_width)(0), in_count_next)

            phase.assign(phase_next)
            in_count.assign(in_count_next)
            out_count.assign(out_count_next)
            pass_count.assign(pass_count_next)
            butterfly_count.assign(butterfly_count_next)
            group_count.assign(group_count_next)
            addr.assign(addr_next_reg)
            twiddle_index.assign(twiddle_next_reg)

            # ------------------------------------------------------------------
            # the interface
            # ------------------------------------------------------------------
            out_re = memory.r2_re
            out_im = memory.r2_im
            io.in_ready = receiving
            io.out_valid = sending
            io.out_real = out_re
            io.out_imag = out_im

    Fft.module_name = fft_name(width, points, radices, eval_mode, pipeline_style,
                                twiddle_mode, data_format, scaling, stages,
                                inverse, ordering, parallel)
    return Fft


def build_fft_system(configs=None, name: str = "ip_fft_lib",
                     output_directory: str = "build/ip_fft_lib"):
    """Generate the SystemVerilog of the given FFT configurations.

    A PyCDE system may only have a single top level module (the ESI manifest
    pass looks up exactly one top module), so every configuration is built
    into its own system and its own directory.
    """
    configs = FFT_CONFIGS if configs is None else configs
    os.makedirs(output_directory, exist_ok=True)
    systems = []
    for cfg in configs:
        module = Fft(**cfg["params"])
        system = System([module], name=cfg["name"],
                        output_directory=os.path.join(output_directory, cfg["name"]))
        system.compile()
        systems.append(system)
    return systems


def build_twiddle_system(width: int = 16, points: int = 16, mode: str = "cordic",
                         name: str = "ip_fft_twiddle",
                         output_directory: str = "build/ip_fft_twiddle"):
    """A system with the twiddle generator as the top level module.

    It is used by the unit test of the generator.
    """
    os.makedirs(output_directory, exist_ok=True)
    module = Twiddle(width=width, points=points, mode=mode, inverse=False)
    system = System([module], name="TwiddleTest", output_directory=output_directory)
    system.compile()
    return system


if __name__ == "__main__":
    build_fft_system()
    build_twiddle_system()
