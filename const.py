from pycde.types import Bits, UInt

XLEN = 32
class Const:
    PC_START = Bits(XLEN)(0x200)
    PC_EVEC = Bits(XLEN)(0x100)