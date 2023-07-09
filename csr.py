from pycde.types import Bits


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
    cycle = Bits(12)(0xc00)
    time = Bits(12)(0xc01)
    instret = Bits(12)(0xc02)
    cycleh = Bits(12)(0xc80)
    timeh = Bits(12)(0xc81)
    instreth = Bits(12)(0xc82)

    # Supervisor-level CSR addrs
    cyclew = Bits(12)(0x900)
    timew = Bits(12)(0x901)
    instretw = Bits(12)(0x902)
    cyclehw = Bits(12)(0x980)
    timehw = Bits(12)(0x981)
    instrethw = Bits(12)(0x982)

    # Machine-level CSR addrs
    # Machine Information Registers
    mcpuid = Bits(12)(0xf00)
    mimpid = Bits(12)(0xf01)
    mhartid = Bits(12)(0xf10)

    # Machine Trap Setup
    mstatus = Bits(12)(0x300)
    mtvec = Bits(12)(0x301)
    mtdeleg = Bits(12)(0x302)
    mie = Bits(12)(0x304)
    mtimecmp = Bits(12)(0x321)

    # Machine Timers and Counters
    mtime = Bits(12)(0x701)
    mtimeh = Bits(12)(0x741)

    # Machine Trap Handling
    mscratch = Bits(12)(0x340)
    mepc = Bits(12)(0x341)
    mcause = Bits(12)(0x342)
    mbadaddr = Bits(12)(0x343)
    mip = Bits(12)(0x344)

    # Machine HITF
    mtohost = Bits(12)(0x780)
    mfromhost = Bits(12)(0x781)

    regs = (cycle, time, instret, cycleh, timeh, instreth, cyclew, timew,
            instretw, cyclehw, timehw, instrethw, mcpuid, mimpid, mhartid,
            mtvec, mtdeleg, mie, mtimecmp, mtime, mtimeh, mscratch, mepc,
            mcause, mbadaddr, mip, mtohost, mfromhost, mstatus)
    
    @classmethod
    def getname(cls, var):
        return [name for name, value in vars(cls).items() if value is var][0]