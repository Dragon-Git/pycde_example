from pycde import (System, Module, Input, Output, generator, types, dim)  # noqa: F401
from pycde.common import Clock, Reset
from pycde.types import Bits, SInt, UInt, List  # noqa: F401
from pycde.behavioral import If, Else, EndIf
from pycde.constructs import Mux, Reg
from pycde.signals import ArraySignal, BitsSignal, Or, And

XLEN = 32

def make_Cause(XLEN):
    class Cause:
        InstAddrMisaligned = Bits(XLEN)(0x0)
        IllegalInst = Bits(XLEN)(0x2)
        Breakpoint = Bits(XLEN)(0x3)
        LoadAddrMisaligned = Bits(XLEN)(0x4)
        StoreAddrMisaligned = Bits(XLEN)(0x6)
        Ecall = Bits(XLEN)(0x8)
    return Cause


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
    inst = Input(Bits(XLEN))
    illegal = Input(Bits(1))
    st_type = Input(Bits(2))
    ld_type = Input(Bits(3))
    pc_check = Input(Bits(1))
    expt = Output(Bits(1))
    evec = Output(Bits(XLEN)),
    epc = Output(Bits(XLEN))
  
    @generator
    def build(io):
        from csr import CSR
        import instructions as rv32i

        csr_addr = io.inst[20:32]
        rs1_addr = io.inst[15:20]

        # read block
        lookup = Bits(32)(0)
        for reg in CSR.regs:
            is_reg = reg.addr == csr_addr
            is_reg.name = f"lookup_{reg.name}"
            lookup = Mux(is_reg, lookup, reg.value)
        lookup.name = "lookup"
        io.Out = lookup

        # get next value
        priv_valid = Bits(1)(0) #TODO: csr_addr[8:10] <= PRV
        priv_inst = io.cmd == CSR.P
        is_E_call = priv_inst & ~csr_addr[0] & ~csr_addr[8]
        is_E_break = priv_inst & csr_addr[0] & ~csr_addr[8]
        is_E_ret = priv_inst & ~csr_addr[0] & csr_addr[8]
        csr_valid = Or(*[csr_addr == reg.addr for reg in CSR.regs])
        csr_RO = ((csr_addr[10] & csr_addr[11]) | (csr_addr == CSR.mtvec.addr) | (csr_addr == CSR.mtdeleg.addr))
        wen = (io.cmd == CSR.W) | io.cmd[1] & Or(*[rs1_addr[i] for i in range(len(rs1_addr))])
        wen.name = "wen"
        wdata = Bits(XLEN)(0)
        wdata = Mux(io.cmd == CSR.C, wdata, lookup & ~io.In)
        wdata = Mux(io.cmd == CSR.S, wdata, lookup | io.In)
        wdata = Mux(io.cmd == CSR.W, wdata, io.In)
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
        expt = (io.illegal | iaddr_invalid | laddr_invalid | saddr_invalid |
                (io.cmd[0] | io.cmd[1]) &
                (~csr_valid | ~priv_valid) | wen & csr_RO |
                (priv_inst & ~priv_valid) | is_E_call | is_E_break)
        io.expt = expt.reg()
        io.evec = Bits(XLEN)(0)
        io.epc = CSR.mepc.value

        is_inst_ret = (((io.inst != rv32i.NOP) & (~expt | is_E_call | is_E_break) & ~io.stall)).reg()
        is_inst_ret.name="is_inst_ret"

        is_inst_reth = (is_inst_ret & And(*[CSR.instret.value.as_bits()[i] for i in range(len(CSR.instret.value))])).reg()
        is_inst_reth.name="is_inst_reth"

        not_stall = (~io.stall).reg()
        not_stall.name="not_stall"

        is_mbadaddr = (iaddr_invalid | laddr_invalid | saddr_invalid).reg()
        is_mbadaddr.name="is_mbadaddr"

        # Counters
        CSR.time.next = (CSR.time.value.as_uint(32) + 1).as_bits(32)
        CSR.timeh.next = Mux(And(*[CSR.time.value[i] for i in range(len(CSR.time.value))]), CSR.timeh.value, (CSR.timeh.value.as_uint(32) + 1).as_bits(32))
        CSR.cycle.next = (CSR.cycle.value.as_uint(32) + 1).as_bits(32)
        CSR.cycleh.next = Mux(And(*[CSR.cycle.value[i] for i in range(len(CSR.cycle.value))]), CSR.cycleh.value, (CSR.cycleh.value.as_uint(32) + 1).as_bits(32))
        CSR.instret.next = Mux(is_inst_ret, CSR.instret.value, (CSR.instret.value.as_uint(32) + 1).as_bits(32))
        CSR.instreth.next = Mux(is_inst_reth, CSR.instreth.value, (CSR.instreth.value.as_uint(32) + 1).as_bits(32))

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