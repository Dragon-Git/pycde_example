"""cocotb tests of the multi path delay commutator FFT.

16 bit datapath, 32 points: the first stage splits
the frame and two delay commutator chains transform the halves side by
side.
"""

from .cocotb_runner import run_cocotb
from .fft_tb import make_mdc_tests

params = {'width': 16, 'points': 32, 'radices': '2', 'eval_mode': 'pipelined', 'pipeline_style': 'mdc', 'twiddle_mode': 'rom', 'data_format': 'fixed', 'scaling': 'stage', 'stages': 1, 'inverse': False, 'ordering': 'dif', 'parallel': 1}

fft_result, fft_handshake = make_mdc_tests(**params)


def test_fft_runner():
    """The FFT is verified by the cocotb tests above (see cocotb_runner.py)."""
    run_cocotb(__name__)
