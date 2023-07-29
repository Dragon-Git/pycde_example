
from pycde import (Clock, Input, Module, System, generator)
from pycde.types import Bits, SInt, UInt, types  # noqa: F401
from pycde.constructs import Wire
from pycde import esi
from pycde import fsm

XLEN = 32

RamI32x32 = esi.DeclareRandomAccessMemory(types.i32, 32, "RamI32x32")
WriteType = RamI32x32.write.to_server_type

class Cache_fsm(fsm.Machine):
    cpu_req_vld = Input(types.i1)
    cpu_req_data_mask = Input(types.i1)
    cpu_mask_reduce_or = Input(types.i1) 
    nasti_ar = Input(types.i1)
    nasti_ar = Input(types.i1)
    nasti_aw = Input(types.i1)
    nasti_b = Input(types.i1)
    read_wrap_out = Input(types.i1)
    write_wrap_out = Input(types.i1)
    hit = Input(types.i1)
    is_alloc_reg = Input(types.i1)
    cpu_abort = Input(types.i1)
    # States
    IDEL = fsm.State(initial=True)
    (READ_CACHE, WRITE_CACHE, WRITE_BACK, WRITE_ACK, REFILL_RDY, REFILL) = fsm.States(6)  
    # Transitions
    IDEL.set_transitions(
        (WRITE_CACHE, lambda io: io.cpu_req_vld & io.cpu_req_data_mask),
        (READ_CACHE, lambda io: io.cpu_req_vld))
    READ_CACHE.set_transitions(
        (WRITE_CACHE, lambda io: io.hit & io.cpu_req_vld & io.cpu_req_data_mask),
        (IDEL, lambda io: io.hit & ~io.cpu_req_vld),
        (WRITE_BACK, lambda io: ~io.hit & io.nasti_aw),
        (REFILL, lambda io: ~io.hit & io.nasti_ar))
    WRITE_CACHE.set_transitions(
        (IDEL, lambda io: io.hit | io.is_alloc_reg | io.cpu_abort),
        (WRITE_BACK, lambda io: ~io.hit & ~io.is_alloc_reg & ~io.cpu_abort & io.nasti_aw),
        (REFILL, lambda io: ~io.hit & ~io.is_alloc_reg & ~io.cpu_abort & io.nasti_ar))
    WRITE_BACK.set_transitions((WRITE_ACK, lambda io: io.write_wrap_out))
    WRITE_ACK.set_transitions((REFILL_RDY, lambda io: io.nasti_b))
    REFILL_RDY.set_transitions((REFILL, lambda io: io.nasti_ar))
    REFILL.set_transitions(
        (WRITE_CACHE, lambda io: io.read_wrap_out & io.cpu_mask_reduce_or),
        (IDEL, lambda io: io.read_wrap_out)
        )

@esi.ServiceDecl
class Cache_io:
    write = esi.FromServer(WriteType)
    read = esi.ToFromServer(to_server_type=types.i32, to_client_type=types.i5)

class Cache(Module):
    clk = Clock()
    rst = Input(types.i1)

    @generator
    def construct(io):
        RamI32x32.write(Cache_io.write("write"))
        read_address = Wire(RamI32x32.read.to_server_type)
        read_data = RamI32x32.read(read_address)
        read_address.assign(Cache_io.read(read_data, "read"))

        RamI32x32.instantiate_builtin("sv_mem", [], inputs=[io.clk, io.rst])

if __name__ == '__main__':
    mod = System([Cache, Cache_fsm],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
