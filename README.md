# pycde_example

[![Build Status](https://github.com/Dragon-Git/pycde_example/actions/workflows/python-package.yml/badge.svg)](https://github.com/Dragon-Git/pycde_example/actions)

## Getting Started

### Dependencies Installation  
Prerequisites
Operating systems:
- Windows
- Linux 
 
Python: 3.10 ~ 3.14 (64-bit only)

- Use Python's package installer pip to install pycde example dependencies:
```bash
pip install .
```

- Build from source
If you use other OS or other version of python, you can build pycde for your own environments.See [pycde build]([docs/PyCDE/compiling.md](https://github.com/llvm/circt/blob/main/docs/PyCDE/compiling.md)).

### Usage
Create a directory named "build", and execute the corresponding .py file with Python to generate the desired SystemVerilog file and its dependent SystemVerilog files, for example:
```bash
mkdir build
python pycde_example/lfsr.py
```

## Configurable CORDIC

[cordic](pycde_example/cordic.py) implements a CORDIC which can be configured
along four independent axes:

| parameter     | values                                                | meaning                                                        |
|---------------|-------------------------------------------------------|----------------------------------------------------------------|
| `width`       | any width >= 8                                        | width of the two's complement datapath                         |
| `iterations`  | any number >= 1                                       | number of CORDIC iterations (angular resolution and gain)     |
| `mode`        | `rotation`, `vectoring`                               | rotate the vector by `z` / compute magnitude and angle         |
| `arch`        | `comb`, `pipelined`, `loop`, `loop_pipelined`         | the hardware architecture (see below)                          |

| architecture      | description                                              | latency             |
|-------------------|----------------------------------------------------------|---------------------|
| `comb`            | fully combinational, all iterations unrolled             | 0                   |
| `pipelined`       | all iterations unrolled, one register per iteration      | `iterations`        |
| `loop`            | a single iteration is reused `iterations` times          | `iterations + 1`    |
| `loop_pipelined`  | a single, registered iteration is reused                 | `2 * iterations + 1`|

All architectures use the same ready/valid interface.  The angles are fixed
point numbers where `pi` is represented by `1 << (width - 2)`.

The module is created with:
```python
from pycde_example.cordic import Cordic

cordic = Cordic(width=32, iterations=16, mode="rotation", arch="pipelined")
```

Generate the SystemVerilog of every configuration listed in
[cordic_configs.py](pycde_example/cordic_configs.py) with:
```bash
mkdir build
python -m pycde_example.cordic
```

The tests compare the generated RTL against the bit exact software model in
[cordic_model.py](pycde_example/cordic_model.py), they need the generated RTL
and verilator:
```bash
mkdir build
python -m pycde_example.cordic
pytest pycde_example -n auto
```

## Configurable FFT

[fft](pycde_example/fft.py) implements a radix-2 FFT.  The transform is
split into three independent submodules which the top level instantiates
according to the configuration:

| module | description |
|--------|-------------|
| [fft_butterfly](pycde_example/fft_butterfly.py) | the butterfly: the complex multiplier and the adders |
| [fft_twiddle](pycde_example/fft_twiddle.py) | the twiddle factor generator: a read only memory or a CORDIC rotator |
| [fft_memory](pycde_example/fft_memory.py) | the in place frame memory with two write and three read ports |
| [fft_pipelined](pycde_example/fft_pipelined.py) | the unrolled pipeline: every radix-2 stage has its own butterflies |
| [fft_sdf](pycde_example/fft_sdf.py) | the single path delay feedback: the stages are folded into a chain which is fed back into itself |
| [fft_sdc](pycde_example/fft_sdc.py) | the single path delay commutator: the stages are folded into a feed forward chain which is rearranged by commutators |

| parameter | values | meaning |
|-----------|--------|---------|
| `width` | any width >= 8 | the width of the two's complement datapath, a real number `v` is represented by `round(v * 2**(width - 1))` |
| `points` | a power of two | the number of points of the transform |
| `radices` | `"2"` | the radices of the transform |
| `eval_mode` | `"memory_based"`, `"pipelined"` | `"memory_based"`: the transform is computed iteratively, the intermediate results stay in the frame memory (`log2(points)` passes of `points / 2` butterflies).  `"pipelined"`: the transform is unrolled, every radix-2 stage has its own butterflies |
| `pipeline_style` | `"unrolled"`, `"sdf"`, `"sdc"`, `"mdf"` | the sub topology of the pipelined architecture: `"unrolled"` gives every stage its own butterflies and unrolls the transform, the single path delay feedback (`"sdf"`) and the single path delay commutator (`"sdc"`) fold it into a chain of stages, and the multi path delay feedback (`"mdf"`) splits the frame and transforms the halves in two chains side by side |
| `twiddle_mode` | `"rom"`, `"cordic"`, `"hybrid"`, `"no_mem"` | how the twiddle factors are produced (the memory based architecture only, the pipelined ones use constant factors): a table, a CORDIC, a coarse CORDIC with a correction table, or - not implemented - no memory at all |
| `data_format` | `"fixed"`, `"block_float"` | the number format of the datapath |
| `scaling` | `"stage"`, `"none"` | the scaling of the stages: `"stage"` halves the operands of every butterfly, so that the magnitude of the datapath does not grow from stage to stage |
| `stages` | any number >= 0 | the number of pipeline stages: the number of registers between two radix-2 stages of the pipelined architecture |
| `inverse` | `False`, `True` | the inverse transform (the twiddle factors, the input and the output are conjugated), the memory based architecture only |
| `ordering` | `"dit"`, `"dif"` | decimation in time (the input is read bit reversed) or decimation in frequency (the output is written bit reversed) |
| `parallel` | `1` | the number of butterflies which are computed in parallel |

The module is created with:
```python
from pycde_example.fft import Fft

fft = Fft(width=16, points=64, radices="2", eval_mode="memory_based",
          twiddle_mode="rom", ordering="dit")
```

The interface is frame based: the transform accepts `points` samples and
produces `points` samples, the samples of a frame are counted.

Generate the SystemVerilog of every configuration listed in
[fft_configs.py](pycde_example/fft_configs.py) with:
```bash
mkdir build
python -m pycde_example.fft
```

The tests compare the generated RTL against the bit exact software model in
[fft_model.py](pycde_example/fft_model.py), which is verified against a
floating point discrete Fourier transform.  The twiddle factor generator has
a unit test of its own ([test_fft_twiddle.py](pycde_example/test_fft_twiddle.py)),
the generator is instantiated as a top level module for it.

```bash
mkdir build
python -m pycde_example.fft
pytest pycde_example -n auto
```

The pipelined architecture unrolls the transform: every radix-2 stage has its
own butterflies and the stages are separated by `stages` registers.  It needs
`log2(points)` stages with their butterflies and trades the area for the
throughput, it is only practical for a small number of points.

The unrolled architecture (`pipeline_style="unrolled"`) gives every radix-2
stage its own butterflies and separates the stages with `stages` registers; the
whole transform is unrolled, which costs the area of `log2(points)` butterflies
and works well for a small number of points.

The multi path delay feedback architecture (`pipeline_style="mdf"`) uses the
first stage of the decimation in frequency to split the frame: the sum of the
halves goes down one path and the rotated difference down the other, and each
half is then transformed by a delay feedback chain of its own.  The two halves
meet in the first stage and nowhere else, so the chains are independent and work
at the same time - several paths, each of them fed back.  A chain hands its half
of the spectrum out in the natural order and the two halves interleave into the
even and the odd bins.

The single path delay feedback architecture (`pipeline_style="sdf"`) folds the
transform into a chain of `log2(points)` stages: every stage owns a delay line
(a shift register of `points / 2`, `points / 4`, ..., 1 entries) and a
butterfly.  The difference of the butterfly is written back into the delay
line of the stage, the sum is forwarded to the next stage, so the data of a
frame is transformed while it flows through the chain.  The architecture needs
`points - 1` registers and one butterfly per stage, the frame based interface
is built on top of it: the samples are collected in a register array and the
spectrum is read from it in the natural order.  The bit exact model of the
architecture is in [fft_sdf_model.py](pycde_example/fft_sdf_model.py), it is
verified against the reference model of the transform.

The single path delay commutator architecture (`pipeline_style="sdc"`) is the
other way of folding the transform into a chain.  It has no feedback loop: a
commutator - a multiplexer with a delay line - rearranges the stream so that
one word per cycle leaves every stage.  It needs `2 * points - 2` registers,
twice as many as the delay feedback chain, and its control is a commutator
schedule instead of the write enables of a feedback register.  It is a
streaming pipeline as well, and it is a decimation in frequency pipeline: it
reads the samples in the natural order, so `ordering` has to be `"dif"`.  The
bit exact model of the architecture is in
[fft_sdc_model.py](pycde_example/fft_sdc_model.py).

The three twiddle generators trade accuracy against size.  A table holds
`points / 2` factors and is exact; a CORDIC holds nothing but is a handful of
units of the last bit off, and more so as the transform grows; the `hybrid` mode
turns the vector with a coarse CORDIC and corrects the angle it leaves over with
a table of a fixed 128 entries, so its size does not depend on the number of
points.  Measured against the table for a 16 bit datapath:

| points | table | CORDIC | hybrid |
|--------|-------|--------|--------|
| 16     | 8 entries, exact | 8 units off | 128 entries, 1 unit off |
| 256    | 128 entries, exact | 16 units off | 128 entries, 3 units off |
| 1024   | 512 entries, exact | 21 units off | 128 entries, 4 units off |

The hybrid pays off from about 256 points on, where its table is the smallest of
the three and it stays much closer than the plain CORDIC.  The CORDIC of this
example stops working above a 26 bit datapath, the hybrid inherits that.

Not implemented yet: the multi path delay feedback sub topology of the
pipelined architecture, the radix 4 (and larger) butterflies, the mixed radix
and split radix transforms, the block floating point format and the twiddle
factors without a memory (`twiddle_mode="no_mem"`).  The parameters are already
part of the interface, they raise a `NotImplementedError` for the
configurations which are not supported yet.

The sub topologies of the pipelined architecture follow the classical
framework of the pipelined FFT processors (the delay feedback and the delay
commutator families).  A description of the delay commutator stages is in
"Analysis and implementation of FFT algorithms" (the internship report of the
Department of Electronics Engineering, SOE, CUSAT), it is available at
<https://github.com/roopeshor/Typesetting> under `Reports/Internship-3`.

## Example List  

### common_ip
- [cordic](pycde_example/cordic.py) 
- [fft](pycde_example/fft.py)
- [counter](pycde_example/counter.py) 
- [fir_filter](pycde_example/fir_filter.py) 
- [hwarith](pycde_example/hwarith.py) 
- [lfsr](pycde_example/lfsr.py)

### riscv-mini 
- [alu](pycde_example/mini_riscv/alu.py)  
- [bru](pycde_example/mini_riscv/bru.py)  
- [cache](pycde_example/mini_riscv/cache.py)
- [immgen](pycde_example/mini_riscv/immgen.py)  
- [regfile](pycde_example/mini_riscv/regfile.py)

## TODO：
- [ ] axi-lite
- [ ] cache
- [ ] Tile
- [ ] add test 