# pycde_example

## Getting Started

### Dependencies Installation  
Prerequisites
Operating systems:
- Windows
- Linux 
 
Python: 3.8 ~ 3.11 (64-bit only)

- Use Python's package installer pip to install pycde example dependencies:
```bash
pip install -r requirements.txt
```

- Build from source
If you use other OS or other version of python, you can build pycde for your own environments.See [pycde build]([docs/PyCDE/compiling.md](https://github.com/llvm/circt/blob/main/docs/PyCDE/compiling.md)).

### Usage
Create a directory named "build", and execute the corresponding .py file with Python to generate the desired SystemVerilog file and its dependent SystemVerilog files, for example:
```bash
mkdir build
python lfsr.py
```

## Example List  

### common_ip
- [codic](codic.py) 
- [counter](counter.py) 
- [fir_filter](fir_filter.py) 
- [hwarith](hwarith.py) 
- [lfsr](lfsr.py)

### riscv-mini 
- [alu](mini_riscv/alu.py)  
- [bru](mini_riscv/bru.py)  
- [cache](mini_riscv/cache.py)
- [immgen](mini_riscv/immgen.py)  
- [regfile](mini_riscv/regfile.py)

## TODO：
- [ ] axi-lite
- [ ] cache
- [ ] Tile
- [ ] add test 