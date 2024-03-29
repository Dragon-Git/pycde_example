from pycde import System, Module, Input, Output, generator
from pycde.types import Bits, StructType
from pycde.signals import BitsSignal

from .bit_pat import dict_lookup
from .instructions import RV32I
from .csr import CSR_CMD_
from .const import XLEN

ctrl_sig = StructType({
    # Control signals for Fetch
    "pc_sel": Bits(2),
    "inst_kill": Bits(1),
    # Control signals for Execute
    "A_sel": Bits(1),
    "B_sel": Bits(1),
    "imm_sel": Bits(3),
    "alu_op": Bits(4),
    "br_type": Bits(3),
    "st_type": Bits(2),
    # Control signals for Write Back
    "ld_type": Bits(3),
    "wb_sel": Bits(2),
    "wb_en": Bits(1),
    "csr_cmd": Bits(3),
    "illegal": Bits(1)
})

class Control(Module):

    insn = Input(Bits(XLEN))
    ctrl = Output(ctrl_sig)

    @generator
    def build(io):

        (ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR, ALU_SLT, ALU_SLL, ALU_SLTU,
            ALU_SRL, ALU_SRA, ALU_COPY_A, ALU_COPY_B) = map(Bits(4), range(12))  
        ALU_XXX = Bits(4)(15)

        Y, N = map(Bits(1), range(2))  

        # pc_sel
        PC_4, PC_ALU, PC_0, PC_EPC = map(Bits(2), range(4))  

        # A_sel
        A_XXX = Bits(1)(0)
        A_PC, A_RS1 = map(Bits(1), range(2))  
        # B_sel
        B_XXX = Bits(1)(0)
        B_IMM, B_RS2 = map(Bits(1), range(2))  
        # imm_sel
        IMM_X, IMM_I, IMM_S, IMM_U, IMM_J, IMM_B, IMM_Z = map(Bits(3), range(7))  
        # br_type
        BR_XXX, BR_LTU, BR_LT, BR_EQ, BR_GEU, BR_GE, BR_NE = map(Bits(3), range(7))  
        # st_type
        ST_XXX, ST_SW, ST_SH, ST_SB = map(Bits(2), range(4))  
        # ld_type
        LD_XXX, LD_LW, LD_LH, LD_LB, LD_LHU, LD_LBU = map(Bits(3), range(6))  
        # wb_sel
        WB_ALU, WB_MEM, WB_PC4, WB_CSR = map(Bits(2), range(4))


        rv32i = RV32I()
        CSR_CMD = CSR_CMD_()
        default_list = [PC_4, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, Y]
        default = BitsSignal.concat(default_list[::-1])

        inst_map = {
            rv32i.LUI: (PC_4, A_PC, B_IMM, IMM_U, ALU_COPY_B, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.AUIPC: (PC_4, A_PC, B_IMM, IMM_U, ALU_ADD, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.JAL: (PC_ALU, A_PC, B_IMM, IMM_J, ALU_ADD, BR_XXX, Y, ST_XXX, LD_XXX, WB_PC4, Y, CSR_CMD.N, N),
            rv32i.JALR: (PC_ALU, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_XXX, WB_PC4, Y, CSR_CMD.N, N),
            rv32i.BEQ: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_EQ, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.BNE: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_NE, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.BLT: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_LT, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.BGE: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_GE, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.BLTU: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_LTU, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.BGEU: (PC_4, A_PC, B_IMM, IMM_B, ALU_ADD, BR_GEU, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.LB: (PC_0, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_LB, WB_MEM, Y, CSR_CMD.N, N),
            rv32i.LH: (PC_0, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_LH, WB_MEM, Y, CSR_CMD.N, N),
            rv32i.LW: (PC_0, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_LW, WB_MEM, Y, CSR_CMD.N, N),
            rv32i.LBU: (PC_0, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_LBU, WB_MEM, Y, CSR_CMD.N, N),
            rv32i.LHU: (PC_0, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, Y, ST_XXX, LD_LHU, WB_MEM, Y, CSR_CMD.N, N),
            rv32i.SB: (PC_4, A_RS1, B_IMM, IMM_S, ALU_ADD, BR_XXX, N, ST_SB, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.SH: (PC_4, A_RS1, B_IMM, IMM_S, ALU_ADD, BR_XXX, N, ST_SH, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.SW: (PC_4, A_RS1, B_IMM, IMM_S, ALU_ADD, BR_XXX, N, ST_SW, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.ADDI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_ADD, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLTI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_SLT, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLTIU: (PC_4, A_RS1, B_IMM, IMM_I, ALU_SLTU, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.XORI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_XOR, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.ORI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_OR, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.ANDI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_AND, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLLI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_SLL, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SRLI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_SRL, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SRAI: (PC_4, A_RS1, B_IMM, IMM_I, ALU_SRA, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.ADD: (PC_4, A_RS1, B_RS2, IMM_X, ALU_ADD, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SUB: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SUB, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLL: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SLL, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLT: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SLT, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SLTU: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SLTU, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.XOR: (PC_4, A_RS1, B_RS2, IMM_X, ALU_XOR, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SRL: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SRL, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.SRA: (PC_4, A_RS1, B_RS2, IMM_X, ALU_SRA, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.OR: (PC_4, A_RS1, B_RS2, IMM_X, ALU_OR, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.AND: (PC_4, A_RS1, B_RS2, IMM_X, ALU_AND, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, Y, CSR_CMD.N, N),
            rv32i.FENCE: (PC_4, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.FENCEI: (PC_0, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, Y, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
            rv32i.CSRRW: (PC_0, A_RS1, B_XXX, IMM_X, ALU_COPY_A, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.W, N),
            rv32i.CSRRS: (PC_0, A_RS1, B_XXX, IMM_X, ALU_COPY_A, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.S, N),
            rv32i.CSRRC: (PC_0, A_RS1, B_XXX, IMM_X, ALU_COPY_A, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.C, N),
            rv32i.CSRRWI: (PC_0, A_XXX, B_XXX, IMM_Z, ALU_XXX, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.W, N),
            rv32i.CSRRSI: (PC_0, A_XXX, B_XXX, IMM_Z, ALU_XXX, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.S, N),
            rv32i.CSRRCI: (PC_0, A_XXX, B_XXX, IMM_Z, ALU_XXX, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, Y, CSR_CMD.C, N),
            rv32i.ECALL: (PC_4, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, N, ST_XXX, LD_XXX, WB_CSR, N, CSR_CMD.P, N),
            rv32i.EBREAK: (PC_4, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, N, ST_XXX, LD_XXX, WB_CSR, N, CSR_CMD.P, N),
            rv32i.ERET: (PC_EPC, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, Y, ST_XXX, LD_XXX, WB_CSR, N, CSR_CMD.P, N),
            rv32i.WFI: (PC_4, A_XXX, B_XXX, IMM_X, ALU_XXX, BR_XXX, N, ST_XXX, LD_XXX, WB_ALU, N, CSR_CMD.N, N),
        }
        inst_map = {k: BitsSignal.concat(v[::-1]) for k, v in inst_map.items()}

        ctrl_signals = dict_lookup(inst_map, io.insn, default=default)

        io.ctrl = ctrl_sig({
        "pc_sel" : ctrl_signals[0:2],
        "A_sel" : ctrl_signals[2],
        "B_sel" : ctrl_signals[3],
        "imm_sel" : ctrl_signals[4:7],
        "alu_op" : ctrl_signals[7:11],
        "inst_kill" : ctrl_signals[11],
        "br_type" : ctrl_signals[12:15],
        "st_type" : ctrl_signals[15:17],
        "ld_type" : ctrl_signals[17:20],
        "wb_sel" : ctrl_signals[20:22],
        "wb_en" : ctrl_signals[22],
        "csr_cmd" : ctrl_signals[23:26],
        "illegal" : ctrl_signals[26],
        })

if __name__ == '__main__':
    mod = System([Control],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
