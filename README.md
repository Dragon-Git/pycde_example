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
| `radices` | `"2"`, `"4"`, `"8"`, `"4,2"`, ... | the radices of the transform as a comma separated list whose product is `points`; a single value is repeated to fill the transform, a list is taken literally.  A radix larger than 2 is supported by every pipelined topology |
| `eval_mode` | `"memory_based"`, `"pipelined"` | `"memory_based"`: the transform is computed iteratively, the intermediate results stay in the frame memory (`log2(points)` passes of `points / 2` butterflies).  `"pipelined"`: the transform is unrolled, every radix-2 stage has its own butterflies |
| `pipeline_style` | `"unrolled"`, `"sdf"`, `"sdc"`, `"mdf"`, `"mdc"` | the sub topology of the pipelined architecture: `"unrolled"` gives every stage its own butterflies and unrolls the transform, the single path delay feedback (`"sdf"`) and the single path delay commutator (`"sdc"`) fold it into a chain of stages, and the multi path (`"mdf"`, `"mdc"`) ones split the frame and transform the halves in two chains side by side, on delay feedback or on delay commutator chains |
| `twiddle_mode` | `"rom"`, `"cordic"`, `"hybrid"`, `"no_mem_cascade"`, `"no_mem_logic"` | how the twiddle factors are produced (the memory based architecture only, the pipelined ones use constant factors): a table, a CORDIC, a coarse CORDIC with a correction table, or one of the two structures which need no memory at all - a cascade of rotator cells, or the table realised as gates |
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

The two multi path architectures are the two halves of a table: ``S`` and ``M``
say whether the frame is split, ``F`` and ``C`` say how a path is built - a delay
feedback stage writes the difference of its butterfly back into the delay line,
a delay commutator keeps the data moving forward and reorders it with
multiplexers.  The multi path delay commutator (`pipeline_style="mdc"`) uses the
same first stage as the feedback one and then two commutator chains, which hand
their spectra over one window late: the first frame only fills them.

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

### Storage of the architectures

The four pipelined topologies are named by two independent letters: `S` or `M`
says whether the frame is split, `F` or `C` says how a path is built - `F` writes
the difference of a butterfly back into the delay line of its stage, `C` keeps the
data moving forward and reorders it with multiplexers.  Counting the delay line
registers of a transform of `points` points gives four closed forms:

| topology | delay line storage | `points = 16` | `points = 1024` |
|----------|--------------------|---------------|-----------------|
| `sdf` (single path, feedback)          | `points - 1`   | 15 | 1023 |
| `mdf` (multi path, feedback)           | `points - 2`   | 14 | 1022 |
| `sdc` (single path, commutator)        | `2 * points - 2` | 30 | 2046 |
| `mdc` (multi path, commutator)         | `2 * points - 4` | 28 | 2044 |

Two things are worth reading off this table.  A commutator chain needs about
twice the storage of a feedback chain, because the feedback one reuses the
register of a stage for the difference that the butterfly produced, while the
commutator one keeps the data moving and needs a second line per stage to align
it again.  And splitting the frame buys almost nothing in storage: `mdf` saves a
single register against `sdf`, `mdc` two against `sdc`, since each of the two
chains holds `points / 2 - 1` instead of `points - 1`.

What the multi path variants buy is not storage but throughput: two chains work
at the same time, each on half of the frame.  The implementations here do not
cash that in - they collect a frame into registers, `points` cycles long, and
then feed the leading butterfly in a burst of `points / 2` cycles, so a frame
still costs about `points` cycles.  Taking the two samples of the first stage on
the same cycle, which is what the architecture is drawn for, would halve that,
and it is the natural next step rather than something the current code does.

The numbers above are the delay lines, the part which follows from the topology.
On top of them every implementation holds buffers which follow from its control:
the delay feedback and delay commutator modules keep a bank of `points` words
(and the commutator two banks, since it writes one while reading the other), and
the multi path modules collect the frame into `points` words, because a sample
and its partner are `points / 2` apart.  Those buffers do not differ much between
the topologies, and the multi path modules currently inherit a bank from each of
the single path modules they instantiate on top of their own, which is redundant
and could be removed.

A stage of radix `R` combines `R` samples which are `length / R` apart, applies
an `R` point transform to them and rotates the result.  Writing `R = 2` gives
back the radix 2 stage, so `radices="2,2,2"` is the same pipeline as
`radices="2"` - and the mixed radix model is checked to be bit exact with the
radix 2 one, which is what makes the generalisation trustworthy.  The
decomposition is in `fft_radix_model.py`, the pipeline builds one stage per
radix: `radices="4"` on 16 points replaces two radix 2 stages.

The `R` point transform inside a butterfly is the one place where the roots of
unity `+1`, `-1` and `-j` are needed inside a stage, and they are applied
exactly, for the reason the twiddles are: the table cannot hold them.  A radix 4
butterfly therefore needs no multiplier at all, a radix 8 one only for the
eighth roots which are neither.

### Twiddle factors without a memory

A table holds `points / 2` factors, which for a small transform is its largest
part.  Two structures replace it, and they are different designs rather than two
names for one thing:

| | `no_mem_cascade` | `no_mem_logic` |
|---|---|---|
| structure | a chain of rotator cells, one per bit of the index | gates: the table realised as logic |
| cell | a constant rotation, a shift and add chain - no multiplier | a sum of products over the index bits |
| has an angle iteration | no, feed forward | no |
| cost grows with | `log2(points)` cells | the number of points |
| values | within one unit of the table | the table, bit for bit |
| applies to | any number of points | a small transform |

The cascade splits the factor along the bits of its index,
`W**k = product of W**(2**i)` over the bits `i` of `k` which are set, and cell
`i` rotates by its constant when bit `i` is set and passes through when it is
not.  It is the multiplier free cascade of Huang and Chen (IEEE TVLSI, 2014):
feed forward, no residual angle, and one more cell extends the supported number
of points, so the design scales from 64 to 32768 points by adding or removing
cells.  A cell multiplies by a constant, which is a shift and add chain rather
than a multiplier; the shifts which two neighbouring cells share are left for
the synthesis tool to find and share.  Two details decide whether it is nearly exact or not - it starts at
the factor of the highest bit which is set, because the format cannot hold
`+1.0`, and its cells work in `GUARD` extra bits and saturate, because a product
whose magnitude is exactly one is one unit past what the format holds and
would otherwise wrap to the other end of the range with the wrong sign.  With
both, the factor is within one unit of the table for every width and number of
points measured.

The logic one keeps the values and drops the memory: every output bit is a
boolean function of the index bits, built at elaboration time from the entries
the table would hold.  Nothing is approximated, but the gates grow with the
number of points, so it is the structure for a small transform with a fixed
size - which is the case it is published for, the ROMless generator of the low
power literature: for a fixed transform the bus sum of the logic terms costs
less power than the smallest table which holds the factors.  `LOGIC_LIMIT` is
where this implementation stops; `no_mem_cascade` is the structure which scales.

A stage of radix `R` combines `R` samples which are `length / R` apart.  In a
delay line topology the timing follows from one observation: a shift register of
depth `d` hands out what was pushed into it `d` cycles ago, so `d` is the time a
value has to be held.  The sample of quarter `q` waits `(R-1-q)*sub` cycles for
the butterfly and the difference of arm `r` waits `r*sub` cycles before it leaves,
which is the same set of durations - so a stage keeps `R - 1` registers of depth
`k*sub`, and the latency stays `points - 1` for every radix.

What the larger butterfly costs is storage.  Per stage a delay feedback chain
needs `L*(R-1)/2` registers against `L/2` at radix 2, so a uniform radix `R`
transform of `N` points needs about `N*R/2` - twice as much at radix 4, four times
at radix 8.  A commutator chain needs twice that again, because the results need
lines of their own: it has no feedback loop, which is what it trades the
registers for.

Not implemented yet: the split radix transform, the block floating point format
.  A radix
larger than 2 is wired into the unrolled pipeline only; the other architectures
have a radix 2 butterfly hard wired in their stages.  The parameters are already
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