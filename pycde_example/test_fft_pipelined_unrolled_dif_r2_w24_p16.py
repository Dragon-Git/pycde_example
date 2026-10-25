"""cocotb tests of a unrolled FFT.

24 bit datapath, 16 points with the radices
'2'.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 24, 'points': 16, 'radices': '2', 'eval_mode': 'pipelined', 'pipeline_style': 'unrolled', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'none', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake = \
    make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
