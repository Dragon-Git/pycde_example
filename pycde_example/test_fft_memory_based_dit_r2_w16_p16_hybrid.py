"""cocotb tests of the memory based FFT, hybrid twiddle factors.

16 bit datapath, 16 points: a coarse CORDIC turns the
vector and a small correction table finishes the angle.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 16, 'points': 16, 'radices': '2', 'eval_mode': 'memory_based', 'pipeline_style': 'sdf', 'twiddle_mode': 'hybrid', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dit', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
