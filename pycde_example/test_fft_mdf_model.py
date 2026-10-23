"""Unit tests of the bit exact model of the multi path delay feedback.

The architecture is a butterfly of the first stage followed by two delay feedback
chains, one per half of the frame.  The tests check it against the reference
model of the transform, over different frames fed one after another as well,
since the chains hold the data of the previous frame.
"""

from __future__ import annotations

import math
import random

import pytest

from .fft_mdf_model import MdfPath, chain_radices, mdf
from .fft_model import fft, to_fixed


def random_samples(points: int, width: int, seed: int = 0,
                   amplitude: float = 0.4) -> list[tuple[int, int]]:
    """Deterministic random samples with a magnitude below ``amplitude``."""
    rng = random.Random(seed)
    samples = []
    for _ in range(points):
        radius = rng.uniform(0.0, amplitude)
        angle = rng.uniform(0.0, 2.0 * math.pi)
        samples.append((to_fixed(radius * math.cos(angle), width),
                        to_fixed(radius * math.sin(angle), width)))
    return samples


@pytest.mark.parametrize("width,points", [(16, 4), (16, 8), (16, 16),
                                          (16, 32), (24, 32)])
def test_mdf_matches_the_transform(width, points):
    """The multi path delay feedback computes the same spectrum, bit for bit."""
    for seed in range(3):
        samples = random_samples(points, width, seed=points + seed)
        assert mdf(samples, width, points) == fft(samples, width, points,
                                                   dit=False, scale=True)


@pytest.mark.parametrize("width,points", [(24, 8), (24, 16)])
def test_mdf_without_scaling(width, points):
    """The stages can be left unscaled if the datapath is wide enough."""
    samples = random_samples(points, width, seed=points, amplitude=0.02)
    assert mdf(samples, width, points, scale=False) == fft(
        samples, width, points, dit=False, scale=False)


def test_mdf_path_is_a_delay_feedback_chain():
    """A path of the architecture is a chain of its own, half as long."""
    width, points = 16, 16
    half = points // 2
    path = MdfPath(width, half, True, [])
    # the number of stages is one less than the whole transform needs
    assert path.levels == (points.bit_length() - 1) - 1
    # the storage of a chain is points / 2 - 1 for its own points
    assert sum(path.delays) == half - 1


def test_mdf_impulse_response():
    """An impulse in the input is flat in the output."""
    width, points = 16, 16
    samples = [(to_fixed(0.5, width), 0)] + [(0, 0)] * (points - 1)
    got = mdf(samples, width, points)
    expected = to_fixed(0.5 / points, width)
    for k in range(points):
        assert got[k] == (expected, 0)


def test_mdf_is_deterministic():
    width, points = 16, 8
    samples = random_samples(points, width, seed=19)
    assert mdf(samples, width, points) == mdf(samples, width, points)


# The commutator sibling shares the arithmetic and differs in the datapath of a
# chain, so the two have to agree bit for bit; that is what makes one model
# enough for both topologies.
def test_the_commutator_sibling_computes_the_same_spectrum():
    """The two multi path architectures differ in shape, not in arithmetic."""
    from .fft_mdc_model import mdc

    for points in (4, 8, 16, 32):
        for radices in ("2", "2,4", "2,2,4"):
            try:
                stages = chain_radices(radices, points)
            except ValueError:
                continue
            del stages
            for seed in range(2):
                frame = random_samples(points, 16, seed=points + seed)
                assert (mdc(frame, 16, points, radices=radices)
                        == mdf(frame, 16, points, radices=radices)), \
                    f"{radices} on {points} points"


def test_the_commutator_sibling_agrees_with_the_golden():
    """The commutator sibling is checked against NumPy too, not just the other."""
    from .fft_golden import deviation, golden, truncation_bound
    from .fft_mdc_model import mdc

    for points, radices in ((8, "2"), (16, "2,4,2"), (16, "2,8")):
        for seed in range(2):
            frame = random_samples(points, 16, seed=points + seed)
            got = mdc(frame, 16, points, radices=radices)
            worst = deviation(got, golden(frame, 16, points))
            # the chains are the radices after the stage which splits the frame
            allowed = truncation_bound(chain_radices(radices, points))
            assert worst <= allowed, f"{radices} off by {worst:.2f}"
