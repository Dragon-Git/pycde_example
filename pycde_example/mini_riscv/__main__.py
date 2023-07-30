from pycde import System

from .core import Core

mod = System([Core],name="ip_riscv_lib", output_directory="build/ip_riscv_lib")
mod.compile()