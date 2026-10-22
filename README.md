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

## Example List  

### common_ip
- [cordic](pycde_example/cordic.py) 
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