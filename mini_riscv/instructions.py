from bit_pat import BitPat
#   Loads
LB     = BitPat("b?????????????????000?????0000011")
LH     = BitPat("b?????????????????001?????0000011")
LW     = BitPat("b?????????????????010?????0000011")
LBU    = BitPat("b?????????????????100?????0000011")
LHU    = BitPat("b?????????????????101?????0000011")
#   Stores
SB     = BitPat("b?????????????????000?????0100011")
SH     = BitPat("b?????????????????001?????0100011")
SW     = BitPat("b?????????????????010?????0100011")
#   Shifts
SLL    = BitPat("b0000000??????????001?????0110011")
SLLI   = BitPat("b0000000??????????001?????0010011")
SRL    = BitPat("b0000000??????????101?????0110011")
SRLI   = BitPat("b0000000??????????101?????0010011")
SRA    = BitPat("b0100000??????????101?????0110011")
SRAI   = BitPat("b0100000??????????101?????0010011")
#   Arithmetic
ADD    = BitPat("b0000000??????????000?????0110011")
ADDI   = BitPat("b?????????????????000?????0010011")
SUB    = BitPat("b0100000??????????000?????0110011")
LUI    = BitPat("b?????????????????????????0110111")
AUIPC  = BitPat("b?????????????????????????0010111")
#   Logical
XOR    = BitPat("b0000000??????????100?????0110011")
XORI   = BitPat("b?????????????????100?????0010011")
OR     = BitPat("b0000000??????????110?????0110011")
ORI    = BitPat("b?????????????????110?????0010011")
AND    = BitPat("b0000000??????????111?????0110011")
ANDI   = BitPat("b?????????????????111?????0010011")
#   Compare
SLT    = BitPat("b0000000??????????010?????0110011")
SLTI   = BitPat("b?????????????????010?????0010011")
SLTU   = BitPat("b0000000??????????011?????0110011")
SLTIU  = BitPat("b?????????????????011?????0010011")
#   Branches
BEQ    = BitPat("b?????????????????000?????1100011")
BNE    = BitPat("b?????????????????001?????1100011")
BLT    = BitPat("b?????????????????100?????1100011")
BGE    = BitPat("b?????????????????101?????1100011")
BLTU   = BitPat("b?????????????????110?????1100011")
BGEU   = BitPat("b?????????????????111?????1100011")
#   Jump & Link
JAL    = BitPat("b?????????????????????????1101111")
JALR   = BitPat("b?????????????????000?????1100111")
#   Synch
FENCE  = BitPat("b0000????????00000000000000001111")
FENCEI = BitPat("b00000000000000000001000000001111")
#   CSR Access
CSRRW  = BitPat("b?????????????????001?????1110011")
CSRRS  = BitPat("b?????????????????010?????1110011")
CSRRC  = BitPat("b?????????????????011?????1110011")
CSRRWI = BitPat("b?????????????????101?????1110011")
CSRRSI = BitPat("b?????????????????110?????1110011")
CSRRCI = BitPat("b?????????????????111?????1110011")
#   Change Level
ECALL  = BitPat("b00000000000000000000000001110011")
EBREAK = BitPat("b00000000000100000000000001110011")
ERET   = BitPat("b00010000000000000000000001110011")
WFI    = BitPat("b00010000001000000000000001110011")

NOP = BitPat("b00000000000000000000000000010011").as_bits()