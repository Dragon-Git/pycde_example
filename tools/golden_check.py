"""Compare every model against an independent golden reference.

The models share their arithmetic: `fft_mixed`, `sdf_radix` and `sdc_radix` all
rotate with `apply_twiddle`, so a mistake there is a mistake in all of them and
comparing them with each other finds nothing.  The golden reference here is
NumPy's transform, which shares no code with any of them.

Two things are asked of a model:

* it has to be close to the golden, within a bound derived from the datapath
  rather than fitted to the measurement;
* every topology has to be bit identical with every other one which computes the
  same decomposition, because they differ in the datapath and not in the
  arithmetic.

Run it with `python tools/golden_check.py`.
"""
from __future__ import annotations

import math
import sys

import numpy as np

sys.path.insert(0, ".")

from pycde_example.fft_model import fft, to_fixed
from pycde_example.fft_radix_model import fft_mixed
from pycde_example.fft_sdc_radix_model import sdc_radix
from pycde_example.fft_sdf_radix_model import sdf_radix


def golden(frame: list[tuple[int, int]], width: int, points: int) -> np.ndarray:
    """The transform of the frame, computed by NumPy.

    The frame is a fixed point number with `width - 1` fractional bits, so the
    value it stands for is the integer divided by `2**(width - 1)`; the result is
    brought back to the same scale and divided by the number of points, because
    the datapath scales every stage.
    """
    scale = 1 << (width - 1)
    values = np.array([complex(re, im) for re, im in frame]) / scale
    return np.fft.fft(values) * scale / points


def error_in_lsb(got: list[tuple[int, int]], want: np.ndarray) -> float:
    """The largest deviation, in units of the last bit."""
    worst = 0.0
    for (re, im), value in zip(got, want):
        worst = max(worst, abs(re - value.real), abs(im - value.imag))
    return worst


def bound(radices: list[int]) -> float:
    """The deviation the datapath is allowed, derived from its arithmetic.

    Every stage shifts its operands right, which drops up to one unit of the last
    bit per term, and every rotation truncates a product the same way.  A stage
    of radix `R` therefore adds up to a couple of units per term, and the errors
    of the stages add up - so the bound grows with the number of stages and with
    the width of the butterfly.

    It is deliberately generous: it is here to catch a model which is
    structurally wrong - those are off by thousands of units - and not to make a
    statement about a single unit either way.
    """
    stages = len(radices)
    widest = max(int(math.log2(radix)) for radix in radices)
    return 8.0 * (stages + 1) * (widest + 1)


def frames(points: int, width: int):
    """Frames with different shapes: an impulse, a tone and noise."""
    scale = 1 << (width - 1)
    impulse = [(0, 0)] * points
    impulse[0] = (to_fixed(0.5, width), 0)
    yield "impulse", impulse

    tone = []
    for n in range(points):
        angle = 2.0 * math.pi * 3 * n / points
        tone.append((to_fixed(0.4 * math.cos(angle), width),
                     to_fixed(0.4 * math.sin(angle), width)))
    yield "tone", tone

    rng = np.random.default_rng(12345 + points)
    noise = []
    for _ in range(points):
        radius = rng.uniform(0.0, 0.3)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        noise.append((round(scale * radius * math.cos(angle)),
                      round(scale * radius * math.sin(angle))))
    yield "noise", noise


def report(name: str, points: int, width: int, radices: str,
           compute) -> bool:
    """Check one model against the golden, and print what it did."""
    stages = [int(part) for part in radices.split(",")]
    worst = 0.0
    worst_frame = ""
    for label, frame in frames(points, width):
        deviation = error_in_lsb(compute(frame), golden(frame, width, points))
        if deviation > worst:
            worst, worst_frame = deviation, label
    allowed = bound(stages)
    ok = worst <= allowed
    print(f"  {name:11s} radices={radices:6s} N={points:3d}: "
          f"worst {worst:8.2f} LSB (bound {allowed:5.1f}) "
          f"{'ok' if ok else 'FAIL'}  [{worst_frame}]")
    return ok


def main() -> int:
    """Check every model against the golden and against the others."""
    failures = 0
    width = 16

    print("against the NumPy transform")
    for points in (4, 8, 16, 32, 64):
        radices = ",".join(["2"] * int(math.log2(points)))
        if not report("fft (radix 2)", points, width, radices,
                      lambda f, n=points: fft(f, width, n, dit=False)):
            failures += 1
        if not report("fft_mixed", points, width, radices,
                      lambda f, n=points, r=radices: fft_mixed(
                          f, width, n, r, dit=False)):
            failures += 1

    for points, radices in ((4, "4"), (16, "4"), (64, "4"), (8, "8"),
                            (64, "8"), (8, "4,2"), (8, "2,4"), (16, "4,4"),
                            (16, "8,2"), (16, "2,8")):
        if not report("fft_mixed", points, width, radices,
                      lambda f, n=points, r=radices: fft_mixed(
                          f, width, n, r, dit=False)):
            failures += 1
        if not report("sdf_radix", points, width, radices,
                      lambda f, n=points, r=radices: sdf_radix(f, width, n, r)):
            failures += 1
        if not report("sdc_radix", points, width, radices,
                      lambda f, n=points, r=radices: sdc_radix(f, width, n, r)):
            failures += 1

    print()
    print("the topologies against each other, bit for bit")
    for points, radices in ((16, "4"), (16, "4,4"), (8, "8"), (8, "4,2"),
                            (16, "8,2")):
        for label, frame in frames(points, width):
            mixed = fft_mixed(frame, width, points, radices, dit=False)
            delay = sdf_radix(frame, width, points, radices)
            commutator = sdc_radix(frame, width, points, radices)
            if not (mixed == delay == commutator):
                failures += 1
                print(f"  radices={radices:6s} N={points:3d} [{label}]: "
                      f"mixed vs sdf {mixed != delay}, "
                      f"sdf vs sdc {delay != commutator}")

    print()
    print("every model agrees with the golden and with the others"
          if failures == 0 else f"{failures} checks failed")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
