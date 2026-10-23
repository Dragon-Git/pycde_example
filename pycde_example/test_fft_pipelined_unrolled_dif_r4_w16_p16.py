"""cocotb tests of a mixed radix FFT.

16 bit datapath, 16 points with the radices
'4': each stage combines as many samples as its radix says.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 16, 'points': 16, 'radices': '4', 'eval_mode': 'pipelined', 'pipeline_style': 'unrolled', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
