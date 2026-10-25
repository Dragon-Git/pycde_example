"""cocotb tests of a sdc FFT.

16 bit datapath, 8 points with the radices
'4,2'.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_streaming_fft_tests

params = {'width': 16, 'points': 8, 'radices': '4,2', 'eval_mode': 'pipelined', 'pipeline_style': 'sdc', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake, fft_backpressure = \
    make_streaming_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
