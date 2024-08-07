
from pycde import (Clock, Reset, InputChannel, OutputChannel, Input, Module, System, generator)
from pycde.types import Bits, SInt, UInt, types, StructType  # noqa: F401
from pycde.constructs import Wire  # noqa: F401
from pycde import esi
from pycde import fsm

from .const import XLEN

RamI32x32 = esi.DeclareRandomAccessMemory(types.i32, 32, "RamI32x32")
WriteType = RamI32x32.write.type.req
ReqType = StructType({"addr": Bits(XLEN), "data": Bits(XLEN), "mask": Bits(XLEN//8), "abort": Bits(1)})
class Cache_fsm(fsm.Machine):
    cpu_req_vld = Input(Bits(1))
    cpu_req_data_mask = Input(Bits(1))
    cpu_mask_reduce_or = Input(Bits(1)) 
    nasti_ar = Input(Bits(1))
    nasti_ar = Input(Bits(1))
    nasti_aw = Input(Bits(1))
    nasti_b = Input(Bits(1))
    read_wrap_out = Input(Bits(1))
    write_wrap_out = Input(Bits(1))
    hit = Input(Bits(1))
    is_alloc_reg = Input(Bits(1))
    cpu_abort = Input(Bits(1))
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

class Cache(Module):
    clk = Clock()
    rst = Reset()
    req = InputChannel(ReqType)
    resp = OutputChannel(Bits(XLEN))

    @generator
    def construct(io):
        pack, valid = io.req.unwrap(readyOrRden=1)
        io.resp, ready = types.channel(Bits(32)).wrap(pack.data.reg(), valid)


if __name__ == '__main__':
    mod = System([Cache, Cache_fsm],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
    mod.compile()
