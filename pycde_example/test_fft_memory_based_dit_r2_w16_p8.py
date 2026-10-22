"""cocotb tests of the memory_based FFT in dit mode.

16 bit datapath, 8 points, twiddle factors from
the rom, forward transform.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 16, 'points': 8, 'radices': '2', 'eval_mode': 'memory_based', 'pipeline_style': 'sdf', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'inverse': False, 'ordering': 'dit', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
