#part1:import pycde相关module
import pycde
from pycde.constructs import Reg,Mux
from pycde.dialects import comb
from pycde import Module
from pycde.types import UInt,SInt,Bits
from pycde import Clock,Reset,Output,Input
from pycde import generator
from pycde import System

POLY=[7,3,6,1]
width=max(POLY)+1

   
class my_lsfr(Module):
    clk = Clock()
    rst = Reset()
    # rst = Input(Bits(1))
    seed = Input(Bits(width))     
    lsfr = Output(Bits(width))
    #RTL主体结构
    @generator  
    def LSFR(ports):            
        #--part4.1 定义计数寄存器
        r1 = Reg(Bits(width),  rst = ports.rst, rst_value = ports.seed) #如何定义一个Reg ? 如何增加异步复位？
        r1.name = "lsfr_t"
        #--part4.2 计数器核心逻辑
        r2 = comb.XorOp(*[r1[ii] for ii in POLY])
        r1.assign ((comb.ConcatOp(r1[0:-1],r2)))
        ports.lsfr = r1
#part4.3 注意return计数器

#part5 系统编译与输出
if __name__ == '__main__':
    #指定输出文件夹的名字
    mod=System([my_lsfr], output_directory="build/my_lsfr_lib/")
    mod.compile()