"""cocotb tests of a multi path delay feedback FFT with a radix chain.

16 bit datapath, 8 points with the radices
'2,4': the first stage splits the frame, the chains carry a
butterfly of their own radix.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_fft_tests

params = {'width': 16, 'points': 8, 'radices': '2,4', 'eval_mode': 'pipelined', 'pipeline_style': 'mdf', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake = make_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
