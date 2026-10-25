"""cocotb tests of a radix mixed delay feedback FFT.

16 bit datapath, 8 points with the radices
'8': one chain of stages, each with a butterfly of its radix.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 16, 'points': 8, 'radices': '8', 'eval_mode': 'pipelined', 'pipeline_style': 'sdf', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
