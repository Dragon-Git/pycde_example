
from pycde import (AppID, Clock, Reset, Input, Output, Module, System, generator, esi,  ir)
from pycde.types import Bits, UInt
from pycde.signals import BitsSignal
from pycde.dialects import sv
from pycde import support

def unknown_location():
    return ir.Location.unknown()
support.get_user_loc.__code__ = unknown_location.__code__

def sram(width: int = 32, depth: int = 1024):
    Ram = esi.DeclareRandomAccessMemory(Bits(width), depth, f"RamI{width}x{depth}")
    WriteReqType = Ram.write.type.req
    ReadAddrType = Ram.read.type.address

    class Sram(Module):
        hclk = Clock()
        hresetn = Reset()
        hsel = Input(Bits(1))
        hready_in = Input(Bits(1))
        htrans = Input(Bits(2))
        hsize = Input(Bits(3))
        hwrite = Input(Bits(1))
        haddr = Input(UInt(32))
        hwdata = Input(Bits(32))
        hready = Output(Bits(1))
        hresp = Output(Bits(1))
        hrdata = Output(Bits(32))

        @generator
        def construct(io):

            # 控制逻辑
            ahb_access = io.htrans[1] & io.hsel & io.hready_in
            ahb_access.name = "ahb_access"
            ahb_write = ahb_access & io.hwrite
            ahb_write.name = "ahb_write"
            ahb_read = ahb_access & ~io.hwrite
            
            ram_write = ahb_write.reg(io.hclk, io.hresetn, name="ram_write")
            ram_read = ahb_read.reg(io.hclk, io.hresetn, name="ram_read")
            buf_addr = io.haddr.reg(io.hclk, io.hresetn, name="addr")
            buf_addr_cut = buf_addr.as_bits()[2:12].as_uint()

            # 字节选择逻辑 ----- 0: Byte, 1: Half-word, 2: Word
            tx_byte_num = [io.hsize == Bits(3)(i) for i in range(3)]
            byte_pos = [tx_byte_num[0] & (io.haddr.as_bits()[0:2] == Bits(2)(i)) for i in range(4)]
            half_pos = [tx_byte_num[1] & ~io.haddr.as_bits()[1], tx_byte_num[1] & io.haddr.as_bits()[1]]
            
            # 地址阶段字节选通信号
            byte_sel = [tx_byte_num[2] | half_pos[i//2] | byte_pos[i] for i in range(4)]
            write_mask = BitsSignal.concat([BitsSignal.concat([byte_sel[i]]*8) & BitsSignal.concat([ahb_write]*8) for i in range(4)])

            # 读数据逻辑
            read_bundle = Ram.read(AppID("rd"))
            bundled_channels = read_bundle.unpack(address=ReadAddrType.wrap(buf_addr_cut, ram_read)[0])
            hrdata = bundled_channels["data"].unwrap(ram_read)[0]
            
            # 写数据逻辑
            write_mask_reg = write_mask.reg(io.hclk, io.hresetn, name="write_mask_reg")
            write_data = write_mask_reg & io.hwdata | ~write_mask_reg & hrdata
            write_bundle = Ram.write(AppID("wr"))
            write_channal = Ram.write_struct({"address": buf_addr_cut, "data": write_data})
            write_bundle.unpack(req=WriteReqType.wrap(write_channal, ram_write)[0])
            # 连接输出信号
            io.hready = Bits(1)(1)
            io.hresp = Bits(1)(0)
            io.hrdata = hrdata

            Ram.implement_as("sv_mem", io.hclk, io.hresetn)
            sv.VerbatimOp(ir.StringAttr.get(f"initial begin\nRamI{width}x{depth}=\'{{default:0}}; \nend\n" ), [])

    return Sram

if __name__ == '__main__':
    mod = System([sram()],name="ip_amba_lib", output_directory="build/ip_amba_lib")
    mod.compile()
