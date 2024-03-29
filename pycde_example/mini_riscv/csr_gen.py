from pycde import System, Module, Clock, Reset, Input, Output, generator, types, dim  # noqa: F401
from pycde.types import Bits
from pycde.constructs import Mux
from pycde.signals import BitsSignal, Or

from .instructions import RV32I
from .csr import CSR_, CSR_CMD_
from .const import XLEN


class Cause:
    def __init__(self) -> None:
        self.InstAddrMisaligned = Bits(XLEN)(0x0)
        self.IllegalInst = Bits(XLEN)(0x2)
        self.Breakpoint = Bits(XLEN)(0x3)
        self.LoadAddrMisaligned = Bits(XLEN)(0x4)
        self.StoreAddrMisaligned = Bits(XLEN)(0x6)
        self.Ecall = Bits(XLEN)(0x8)


class CSRGen(Module):
    clk = Clock()
    rst = Reset()
    stall = Input(Bits(1))
    cmd = Input(Bits(3))
    In = Input(Bits(XLEN))
    Out = Output(Bits(XLEN))
    # Excpetion
    pc = Input(Bits(XLEN))
    addr = Input(Bits(XLEN))
    insn = Input(Bits(XLEN))
    illegal = Input(Bits(1))
    st_type = Input(Bits(2))
    ld_type = Input(Bits(3))
    pc_check = Input(Bits(1))
    expt = Output(Bits(1))
    evec = Output(Bits(XLEN))
    epc = Output(Bits(XLEN))

    @generator
    def build(io):

        CSR = CSR_()
        CSR_CMD = CSR_CMD_()
        rv32i = RV32I()
        cause = Cause()

        csr_addr = io.insn[20:32]
        rs1_addr = io.insn[15:20]

        # read block
        lookup = Bits(XLEN)(0)
        for reg in CSR.regs:
            is_reg = reg.addr == csr_addr
            is_reg.name = f"lookup_{reg.name}"
            lookup = Mux(is_reg, lookup, reg.value)
        lookup.name = "lookup"
        io.Out = lookup

        # get next value
        priv_valid = Bits(1)(0)  # TODO: csr_addr[8:10] <= PRV
        priv_inst = io.cmd == CSR_CMD.P
        is_E_call = priv_inst & ~csr_addr[0] & ~csr_addr[8]
        is_E_break = priv_inst & csr_addr[0] & ~csr_addr[8]
        is_E_ret = priv_inst & ~csr_addr[0] & csr_addr[8]
        csr_valid = Or(*[csr_addr == reg.addr for reg in CSR.regs])
        csr_RO = (csr_addr[10] & csr_addr[11]) | (csr_addr == CSR.mtvec.addr) | (csr_addr == CSR.mtdeleg.addr)
        wen = (io.cmd == CSR_CMD.W) | io.cmd[1] & rs1_addr.or_reduce()
        wen.name = "wen"
        wdata = Bits(XLEN)(0)
        wdata = Mux(io.cmd == CSR_CMD.C, wdata, lookup & ~io.In)
        wdata = Mux(io.cmd == CSR_CMD.S, wdata, lookup | io.In)
        wdata = Mux(io.cmd == CSR_CMD.W, wdata, io.In)
        wdata.name = "wdata"

        iaddr_invalid = io.pc_check & io.addr[1]

        laddr_invalid = Bits(1)(0)
        laddr_invalid = Mux(io.ld_type == Bits(3)(4), laddr_invalid, io.addr[0])
        laddr_invalid = Mux(io.ld_type == Bits(3)(2), laddr_invalid, io.addr[0])
        laddr_invalid = Mux(io.ld_type == Bits(3)(1), laddr_invalid, io.addr[0] | io.addr[1])
        laddr_invalid.name = "laddr_invalid"

        saddr_invalid = Bits(1)(0)
        saddr_invalid = Mux(io.st_type == Bits(2)(2), saddr_invalid, io.addr[0])
        saddr_invalid = Mux(io.st_type == Bits(2)(1), saddr_invalid, io.addr[0] | io.addr[1])
        saddr_invalid.name = "saddr_invalid"
        expt = (io.illegal | iaddr_invalid | laddr_invalid | saddr_invalid | (io.cmd[0] | io.cmd[1])
                & (~csr_valid | ~priv_valid) | wen & csr_RO | (priv_inst & ~priv_valid) | is_E_call | is_E_break)
        io.expt = expt
        io.evec = Bits(XLEN)(0)
        io.epc = CSR.mepc.value

        is_inst_ret = (io.insn != rv32i.NOP) & (~expt | is_E_call | is_E_break) & ~io.stall
        is_inst_ret.name = "is_inst_ret"

        is_inst_reth = is_inst_ret & CSR.instret.value.as_bits().and_reduce()
        is_inst_reth.name = "is_inst_reth"

        is_mbadaddr = iaddr_invalid | laddr_invalid | saddr_invalid
        is_mbadaddr.name = "is_mbadaddr"

        # Counters
        CSR.time.next = (CSR.time.value.as_uint(32) + 1).as_bits(32)
        CSR.timeh.next = Mux(CSR.time.value.and_reduce(), CSR.timeh.value, (CSR.timeh.value.as_uint(XLEN) + 1).as_bits(XLEN))  # noqa: E501
        CSR.cycle.next = (CSR.cycle.value.as_uint(32) + 1).as_bits(32)
        CSR.cycleh.next = Mux(CSR.cycle.value.and_reduce(), CSR.cycleh.value, (CSR.cycleh.value.as_uint(XLEN) + 1).as_bits(XLEN))  # noqa: E501
        CSR.instret.next = Mux(is_inst_ret, CSR.instret.value, (CSR.instret.value.as_uint(XLEN) + 1).as_bits(XLEN))
        CSR.instreth.next = Mux(is_inst_reth, CSR.instreth.value, (CSR.instreth.value.as_uint(XLEN) + 1).as_bits(XLEN))

        CSR.mepc.next   = Mux(~io.stall & expt, CSR.mepc.next, io.pc & Bits(XLEN)((1<<XLEN)-4))
        CSR.mcause.next = Mux(~io.stall & expt & iaddr_invalid, cause.InstAddrMisaligned,
                Mux(~io.stall & expt & laddr_invalid, cause.LoadAddrMisaligned,
                Mux(~io.stall & expt & saddr_invalid, cause.StoreAddrMisaligned,
                Mux(~io.stall & expt & is_E_call,     cause.Ecall, # need add PRV
                Mux(~io.stall & expt & is_E_break,    cause.Breakpoint, cause.IllegalInst)))))
        CSR.mbadaddr.next   = Mux(~io.stall & expt & is_mbadaddr, CSR.mbadaddr.next, io.addr)
        CSR.mstatus.next   = Mux(~io.stall & expt, CSR.mstatus.next, BitsSignal.concat([CSR.mstatus.next.as_bits()[6:], CSR.mstatus.next.as_bits()[:3], CSR.PRV_M, Bits(1)(0)]))  # noqa: E501
        CSR.mstatus.next   = Mux(~io.stall & is_E_ret, CSR.mstatus.next, BitsSignal.concat([CSR.mstatus.next.as_bits()[6:], CSR.PRV_U, Bits(1)(1), CSR.mstatus.next.as_bits()[3:6]]))  # noqa: E501


        reg_assign_dict = {}
        for reg in CSR.regs:
            if reg.access == "RW":
                if reg in reg_assign_dict:
                    reg_assign_dict[reg] = Mux((reg.addr == csr_addr) & wen, reg_assign_dict[reg], wdata)
                else:
                    reg_assign_dict[reg] = Mux((reg.addr == csr_addr) & wen, reg.next, wdata)

        # assign block
        for reg, next in reg_assign_dict.items():
            reg.value.assign(next)


if __name__ == '__main__':
    mod = System([CSRGen],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
