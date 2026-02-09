#part1:import pycde相关module
import pycde
from pycde.constructs import Reg,Mux
from pycde import Module
from pycde.types import UInt,SInt
from pycde import Clock,Reset,Output
from pycde import generator
from pycde import System

#part2:模块参数化
@pycde.modparams
def my_counter(boundary:int,inc=1):
    width = boundary.bit_length()    
#part3:接口定义    
    class my_counter(Module):
        clk = Clock()
        rst = Reset()
        cnt = Output(UInt(width))
        #RTL主体结构
        @generator  
        def counter(ports):            
            #--part4.1 定义计数寄存器
            count = Reg(UInt(width), rst = ports.rst) #如何定义一个Reg ? 如何增加异步复位？
            count.name = "cnt"
            #--part4.2 计数器核心逻辑
            count.assign(Mux(
                (count == UInt(width)(boundary)).as_bits(1),
                (count+inc).as_uint(width) ,
                UInt(width)(0)
                )
             ) #Mux如何使用？ 在哪里有说明？ 看源代码Go to Definition
            ports.cnt = count
    #part4.3 注意return计数器
    return my_counter

#part5 系统编译与输出
if __name__ == '__main__':
    #指定输出文件夹的名字
    mod=System([my_counter(100,1)], output_directory="build/my_counter_lib/")
    mod.compile()