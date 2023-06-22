import pycde
from pycde import (Input, InputChannel, OutputChannel, Module, generator, types)



class Producer(Module):
  clk = Input(types.i1)
  const_out = OutputChannel(types.i32)

  @generator
  def construct(ports):
    a = pycde.dim(32, 5)([1, 2, 3, 4, 5], "arr_data")
    chan, ready = types.channel(types.i32).wrap(a[2].reg(ports.clk), valueOrEmpty = 1)
    ports.const_out = chan



class Consumer(Module):
  clk = Input(types.i1)
  int_in = InputChannel(types.i32)

  @generator
  def construct(ports):
    data, valid = ports.int_in.unwrap(readyOrRden=1)


class Top(Module):
  clk = Input(types.i1)

  @generator
  def construct(ports):
    p = Producer(clk=ports.clk)
    Consumer(clk=ports.clk, int_in=p.const_out)


s = pycde.System([Top], name="test_lib", output_directory="build/test_lib")
s.compile()