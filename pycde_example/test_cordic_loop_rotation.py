"""cocotb tests of the loop (iterative) CORDIC in rotation mode.

32 bit datapath, 16 iterations.
"""

from .cocotb_runner import run_cocotb
from .cordic_tb import make_cordic_tests

cordic_result, cordic_handshake = make_cordic_tests(arch="loop", mode="rotation",
                                                     width=32,
                                                     iterations=16)


def test_cordic_runner():
    """The CORDIC is verified by the cocotb tests above (see conftest.py)."""
    run_cocotb(__name__)
