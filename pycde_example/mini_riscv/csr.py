from dataclasses import dataclass
from pycde.types import Bits
from pycde.constructs import Reg
from pycde.signals import BitsSignal

from .const import Const

XLEN = 32


@dataclass()
class CSR_REG:
    name: str
    addr: Bits(12)
    access: str
    value: any
    next: any = None

    def __post_init__(self):
        self.value.name = self.name
        if self.access == "RW":
            self.next = self.value

    def __hash__(self):
        return hash(self.name)


class CSR:
    def __init__(self):
        # Supports machine & user modes
        self.PRV_U = Bits(2)(0x0)
        self.PRV_M = Bits(2)(0x3)
        # User-level CSR addrs
        self.cycle = CSR_REG("cycle", Bits(12)(0xC00), "RW", Reg(Bits(XLEN)))

        self.time = CSR_REG("time", Bits(12)(0xC01), "RW", Reg(Bits(XLEN)))
        self.instret = CSR_REG("instret", Bits(12)(0xC02), "RW", Reg(Bits(XLEN)))
        self.cycleh = CSR_REG("cycleh", Bits(12)(0xC80), "RW", Reg(Bits(XLEN)))
        self.timeh = CSR_REG("timeh", Bits(12)(0xC81), "RW", Reg(Bits(XLEN)))
        self.instreth = CSR_REG("instreth", Bits(12)(0xC82), "RW", Reg(Bits(XLEN)))

        # Supervisor-level CSR addrs
        self.cyclew = CSR_REG("cycle", Bits(12)(0x900), "RW", self.cycle.value)
        self.timew = CSR_REG("time", Bits(12)(0x901), "RW", self.time.value)
        self.instretw = CSR_REG("instret", Bits(12)(0x902), "RW", self.instret.value)
        self.cyclehw = CSR_REG("cycleh", Bits(12)(0x980), "RW", self.cycleh.value)
        self.timehw = CSR_REG("timeh", Bits(12)(0x981), "RW", self.timeh.value)
        self.instrethw = CSR_REG("instreth", Bits(12)(0x982), "RW", self.instreth.value)

        # Machine-level CSR addrs
        # Machine Information Registers
        self.mcpuid = CSR_REG(
            "mcpuid",
            Bits(12)(0xF00),
            "RO",
            BitsSignal.concat(
                [
                    Bits(26)(1 << (ord("I") - ord("A")) | 1 << (ord("U") - ord("A"))),  # Base ISA  # User Mode
                    Bits(XLEN - 28)(0),
                    Bits(2)(0),  # RV32I
                ]
            ),
        )
        self.mimpid = CSR_REG("mimpid", Bits(12)(0xF01), "RO", Bits(XLEN)(0))
        self.mhartid = CSR_REG("mhartid", Bits(12)(0xF10), "RO", Bits(XLEN)(0))

        # Machine Trap Setup
        self.mstatus = CSR_REG("mstatus", Bits(12)(0x300), "RW", Reg(Bits(XLEN)))
        self.mtvec = CSR_REG("mtvec", Bits(12)(0x301), "RO", Const().PC_EVEC)
        self.mtdeleg = CSR_REG("mtdeleg", Bits(12)(0x302), "RO", Bits(XLEN)(0))
        self.mie = CSR_REG("mie", Bits(12)(0x304), "RW", Reg(Bits(XLEN)))
        self.mtimecmp = CSR_REG("mtimecmp", Bits(12)(0x321), "RW", Reg(Bits(XLEN)))

        # Machine Timers and Counters
        self.mtime = CSR_REG("time", Bits(12)(0x701), "RW", self.time.value)
        self.mtimeh = CSR_REG("timeh", Bits(12)(0x741), "RW", self.timeh.value)

        # Machine Trap Handling
        self.mscratch = CSR_REG("mscratch", Bits(12)(0x340), "RW", Reg(Bits(XLEN)))
        self.mepc = CSR_REG("mepc", Bits(12)(0x341), "RW", Reg(Bits(XLEN)))
        self.mcause = CSR_REG("mcause", Bits(12)(0x342), "RW", Reg(Bits(XLEN)))
        self.mbadaddr = CSR_REG("mbadaddr", Bits(12)(0x343), "RW", Reg(Bits(XLEN)))
        self.mip = CSR_REG("mip", Bits(12)(0x344), "RW", Reg(Bits(XLEN)))

        # Machine HITF
        self.mtohost = CSR_REG("mtohost", Bits(12)(0x780), "RW", Reg(Bits(XLEN)))
        self.mfromhost = CSR_REG("mfromhost", Bits(12)(0x781), "RW", Reg(Bits(XLEN)))

        self.regs = [i for i in self.__dict__.values() if isinstance(i, CSR_REG)]
