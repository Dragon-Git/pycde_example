from pycde import System

from .tile import Tile

mod = System([Tile],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
mod.compile()