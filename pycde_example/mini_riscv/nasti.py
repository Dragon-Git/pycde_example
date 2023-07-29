from pycde.types import Bits, SInt, UInt, types  # noqa: F401
from pycde import esi, signal

class NastiParameters:
    def __init__(self, data_bits, addr_bits, id_bits):
        self.data_bits = data_bits
        self.addr_bits = addr_bits
        self.id_bits = id_bits
        self.x_data_bits = self.data_bits
        self.w_strobe_bits = self.data_bits // 8
        self.x_addr_bits = self.addr_bits
        self.w_id_bits = self.id_bits
        self.r_id_bits = self.id_bits
        self.x_id_bits = self.id_bits
        self.x_user_bits = 1
        self.a_w_user_bits = self.x_user_bits
        self.w_user_bits = self.x_user_bits
        self.b_user_bits = self.x_user_bits
        self.a_r_user_bits = self.x_user_bits
        self.r_user_bits = self.x_user_bits
        self.x_len_bits = 8
        self.x_size_bits = 3
        self.x_burst_bits = 2
        self.x_cache_bits = 4
        self.x_prot_bits = 3
        self.x_qos_bits = 4
        self.x_region_bits = 4
        self.x_resp_bits = 2
    
def make_NastiMetadataIO(nasti_params):
    class NastiMetadataIO(signal.Struct):
        addr: UInt(nasti_params.x_addr_bits)
        length: UInt(nasti_params.x_len_bits)
        size: UInt(nasti_params.x_size_bits)
        burst: UInt(nasti_params.x_burts_bits)
        lock: Bits(1)
        cache: UInt(nasti_params.x_cache_bits)
        prot: UInt(nasti_params.x_prot_bits)
        qos: UInt(nasti_params.x_qos_bits)
        region: UInt(nasti_params.x_region_bits)
    return NastiMetadataIO

def make_NastiDataIO(nasti_params):
    class NastiDataIO(signal.Struct):
        data: UInt(nasti_params.x_data_bits)
        last: Bits(1)
    return NastiDataIO


def make_NastiWriteAddressChannel(nasti_params):
    class NastiWriteAddressChannel(signal.Struct):
        id = UInt(nasti_params.w_id_bits)
        user = UInt(nasti_params.a_w_user_bits)

        # metadata/address channel common
        addr = UInt(nasti_params.x_addr_bits)
        length = UInt(nasti_params.x_len_bits)
        size = UInt(nasti_params.x_size_bits)
        burst = UInt(nasti_params.x_burst_bits)
        lock = Bits(1)
        cache = UInt(nasti_params.x_cache_bits)
        prot = UInt(nasti_params.x_prot_bits)
        qos = UInt(nasti_params.x_qos_bits)
        region = UInt(nasti_params.x_region_bits)
    return NastiWriteAddressChannel


def make_NastiWriteDataChannel(nasti_params):
    class NastiWriteDataChannel(signal.Struct):
        id = UInt(nasti_params.w_id_bits)
        strb = UInt(nasti_params.w_strobe_bits)
        user = UInt(nasti_params.w_user_bits)
        data = UInt(nasti_params.x_data_bits)
        last = Bits(1)
    return NastiWriteDataChannel


def make_NastiWriteResponseChannel(nasti_params):
    class NastiWriteResponseChannel(signal.Struct):
        resp = UInt(nasti_params.x_resp_bits)
        id = UInt(nasti_params.w_id_bits)
        user = UInt(nasti_params.b_user_bits)
    return NastiWriteResponseChannel


def make_NastiReadAddressChannel(nasti_params):
    class NastiReadAddressChannel(signal.Struct):
        id = UInt(nasti_params.r_id_bits)
        user = UInt(nasti_params.a_r_user_bits)

        # metadata/address channel common
        addr = UInt(nasti_params.x_addr_bits)
        length = UInt(nasti_params.x_len_bits)
        size = UInt(nasti_params.x_size_bits)
        burst = UInt(nasti_params.x_burst_bits)
        lock = Bits(1)
        cache = UInt(nasti_params.x_cache_bits)
        prot = UInt(nasti_params.x_prot_bits)
        qos = UInt(nasti_params.x_qos_bits)
        region = UInt(nasti_params.x_region_bits)
    return NastiReadAddressChannel


def make_NastiReadDataChannel(nasti_params):
    class NastiReadDataChannel(signal.Struct):
        resp = UInt(nasti_params.x_resp_bits)
        id = UInt(nasti_params.r_id_bits)
        user = UInt(nasti_params.r_user_bits)
        data = UInt(nasti_params.x_data_bits)
        last = Bits(1)
    return NastiReadDataChannel

class NastiConstants:
    BURST_FIXED = UInt(2)(0b00)
    BURST_INCR = UInt(2)(0b01)
    BURST_WRAP = UInt(2)(0b10)

    RESP_OKAY = UInt(2)(0b00)
    RESP_EXOKAY = UInt(2)(0b01)
    RESP_SLVERR = UInt(2)(0b10)
    RESP_DECERR = UInt(2)(0b11)

    CACHE_DEVICE_NOBUF = UInt(4)(0b0000)
    CACHE_DEVICE_BUF = UInt(4)(0b0001)
    CACHE_NORMAL_NOCACHE_NOBUF = UInt(4)(0b0010)
    CACHE_NORMAL_NOCACHE_BUF = UInt(4)(0b0011)

    def AXPROT(instruction, nonsecure, privileged):
        assert isinstance(instruction, Bits(1))
        assert isinstance(nonsecure, Bits(1))
        assert isinstance(privileged, Bits(1))
        return Bits([instruction, nonsecure, privileged]) # need concat


def NastiWriteAddressChannel(nasti_params, id, addr, size, length=0,
                             burst=NastiConstants.BURST_INCR):
    aw = make_NastiWriteAddressChannel(nasti_params)()
    aw.id = id
    aw.addr = addr
    aw.length = length
    aw.size = size
    aw.burst = burst
    aw.lock = Bits(1)(0)
    aw.cache = NastiConstants.CACHE_DEVICE_NOBUF
    aw.prot = NastiConstants.AXPROT(Bits(0)(0), Bits(0)(0), Bits(0)(0))
    aw.qos = UInt(4)(0b0000)
    aw.region = UInt(4)(0b0000)
    aw.user = 0
    return aw


def NastiReadAddressChannel(nasti_params, id, addr, size, length=0,
                            burst=NastiConstants.BURST_INCR):
    ar = make_NastiReadAddressChannel(nasti_params)()
    ar.id = id
    ar.addr = addr
    ar.length = length
    ar.size = size
    ar.burst = burst
    ar.lock = Bits(1)(0)
    ar.cache = NastiConstants.CACHE_DEVICE_NOBUF
    ar.prot = NastiConstants.AXPROT(Bits(0)(0), Bits(0)(0), Bits(0)(0))
    ar.qos = UInt(4)(0b0000)
    ar.region = UInt(4)(0b0000)
    ar.user = 0
    return ar


def NastiWriteDataChannel(nasti_params, data, strb=None, last=True, id=0):
    w = make_NastiWriteDataChannel(nasti_params)()
    if strb is None:
        strb = Bits(1)(0)
        #TODO: strb = repeat(1, nasti_params.w_strobe_bits)
    w.strb = strb
    w.data = data
    w.last = last
    w.id = id
    w.user = 0
    return w


def NastiReadDataChannel(nasti_params, id, data, last=True, resp=0):
    r = make_NastiReadDataChannel(nasti_params)()
    r.id = id
    r.data = data
    r.last = last
    r.resp = resp
    r.user = 0
    return r


def NastiWriteResponseChannel(nasti_params, id, resp=0):
    b = make_NastiWriteResponseChannel(nasti_params)()
    b.id = id
    b.resp = resp
    b.user = 0
    return b

def make_NastiIO(nasti_params):
    @esi.ServiceDecl
    class Nasti_io:
        write_addr = esi.FromServer(make_NastiWriteAddressChannel(nasti_params))
        write_data = esi.FromServer(make_NastiWriteDataChannel(nasti_params))
        write_resp = esi.ToServer(make_NastiWriteResponseChannel(nasti_params))
        read_addr = esi.FromServer(make_NastiReadAddressChannel(nasti_params))
        read_data = esi.ToServer(make_NastiReadDataChannel(nasti_params))
    return Nasti_io
