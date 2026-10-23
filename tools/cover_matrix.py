"""Check every configuration the generator accepts against NumPy.

The RTL matrix in `fft_configs.py` is a selection, because every point of it costs
a Verilator build and a simulation.  The arithmetic can be covered whole: this
walks the parameter space, works out which model computes each configuration, and
checks it against the golden.

It is a tool rather than a test because the sweep takes minutes; the tests carry a
representative slice of the same thing, see `test_fft_matrix.py`.

Run it with `python tools/cover_matrix.py`; `--quiet` prints only failures and the
summary.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, ".")

from pycde_example.fft_matrix import all_configurations, as_text, check, summary


def main() -> int:
    """Sweep the space and report."""
    quiet = "--quiet" in sys.argv
    counts = summary()
    print("the space the generator accepts")
    for key, value in counts.items():
        print(f"  {key:10s} {value}")

    # A configuration is identified by what it computes: the topology, the number
    # of points, the decomposition and the ordering.  The twiddle generator, the
    # scaling and the inverse do not change the transform, so a shape is worked out
    # once and its variants are noted beside it.
    seen: dict[tuple, list[dict]] = {}
    for config in all_configurations():
        key = (config["eval_mode"], config["style"], config["points"],
               config["decomposition"], config["ordering"])
        seen.setdefault(key, []).append(config)

    variants = sum(len(value) for value in seen.values())
    print()
    print(f"{len(seen)} distinct computations, {variants} configurations")

    failures = 0
    started = time.time()
    for index, (key, configs) in enumerate(seen.items(), start=1):
        eval_mode, style, points, decomposition, ordering = key
        # the widest datapath, because a narrower one only truncates more
        width = max(config["width"] for config in configs)
        # the twiddle generator is part of the arithmetic, so each is checked
        for twiddle in sorted({config["twiddle"] for config in configs}):
            problems = check(eval_mode, style, points, decomposition, width,
                             twiddle, ordering)
            if problems:
                failures += 1
                print(f"  FAIL {eval_mode}/{style} N={points} "
                      f"R={as_text(decomposition)} {ordering} {twiddle}: "
                      f"{problems[:2]}")
            elif not quiet:
                print(f"  ok   {eval_mode}/{style} N={points} "
                      f"R={as_text(decomposition)} {ordering} {twiddle}")
        if index % 100 == 0:
            print(f"  ... {index}/{len(seen)} shapes, "
                  f"{time.time() - started:.0f}s")

    print()
    print(f"{failures} failures over {len(seen)} shapes in "
          f"{time.time() - started:.0f}s")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
