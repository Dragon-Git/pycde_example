from pycde import (Clock, Reset, Input, Output, Module, System, generator)
from pycde.types import Bits, UInt, types  # noqa: F401
from pycde.constructs import Reg, Mux
from pycde.signals import BitsSignal
from pycde.module import ModuleBuilder

class AHBModuleBuilder(ModuleBuilder):
    def scan_cls(self):
        self.cls_dct.update({
            "HSEL": Input(Bits(1)),
            "HREADY": Input(Bits(1)),
            "HTRANS": Input(Bits(2)),
            "HSIZE": Input(Bits(3)),
            "HWRITE": Input(Bits(1)),
            "HADDR": Input(UInt(32)),
            "HWDATA": Input(Bits(32)),
            "HREADYOUT": Output(Bits(1)),
            "HRESP": Output(Bits(1)),
            "HRDATA": Output(Bits(32)),
        })
        return super().scan_cls()
    
class SRAMModuleBuilder(ModuleBuilder):
    def scan_cls(self):
        self.cls_dct.update({
            "SRAMRDATA": Input(Bits(32)),
            "SRAMADDR": Output(UInt(14)),
            "SRAMWEN": Output(Bits(4)),
            "SRAMWDATA": Output(Bits(32)),
            "SRAMCS": Output(Bits(1)),
        })
        return super().scan_cls()

class AHBSRAMModuleBuilder(AHBModuleBuilder, SRAMModuleBuilder):
    pass

class AHBRam(Module):
    BuilderType = AHBSRAMModuleBuilder
    # 时钟和复位
    HCLK = Clock()
    HRESETn = Reset()
    @generator
    def construct(io):
        # # 内部状态变量
        buf_addr = Reg(UInt(14), io.HCLK, io.HRESETn, name="addr")  # 地址缓冲 [AW-3:0]
        buf_we = Reg(Bits(4), io.HCLK, io.HRESETn, name="we")  # 写使能缓冲
        buf_hit = Reg(Bits(1), io.HCLK, io.HRESETn, name="hit")  # 地址匹配标志
        buf_data = [Reg(Bits(8), io.HCLK, name=f"data_{i}") for i in range(4)]
        buf_pend = Reg(Bits(1), io.HCLK, io.HRESETn, name="pend")  # 缓冲数据有效标志

        # 控制逻辑
        ahb_access = io.HTRANS[1] & io.HSEL & io.HREADY
        ahb_write = ahb_access & io.HWRITE
        ahb_write.name = "ahb_write"
        ahb_read = ahb_access & ~io.HWRITE
        ahb_read.name = "ahb_read"
        
        # 缓冲区pending状态
        reg_data_en = ahb_write.reg(io.HCLK, io.HRESETn)
        buf_pend_nxt = (buf_pend | reg_data_en) & ahb_read
        
        # RAM写使能
        ram_write = (buf_pend | reg_data_en) & ~ahb_read
        ram_write.name = "ram_write"
        
        # 连接输出信号
        io.SRAMWEN = BitsSignal.concat(4*[ram_write]) & buf_we
        io.SRAMADDR = Mux(ahb_read, buf_addr, io.HADDR.as_bits()[2:16].as_uint())
        io.SRAMCS = ahb_read | ram_write
        io.HREADYOUT = Bits(1)(1)
        io.HRESP = Bits(1)(0)
        io.SRAMWDATA = Mux(buf_pend, BitsSignal.concat(buf_data[::-1]), io.HWDATA)

        # 字节选择逻辑 ----- 0: Byte, 1: Half-word, 2: Word
        tx_byte_num = [io.HSIZE == Bits(3)(i) for i in range(3)]
        byte_pos = [tx_byte_num[0] & (io.HADDR.as_bits()[0:2] == Bits(2)(i)) for i in range(4)]
        half_pos = [tx_byte_num[1] & ~io.HADDR.as_bits()[1], tx_byte_num[1] & io.HADDR.as_bits()[1]]
        
        # 地址阶段字节选通信号
        byte_sel = [tx_byte_num[2] | half_pos[i//2] | byte_pos[i] for i in range(4)]
        buf_we_nxt = BitsSignal.concat([byte_sel[i] & ahb_write for i in range(4)])
        
        # 更新缓冲区写使能
        buf_we.assign(Mux(ahb_write, buf_we_nxt, buf_we))
        buf_addr.assign(Mux(ahb_write, io.HADDR.as_bits()[2:16].as_uint(), buf_addr))
        buf_hit.assign(Mux(ahb_read, (io.HADDR.as_bits()[2:16].as_uint() == buf_addr), buf_hit))
        buf_pend.assign(buf_pend_nxt)
        
        # 数据缓冲区更新
        for i in range(4):
            buf_data[i].assign(Mux(buf_we[i] & reg_data_en, buf_data[i], io.HWDATA[8*i:8*(i+1)]))
        
        # 读数据合并逻辑
        buf_hit_reg = BitsSignal.concat(4*[buf_hit])
        merge1 = buf_hit_reg & buf_we
        
        # 合并读数据
        hrdata_values = [Mux(merge1[i], io.SRAMRDATA[8*i:8*(i+1)], buf_data[i]) for i in range(4)]
        io.HRDATA = BitsSignal.concat(hrdata_values[::-1])

if __name__ == '__main__':
    mod = System([AHBRam], name="ahb_to_ram", output_directory="build/ahb_to_ram")
    mod.compile()