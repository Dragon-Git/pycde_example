from pycde import (Output, Input, Clock, Module, generator, types, dim, System)


class WireNames(Module):
  clk = Clock()
  sel = Input(types.i2)
  data_in = Input(dim(32, 3))

  a = Output(types.i32)
  b = Output(types.i32)

  @generator
  def build(ports) -> None:
    foo = ports.data_in[0]
    foo.name = "foo"
    arr_data = dim(32, 4)([1, 2, 3, 4], "arr_data")
    ports.a = foo.reg(ports.clk).reg(ports.clk)
    ports.b = arr_data[ports.sel]


system = System([WireNames], name="test_lib", output_directory="build/test_lib")
system.compile()