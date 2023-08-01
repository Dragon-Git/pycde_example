from pycde.types import Bits

XLEN = 32
class PC_const:
    def __init__(self):
        self.PC_START = Bits(XLEN)(0x200)
        self.PC_EVEC = Bits(XLEN)(0x100)