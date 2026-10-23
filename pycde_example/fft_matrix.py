"""Every configuration the generator accepts, and a check of each one.

The RTL matrix in `fft_configs.py` is a selection: forty odd shapes which are
built and simulated.  The parameter space is much larger - every number of points,
every decomposition of it, both orderings, both scalings, every twiddle generator -
and the RTL cannot cover it, because every point costs a Verilator build and a
simulation.

What can be covered locally is the arithmetic, which is where a mistake in a
decomposition would live.  This module enumerates the legal configurations, works
out which model computes each one, and checks it against NumPy.

The enumeration follows the rules `fft.py` enforces rather than a list someone
maintains, and it returns the reason a shape is rejected: a shape which is
rejected everywhere says something about the generator, and a rule which changes
without the coverage changing shows up as a gap.
"""

from __future__ import annotations

import math

import numpy as np

from .fft_golden import deviation, golden, truncation_bound
from .fft_mdc_model import mdc
from .fft_mdf_model import mdf
from .fft_model import fft
from .fft_radix_model import fft_mixed
from .fft_sdc_radix_model import sdc_radix
from .fft_sdf_radix_model import sdf_radix

POINTS = (2, 4, 8, 16, 32, 64)
WIDTHS = (16, 24)
STYLES = ("unrolled", "sdf", "sdc", "mdf", "mdc")
TWIDDLE = ("rom", "cordic", "hybrid", "no_mem_cascade", "no_mem_logic")
SCALINGS = ("stage", "none")
ORDERINGS = ("dit", "dif")

# The logic structure replaces the table with gates, and the number of gates grows
# with the number of points, so it stops at a small transform.
LOGIC_LIMIT = 64


def decompositions(points: int, longest: int | None = None,
                   ) -> list[tuple[int, ...]]:
    """Every decomposition of ``points`` into radices, as tuples.

    The depth has to reach ``log2(points)``, or the pure radix 2 decomposition of a
    large transform would be left out - which is exactly the one every existing
    configuration uses.
    """
    if longest is None:
        longest = int(math.log2(points))
    found: set[tuple[int, ...]] = set()

    def walk(remaining: int, prefix: tuple[int, ...]) -> None:
        if remaining == 1:
            if prefix:
                found.add(prefix)
            return
        if len(prefix) == longest:
            return
        for radix in (2, 4, 8):
            if remaining % radix == 0:
                walk(remaining // radix, prefix + (radix,))

    walk(points, ())
    return sorted(found)


def as_text(decomposition: tuple[int, ...]) -> str:
    """A decomposition as a configuration writes it: a uniform one briefly."""
    if len(set(decomposition)) == 1:
        return str(decomposition[0])
    return ",".join(str(radix) for radix in decomposition)


def is_legal(eval_mode: str, style: str, points: int,
             decomposition: tuple[int, ...], ordering: str,
             twiddle: str, inverse: bool, width: int) -> str | None:
    """Whether the generator accepts a configuration, and why not if it does not."""
    big_radix = any(radix != 2 for radix in decomposition)
    stages = len(decomposition)

    if width < 8:
        return "the datapath is narrower than the interface"

    if eval_mode == "memory_based":
        if big_radix:
            return "a radix larger than 2 is the pipelined architectures only"
        if stages != int(math.log2(points)):
            return "a uniform radix 2 decomposition is the only one"
        if twiddle == "no_mem_logic" and points > LOGIC_LIMIT:
            return "the logic structure stops at a small transform"
        return None

    if style not in STYLES:
        return "unknown topology"
    if twiddle != "rom":
        return "the twiddle generator is the memory based architecture only"
    if inverse:
        return "the inverse transform is the memory based architecture only"
    if stages != int(math.log2(points)) and not big_radix:
        return "a uniform radix 2 decomposition is written as one radix"

    if style == "sdc" and ordering != "dif":
        return "the commutator chain is the decimation in frequency one"
    if style in ("mdf", "mdc"):
        if decomposition[0] != 2:
            return "a multi path architecture starts with the stage which splits"
        if len(decomposition) < 2:
            # the chains would be left with a single point, which is not a
            # transform: the split costs a stage and the chains need one
            return "the chains would be left with one point"
    if big_radix and style in ("sdf", "sdc") and ordering != "dif":
        return ("a chain with a radix larger than 2 is the decimation in "
                "frequency one")
    return None


def model_for(eval_mode: str, style: str, points: int,
              decomposition: tuple[int, ...], twiddle: str = "rom",
              ordering: str = "dif"):
    """The model which computes a configuration, or None if there is none.

    The memory based architecture is the radix 2 model whatever its twiddle
    generator, that generator being a property of the hardware rather than of the
    arithmetic.  A pipelined architecture is its own model, and the multi path ones
    take the radices of the chains - everything after the split.
    """
    radices = as_text(decomposition)
    big_radix = any(radix != 2 for radix in decomposition)
    if eval_mode == "memory_based":
        # the twiddle generator is part of the arithmetic of this architecture:
        # a CORDIC and a table produce different factors, and the point of the
        # mode is that the transform still comes out right
        dit = ordering == "dit"
        return lambda frame, width: fft(frame, width, points, dit=dit,
                                        twiddle_mode=twiddle)
    if style == "unrolled":
        return lambda frame, width: fft_mixed(frame, width, points, radices,
                                              dit=False)
    if style in ("sdf", "sdc"):
        if not big_radix:
            return lambda frame, width: fft(frame, width, points, dit=False)
        build = sdf_radix if style == "sdf" else sdc_radix
        return lambda frame, width: build(frame, width, points, radices)
    if style == "mdf":
        return lambda frame, width: mdf(frame, width, points, radices=radices)
    if style == "mdc":
        return lambda frame, width: mdc(frame, width, points, radices=radices)
    return None


def vectors(points: int, width: int):
    """The shapes a transform has to get right, as fixed point frames."""
    scale = 1 << (width - 1)
    impulse = [(0, 0)] * points
    impulse[0] = (64 * points, 0)
    yield "impulse", impulse

    yield "constant", [(scale // 2, 0)] * points
    yield "alternating", [(scale // 2 if n % 2 == 0 else -(scale // 2), 0)
                          for n in range(points)]

    for bin_index in (1, points // 2 - 1):
        if bin_index <= 0 or bin_index >= points // 2:
            continue
        yield f"tone{bin_index}", [
            (min(max(round(0.4 * scale * math.cos(
                2 * math.pi * bin_index * n / points)), -scale + 1), scale - 1),
             min(max(round(0.4 * scale * math.sin(
                 2 * math.pi * bin_index * n / points)), -scale + 1), scale - 1))
            for n in range(points)]

    rng = np.random.default_rng(1234 + points + width)
    noise = []
    for _ in range(points):
        radius = rng.uniform(0.0, 0.3)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        noise.append((round(scale * radius * math.cos(angle)),
                      round(scale * radius * math.sin(angle))))
    yield "noise", noise

    angles = np.random.default_rng(99 + points).uniform(0.0, 2.0 * math.pi,
                                                        points)
    yield "full scale", [(round((scale - 1) * math.cos(a)),
                          round((scale - 1) * math.sin(a))) for a in angles]


def allowed(decomposition: tuple[int, ...]) -> float:
    """The deviation a datapath of this shape may have from the golden."""
    return truncation_bound(list(decomposition))


def check(eval_mode: str, style: str, points: int,
          decomposition: tuple[int, ...], width: int,
          twiddle: str = "rom", ordering: str = "dif") -> list[str]:
    """Check one configuration against NumPy over every vector."""
    build = model_for(eval_mode, style, points, decomposition, twiddle,
                      ordering)
    if build is None:
        return [f"no model for {eval_mode}/{style}"]
    # the CORDIC and the hybrid generator are approximations of the factor by
    # construction, so their allowance is the one of the generator and not of the
    # datapath alone - see the measurements in `test_fft_no_mem_model`
    ceiling = allowed(decomposition)
    if twiddle == "cordic":
        # the CORDIC resolves the angle in a fixed number of iterations, so its
        # error grows with the number of points
        ceiling = max(ceiling, 8.0 * int(math.log2(points)))
    elif twiddle != "rom":
        # the hybrid and the two memory free structures are close to the table:
        # a few units each, measured in `test_fft_no_mem_model`
        ceiling = max(ceiling, 4.0 * int(math.log2(points)))
    problems = []
    for label, frame in vectors(points, width):
        got = build(frame, width)
        want = golden(frame, width, points)
        worst = deviation(got, want)
        if worst > ceiling:
            problems.append(f"{label}: {worst:.1f} LSB, allowed {ceiling:.0f}")
    return problems


def all_configurations():
    """Every configuration the generator accepts."""
    for eval_mode in ("memory_based", "pipelined"):
        styles = ("sdf",) if eval_mode == "memory_based" else STYLES
        for style in styles:
            for points in POINTS:
                for decomposition in decompositions(points):
                    for ordering in ORDERINGS:
                        for scaling in SCALINGS:
                            for twiddle in TWIDDLE:
                                for inverse in (False, True):
                                    for width in WIDTHS:
                                        if is_legal(eval_mode, style, points,
                                                    decomposition, ordering,
                                                    twiddle, inverse,
                                                    width) is not None:
                                            continue
                                        yield {
                                            "eval_mode": eval_mode,
                                            "style": style,
                                            "points": points,
                                            "radices": as_text(decomposition),
                                            "decomposition": decomposition,
                                            "ordering": ordering,
                                            "scaling": scaling,
                                            "twiddle": twiddle,
                                            "inverse": inverse,
                                            "width": width,
                                        }


def summary() -> dict[str, int]:
    """How many configurations exist and where they come from."""
    counts: dict[str, int] = {}
    for config in all_configurations():
        key = config["style"] if config["eval_mode"] == "pipelined" else "memory"
        counts[key] = counts.get(key, 0) + 1
    counts["total"] = sum(counts.values())
    return counts


def full_configurations():
    """The whole accepted space, in the shape `fft_configs` uses.

    Each entry is what `build_fft_system` needs and what the test bench is
    parameterised by, so the stress matrix can be generated from the same
    enumeration the models are checked against.
    """
    from .fft_configs import _config

    for config in all_configurations():
        yield _config(
            width=config["width"],
            points=config["points"],
            ordering=config["ordering"],
            twiddle_mode=config["twiddle"],
            inverse=config["inverse"],
            scaling=config["scaling"],
            radices=config["radices"],
            eval_mode=config["eval_mode"],
            pipeline_style=config["style"],
            stages=1,
        )


def shard(configs: list, index: int, total: int) -> list:
    """The slice of ``configs`` which belongs to one machine of ``total``.

    The work is spread by the cost of a configuration rather than by its count:
    a shape is settled by its number of points and its number of stages, which
    say how many cycles a frame takes and how long the build is.  Splitting by
    count alone leaves one machine with all the large transforms and the others
    idle.
    """
    if not 0 <= index < total:
        raise ValueError(f"shard {index} is not one of {total}")
    costed = []
    for position, config in enumerate(configs):
        # A configuration is handed over in either of two shapes: the flat record
        # `all_configurations` produces, or the entry `fft_configs` produces with
        # its parameters under "params".  The weight is the same either way.
        params = config.get("params", config)
        stages = len(str(params["radices"]).split(","))
        points = params["points"]
        # a frame costs about `points` cycles, and the datapath is built once
        # per stage; the product is a proxy for both build time and run time
        weight = points * max(1, stages)
        costed.append((weight, position, config))
    costed.sort(key=lambda item: (-item[0], item[1]))

    # the largest shapes go to the emptiest machine, one after the other
    bins: list[list] = [[] for _ in range(total)]
    loads = [0] * total
    for weight, _, config in costed:
        lightest = loads.index(min(loads))
        bins[lightest].append(config)
        loads[lightest] += weight
    # keep the order of the space inside a shard, so a failure reads in order
    order = {id(config): position for position, config in enumerate(configs)}
    return sorted(bins[index], key=lambda config: order[id(config)])
