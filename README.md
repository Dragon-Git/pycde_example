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

| parameter | values | meaning |
|-----------|--------|---------|
| `width` | any width >= 8 | the width of the two's complement datapath, a real number `v` is represented by `round(v * 2**(width - 1))` |
| `points` | a power of two | the number of points of the transform |
| `radices` | `"2"` | the radices of the transform |
| `eval_mode` | `"memory_based"`, `"pipelined"` | `"memory_based"`: the transform is computed iteratively, the intermediate results stay in the frame memory (`log2(points)` passes of `points / 2` butterflies).  `"pipelined"`: the transform is unrolled, every radix-2 stage has its own butterflies |
| `pipeline_style` | `"sdf"`, `"mdc"`, `"sdc"`, `"mdf"` | the sub topology of the pipelined architecture, only the multi path (`"mdc"`) one is implemented |
| `twiddle_mode` | `"rom"`, `"cordic"`, `"hybrid"`, `"no_mem"` | how the twiddle factors are produced |
| `data_format` | `"fixed"`, `"block_float"` | the number format of the datapath |
| `scaling` | `"stage"`, `"none"` | the scaling of the stages: `"stage"` halves the operands of every butterfly, so that the magnitude of the datapath does not grow from stage to stage |
| `stages` | any number >= 0 | the number of pipeline stages: the number of registers between two radix-2 stages of the pipelined architecture |
| `inverse` | `False`, `True` | the inverse transform (the twiddle factors, the input and the output are conjugated) |
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

Not implemented yet: the single path delay feedback, the single path delay
commutator and the multi path delay feedback sub topologies of the pipelined
architecture (only the multi path one is implemented), the radix 4 (and larger)
butterflies, the mixed radix and split radix transforms, the block floating
point format and the twiddle factors without a memory
(`twiddle_mode="no_mem"`).  The parameters are already part of the interface,
they raise a `NotImplementedError` for the configurations which are not
supported yet.

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