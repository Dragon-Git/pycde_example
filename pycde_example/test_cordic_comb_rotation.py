"""cocotb tests of the fully combinational CORDIC in rotation mode.

16 bit datapath, 12 iterations.
"""

from .cordic_tb import make_cordic_tests

cordic_result, cordic_handshake = make_cordic_tests(arch="comb", mode="rotation",
                                                     width=16,
                                                     iterations=12)


def test_cordic_runner():
    """The CORDIC is verified by the cocotb tests above (see conftest.py)."""
