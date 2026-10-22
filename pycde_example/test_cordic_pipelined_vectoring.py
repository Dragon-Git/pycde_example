"""cocotb tests of the pipelined CORDIC in vectoring mode.

24 bit datapath, 12 iterations.
"""

from .cocotb_runner import run_cocotb
from .cordic_tb import make_cordic_tests

cordic_result, cordic_handshake = make_cordic_tests(arch="pipelined", mode="vectoring",
                                                     width=24,
                                                     iterations=12)


def test_cordic_runner():
    """The CORDIC is verified by the cocotb tests above (see conftest.py)."""
    run_cocotb(__name__)
