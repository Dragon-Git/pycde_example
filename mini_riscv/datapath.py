from pycde import (System, Module, Input, Output, generator, types)  # noqa: F401
from pycde.common import Clock, Reset
from pycde.dialects import comb, hw  # noqa: F401
from pycde.types import Bits, SInt, UInt  # noqa: F401
from pycde.constructs import ControlReg, NamedWire, Reg, Wire, Mux  # noqa: F401
from pycde.behavioral import If, Else, EndIf
from pycde.signals import ArraySignal

from regfile import Regfile, RamI32x32, Regfile_io, WriteType
from alu import ALU
from bru import BRU
from immgen import Immgen
width = 32

class Datapath(Module):
    clk = Clock()
    rst = Reset()
    A_sel = Input(Bits(4))
    B_sel = Input(Bits(4))
    stall = Input(Bits(1))
    pc = Input(Bits(width))
    inst = Input(Bits(width))
    imm_sel = Input(Bits(3))
    alu_op = Input(Bits(4))
    out = Output(SInt(width))
    sum = Output(SInt(width))
  
    @generator
    def build(io):

        # Pipelining
        fe_pc = Reg(Bits(width), rst = io.rst)
        fe_inst = Reg(Bits(width), rst = io.rst)
        fe_pc.assign(Mux(io.stall, fe_pc, io.pc))
        fe_inst.assign(Mux(io.stall, fe_inst, io.inst))
        ############################### Execute ############################
        # Decode
        # io.ctrl.inst  := fe_inst

        # regFile read
        rd_addr  = fe_inst[7:12]
        rs1_addr = fe_inst[15:20]
        rs2_addr = fe_inst[20:25]
        (write_data, _) = WriteType.wrap({'data': fe_inst, 'address': rd_addr}, Bits(1)(1))
        reg_file = Regfile(clk=io.clk, rst=io.rst)
        # reg_file.unwrap()
        # reg_file.write(Regfile_io.write("write"))
        # regFile.io.raddr1 := rs1_addr
        # regFile.io.raddr2 := rs2_addr

        # // gen immdeates
        imm = Immgen(insn = fe_inst, sel = io.imm_sel)

        # bypass
        # wb_rd_addr = ew_inst(11, 7)
        # rs1hazard = wb_en && rs1_addr.orR && (rs1_addr === wb_rd_addr)
        # rs2hazard = wb_en && rs2_addr.orR && (rs2_addr === wb_rd_addr)
        # rs1 = Mux(wb_sel === WB_ALU && rs1hazard, ew_alu, regFile.io.rdata1) 
        # rs2 = Mux(wb_sel === WB_ALU && rs2hazard, ew_alu, regFile.io.rdata2)
        rs1 = SInt(width)(0)
        rs2 = SInt(width)(0)
        # ALU operations
        alu_io_A = Mux(io.A_sel == Bits(4)(2), SInt(width)(0), rs1)
        alu_io_B = Mux(io.B_sel == Bits(4)(3), SInt(width)(0), rs2)
        alu_io_alu_op = io.alu_op

        temp = ALU(A=alu_io_A, B=alu_io_B, alu_op=alu_io_alu_op)
        io.out = temp.out
        io.sum = temp.sum

        # Branch condition calc
        temp = BRU(rs1=rs1, rs2=rs2, br_type=alu_io_alu_op[:3])
        io.br_type = temp.taken


if __name__ == '__main__':
    mod = System([Datapath],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()