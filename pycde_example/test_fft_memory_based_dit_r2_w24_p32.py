"""cocotb tests of the memory_based FFT in dit mode.

24 bit datapath, 32 points, 1 pipeline stage(s),
twiddle factors from the rom.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 24, 'points': 32, 'radices': '2', 'eval_mode': 'memory_based', 'pipeline_style': 'sdf', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dit', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
