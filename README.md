# pycde_example

[![Build Status](https://github.com/Dragon-Git/pycde_example/actions/workflows/python-package.yml/badge.svg)](https://github.com/Dragon-Git/pycde_example/actions)

## Getting Started

### Dependencies Installation  
Prerequisites
Operating systems:
- Windows
- Linux 
 
Python: 3.8 ~ 3.13 (64-bit only)

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

## Example List  

### common_ip
- [codic](pycde_example/codic.py) 
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