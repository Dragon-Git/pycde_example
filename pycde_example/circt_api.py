# silicon.py
import pycde.circt as circt
from pycde import System
from pycde.circt.ir import Context, InsertionPoint, IntegerType, Location, Module
from pycde.circt.dialects import hw

i32 = IntegerType.get_signless(32)
def _default(module):
  # x = comb.AndOp.create(*[getattr(module, input) for input in module.inputs()])
  return {output: hw.ConstantOp.create(i32, 0) for output in module.outputs()}
    
with Context() as ctx, Location.unknown():
  circt.register_dialects(ctx)
  m = Module.create()
  with InsertionPoint(m.body):
    hw.HWModuleOp(name="circt_api",
                  # input_ports=[("rvfi_valid", i32), ("rvfi_insn", i32)],
                  output_ports=[(chr(i), i32) for i in range(92)],
                  body_builder=_default)
    
  mod: object = System([],name="circt_api_lib", output_directory="build/circt_api_lib")
  mod.import_mlir(m)
  mod.passed = True
  mod.compile()