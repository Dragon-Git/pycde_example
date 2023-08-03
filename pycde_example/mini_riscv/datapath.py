from pycde import (System, Module, Clock, Reset, InputChannel, OutputChannel, Input, Output, generator, types)
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import ControlReg, NamedWire, Reg, Wire, Mux  # noqa: F401

from .alu import ALU
from .bru import BRU
from .control import ctrl_sig
from .csr_gen import CSRGen
from .immgen import Immgen
from .instructions import RV32I
from .regfile import Regfile, WriteType
from .const import XLEN, PC_const
from .cache import ReqType

class Datapath(Module):
    clk = Clock()
    rst = Reset()
    ctrl = Input(ctrl_sig)
    insn= Output(Bits(XLEN))
    dreq = OutputChannel(ReqType)
    dresp = InputChannel(Bits(XLEN))
    ireq = OutputChannel(ReqType)
    iresp = InputChannel(Bits(XLEN))
  
    @generator
    def build(io):

        fe_pc = Reg(Bits(XLEN))
        fe_inst = Reg(Bits(XLEN), rst=io.rst)
        ew_pc = Reg(Bits(XLEN))
        ew_inst = Reg(Bits(XLEN), rst=io.rst)
        ew_alu = Reg(Bits(XLEN), rst=io.rst)
        csr_in = Reg(Bits(XLEN), rst=io.rst)
        ew_pc.assign(Bits(XLEN)(0)) # FIXME
        ew_alu.assign(Bits(XLEN)(0)) # FIXME
        ctrl_rg = io.ctrl.reg()
        # Fetch
        alu_sum = Wire(Bits(XLEN))
        bru_taken = Wire(Bits(1))
        csr_expt = Wire(Bits(1))
        dresp_data, dresp_valid = io.dresp.unwrap(readyOrRden=1)
        iresp_data, iresp_valid = io.iresp.unwrap(readyOrRden=1)
        started = Bits(1)(1)
        stall = ~iresp_valid | ~dresp_valid
        pc   = Reg(Bits(XLEN), rst=io.rst, rst_value=(PC_const().PC_START.as_uint() - 4).as_bits(XLEN))
        # npc  = Mux(stall, pc, Mux(csr.expt, csr.evec,
        #      Mux(io.ctrl.pc_sel == PC_EPC,  csr.epc,
        #      Mux(io.ctrl.pc_sel == PC_ALU | bru.taken, alu_sum,
        #      Mux(io.ctrl.pc_sel == PC_0, pc, pc + 4)))))
        npc = 0
        pc.assign(npc)
        insn = Mux(started | io.ctrl.inst_kill | bru_taken | csr_expt, iresp_data, RV32I().NOP)
        io.ireq, ready = types.channel(ReqType).wrap(ReqType({"addr": npc, "data": 0, "mask": 0}), ~stall)

        # Pipelining 1
        pc = Bits(32)(0xbad)
        fe_pc.assign(Mux(stall, fe_pc, pc))
        fe_inst.assign(Mux(stall, fe_inst, insn))
        ############################### Execute ############################
        # Decode
        io.insn  = fe_inst

        # regFile read
        (write_data, _) = WriteType.wrap({'data': Bits(32)(0xABCDEF), 'address': fe_inst[7:12]}, valueOrEmpty = 1)
        (rs1_addr, _) = types.channel(Bits(5)).wrap(fe_inst[15:20], valueOrEmpty=1)
        (rs2_addr, _) = types.channel(Bits(5)).wrap(fe_inst[20:25], valueOrEmpty=1)
        reg_file = Regfile(clk=io.clk, rst=io.rst, rs1_read_addr=rs1_addr, rs2_read_addr=rs2_addr, rd_write=write_data)
        rdata1, _ = reg_file.rs1_read_data.unwrap(readyOrRden=1)
        rdata2, _ = reg_file.rs2_read_data.unwrap(readyOrRden=1)

        # // gen immdeates
        immgen = Immgen(insn = fe_inst, sel = io.ctrl.imm_sel)

        # bypass
        wb_en = Bits(1)(0)
        wb_sel = Bits(1)(0)
        WB_ALU = Bits(1)(0)
        ew_alu = Bits(32)(0)
        ew_inst.assign(fe_inst)
        wb_rd_addr = ew_inst[7:12]
        rs1hazard = wb_en & fe_inst[15:20].or_reduce() & (fe_inst[15:20] == wb_rd_addr)
        rs2hazard = wb_en & fe_inst[20:25].or_reduce() & (fe_inst[20:25] == wb_rd_addr)
        rs1 = Mux(wb_sel == WB_ALU & rs1hazard, ew_alu, rdata1) 
        rs2 = Mux(wb_sel == WB_ALU & rs2hazard, ew_alu, rdata2)
        # ALU operations
        alu_io_A = Mux(io.ctrl.A_sel == Bits(1)(1), fe_pc.as_sint(), rs1.as_sint())
        alu_io_B = Mux(io.ctrl.B_sel == Bits(1)(1), immgen.out, rs2.as_sint())

        alu = ALU(A=alu_io_A, B=alu_io_B, alu_op=io.ctrl.alu_op)
        # io.out = temp.out
        alu_sum.assign(alu.sum.as_bits())

        # Branch condition calc
        bru = BRU(rs1=rs1.as_sint(), rs2=rs2.as_sint(), br_type=io.ctrl.br_type)
        bru_taken.assign(bru.taken)

        # Pipelining 2
        csr_in.assign(Mux(io.ctrl.imm_sel == Bits(3)(6), rs1, immgen.out.as_bits()))
        # CSR access
        csr = CSRGen(
            clk      = io.clk,
            rst      = io.rst,
            stall    = stall,
            In       = csr_in,
            cmd      = ctrl_rg.csr_cmd,
            insn     = ew_inst,
            pc       = ew_pc,
            addr     = ew_alu,
            illegal  = ctrl_rg.illegal,
            pc_check = io.ctrl.pc_sel == Bits(2)(1),
            ld_type  = ctrl_rg.ld_type,
            st_type  = ctrl_rg.st_type,
        )
        csr_expt.assign(csr.expt)
        io.dreq, _ = types.channel(ReqType).wrap(ReqType({"addr": 123, "data": 456, "mask": 15}), 1)


if __name__ == '__main__':
    mod = System([Datapath],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()