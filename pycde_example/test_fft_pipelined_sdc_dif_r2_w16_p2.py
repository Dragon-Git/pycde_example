"""cocotb tests of the single path delay commutator FFT, 2 points.

The smallest transform the architecture handles.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_streaming_fft_tests

params = {'width': 16, 'points': 2, 'radices': '2', 'eval_mode': 'pipelined', 'pipeline_style': 'sdc', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake, fft_backpressure = \
    make_streaming_fft_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
