from dataclasses import dataclass
from pycde.types import Bits, UInt
from pycde.constructs import Mux, Reg
from pycde.signals import ArraySignal, BitsSignal, Or

from const import Const
@dataclass()
class CSR_REG:
    name:str
    addr:Bits(12)
    access:str
    value:any
    next:any = None

    def __post_init__(self):
        self.value.name = self.name
        if self.access == "RW":
            self.next = self.value

    def __hash__(self):
        return(hash(self.name))

XLEN = 32

class CSR:
    N = Bits(3)(0)
    W = Bits(3)(1)
    S = Bits(3)(2)
    C = Bits(3)(3)
    P = Bits(3)(4)

    # Supports machine & user modes
    PRV_U = Bits(2)(0x0)
    PRV_M = Bits(2)(0x3)

    # User-level CSR addrs
    cycle = CSR_REG("cycle", Bits(12)(0xc00), "RW", Reg(Bits(XLEN)))
    time = CSR_REG("time", Bits(12)(0xc01), "RW", Reg(Bits(XLEN)))
    instret = CSR_REG("instret", Bits(12)(0xc02), "RW", Reg(Bits(XLEN)))
    cycleh = CSR_REG("cycleh", Bits(12)(0xc80), "RW", Reg(Bits(XLEN)))
    timeh = CSR_REG("timeh", Bits(12)(0xc81), "RW", Reg(Bits(XLEN)))
    instreth = CSR_REG("instreth", Bits(12)(0xc82), "RW", Reg(Bits(XLEN)))

    # Supervisor-level CSR addrs
    cyclew = CSR_REG("cycle", Bits(12)(0x900), "RW", cycle.value)
    timew = CSR_REG("time", Bits(12)(0x901), "RW", time.value)
    instretw = CSR_REG("instret", Bits(12)(0x902), "RW", instret.value)
    cyclehw = CSR_REG("cycleh", Bits(12)(0x980), "RW", cycleh.value)
    timehw = CSR_REG("timeh", Bits(12)(0x981), "RW", timeh.value)
    instrethw = CSR_REG("instreth", Bits(12)(0x982), "RW", instreth.value)

    # Machine-level CSR addrs
    # Machine Information Registers
    mcpuid = CSR_REG("mcpuid", Bits(12)(0xf00), "RO", BitsSignal.concat([
            Bits(26)(1 << (ord('I') - ord('A')) |  # Base ISA
                   1 << (ord('U') - ord('A'))),  # User Mode
            Bits(XLEN - 28)(0),
            Bits(2)(0),  # RV32I
        ])
        )
    mimpid = CSR_REG("mimpid", Bits(12)(0xf01), "RO", Bits(XLEN)(0))
    mhartid = CSR_REG("mhartid", Bits(12)(0xf10), "RO", Bits(XLEN)(0))

    # Machine Trap Setup
    mstatus = CSR_REG("mstatus", Bits(12)(0x300), "RW", Reg(Bits(XLEN)))
    mtvec = CSR_REG("mtvec", Bits(12)(0x301), "RO", Const.PC_EVEC)
    mtdeleg = CSR_REG("mtdeleg", Bits(12)(0x302), "RO", Bits(XLEN)(0))
    mie = CSR_REG("mie", Bits(12)(0x304), "RW", Reg(Bits(XLEN)))
    mtimecmp = CSR_REG("mtimecmp", Bits(12)(0x321), "RW", Reg(Bits(XLEN)))

    # Machine Timers and Counters
    mtime = CSR_REG("time", Bits(12)(0x701), "RW", time.value)
    mtimeh = CSR_REG("timeh", Bits(12)(0x741), "RW", timeh.value)

    # Machine Trap Handling
    mscratch = CSR_REG("mscratch", Bits(12)(0x340), "RW", Reg(Bits(XLEN)))
    mepc = CSR_REG("mepc", Bits(12)(0x341), "RW", Reg(Bits(XLEN)))
    mcause = CSR_REG("mcause", Bits(12)(0x342), "RW", Reg(Bits(XLEN)))
    mbadaddr = CSR_REG("mbadaddr", Bits(12)(0x343), "RW", Reg(Bits(XLEN)))
    mip = CSR_REG("mip", Bits(12)(0x344), "RW", Reg(Bits(XLEN)))

    # Machine HITF
    mtohost = CSR_REG("mtohost", Bits(12)(0x780), "RW", Reg(Bits(XLEN)))
    mfromhost = CSR_REG("mfromhost", Bits(12)(0x781), "RW", Reg(Bits(XLEN)))

    regs = (cycle, time, instret, cycleh, timeh, instreth, cyclew, timew,
            instretw, cyclehw, timehw, instrethw, mcpuid, mimpid, mhartid,
            mtvec, mtdeleg, mie, mtimecmp, mtime, mtimeh, mscratch, mepc,
            mcause, mbadaddr, mip, mtohost, mfromhost, mstatus)
    