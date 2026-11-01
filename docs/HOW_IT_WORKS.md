# How it works: version 2 (2026-11-01)

A plain-English guide to every file in this project, written for someone
who has never programmed.

## The big picture

The project is a measurement chain, like an instrumented test rig. Each
step checks the one before it before anything gets built on top:

```
 raw recordings     check & list them      check the physics       (later)
 data/raw/*.mat --> load_data.py      --> bearing_physics.py  --> features
                    check_sampling_rate.py                     --> models
                                                              --> honest scores
```

So far only the first two stages exist. Nothing is trained yet.

## Words you will meet

- **Script / program:** a text file of instructions the computer follows,
  top to bottom. Ours end in `.py` because they are written in Python.
- **Function:** a named, reusable recipe inside a script, e.g.
  `bpfo_multiplier()`. It takes some inputs, does one job and hands back a
  result, like a formula cell in a spreadsheet.
- **Library:** a toolbox someone else wrote and tested. We use five:
  - numpy: maths on long lists of numbers,
  - scipy: signal processing and reading MATLAB files,
  - pandas: tables,
  - scikit-learn: machine learning, later,
  - matplotlib: plots.
- **`.mat` file:** a MATLAB data file. Each CWRU file holds about 10 seconds
  of accelerometer readings (about 122,000 numbers per sensor) plus the
  measured shaft speed.
- **Sampling rate:** how many readings the accelerometer takes per second.
  12 kHz means 12,000 per second. The software has to be told this number,
  and if it is told the wrong one, every frequency it calculates is wrong
  by the same factor.
- **Spectrum (FFT):** splits a vibration signal into how much of each
  frequency it contains, like a frequency analyser on the rig.
- **Test:** a small script that checks another script gives a known right
  answer, like a calibration check. If anyone changes the code and breaks
  something, a test fails and says where.

## The files, one by one

### Top-level files

| File | What it is |
|---|---|
| `CLAUDE.md` | The project brief: goal, data facts, rules, plan. Any AI assistant (or person) working on the project reads it first. |
| `CHANGELOG.md` | A diary: what changed in each working session and what comes next. |
| `requirements.txt` | The exact versions of the five libraries, so anyone can rebuild the same setup and get the same numbers. |
| `.gitignore` | Tells git to ignore temporary files Python creates by itself. |
| `README.md` | The front page on GitHub. Still a stub. |

### `data/raw/`: the recordings

The CWRU `.mat` files, named by CWRU file number (e.g. `234.mat`). Scripts
only ever *read* these. Nothing changes them.

### `src/`: the working code

**`src/config.py`: the data sheet.**
It holds no logic, only facts: the list of 40 expected files and what each
one is (fault location, size, motor load), the bearing geometry, nominal
speeds, the assumed sampling rate and folder locations. Every other script
reads facts from here, so a correction only has to be made once.

**`src/load_data.py`: goods-in inspection.**
Run with `python -m src.load_data`. For each of the 40 expected files it:
1. checks whether the file exists, and lists any that are missing;
2. opens it and picks out the drive-end accelerometer signal. CWRU names
   that signal after the file (`X234_DE_time` inside `234.mat`). If the
   names don't match, it says so instead of guessing;
3. reads the stored shaft speed, or uses the nominal speed if none is
   stored, and records which;
4. checks whether any two files contain the *same* recording. It computes
   a "fingerprint" (a hash: a short code that changes if even one number
   changes) for every signal and compares them. Exact copies are excluded.
   Signals that merely start the same are reported, but kept;
5. writes two outputs:
   - `results/manifest.csv`: one row per expected file, with its facts and
     a status (ok, missing, unreadable or excluded_duplicate);
   - `results/data_quality_report.txt`: a readable list of everything odd.

It also contains `load_signal()`, the one doorway later code uses to get a
signal. Every signal comes out of it prepared the same way:
1. **at 12 kHz:** any file known to be 48 kHz is converted on the way;
2. **with everything above about 5 kHz removed** by a low-pass filter.

The second step exists because the normal files were recorded on different
equipment settings. Near the top of the frequency range (5-6 kHz) they
look different from the fault files for reasons that have nothing to do
with bearings. Cutting that region off for everyone removes the
difference. Think of trimming every test piece to the same length before
comparing them.

**`src/check_sampling_rate.py`: checking the "clock".**
Run with `python -m src.check_sampling_rate` (after `load_data`). It
answers: was each file really recorded at 12 kHz?
- The shaft turns rpm/60 times a second (about 30 Hz), so the spectrum
  should show a peak there, and usually at 2× and 3× as well.
- If a file were really 48 kHz but read as 12 kHz, every frequency would
  come out 4 times too low. Its 1×, 2× and 3× peaks would then show up at
  ¼, ½ and ¾ of shaft speed instead.
- A genuine 12 kHz recording has no reason to vibrate at those fractions.
  So peaks there are the tell-tale sign of a 48 kHz file.

This is how we found that the four normal (healthy) files were recorded at
48 kHz. `config.py` records that, and `load_signal()` converts them to
12 kHz. The script writes `results/sampling_rate_check.csv` and a plot per
file in `results/figures/`, including a "resampled to 12 kHz" plot for each
converted file.

**`src/check_band_edge.py`: proving the 5 kHz cut works.**
Run with `python -m src.check_band_edge`. It measures:
- how the 48 → 12 kHz conversion and the 5 kHz filter each treat every
  frequency;
- how much vibration energy each file has above 5.2 kHz, before and after
  the filter.

It writes `results/band_edge_by_file.csv`, `results/band_edge_filters.csv`
and `results/figures/band_edge.png`. The figure shows the normal and
fault files side by side, before and after.

**`src/bearing_physics.py`: the pencil-and-paper part.**
Run with `python -m src.bearing_physics`. It calculates the bearing fault
frequencies (FTF, BPFO, BPFI, BSF) from the ball count and dimensions,
using the standard textbook formulas. The tests check its answers against
CWRU's published numbers. It writes `results/fault_frequencies.csv` (the
frequencies in Hz at each motor load).

### `tests/`: the calibration checks

One test file per script. Run them all with:

```bash
python -m unittest discover -s tests -v
```

Each line of output is one check, ending in `ok` or `FAIL`. Examples:
- `test_bearing_physics.py`: do our formulas reproduce CWRU's published
  multipliers? Does BPFO + BPFI equal the number of balls, as the maths
  says it must?
- `test_load_data.py`: given a small fake folder with a missing file, a
  copied file and a file with no stored speed, does the loader report all
  three correctly?
- `test_sampling_rate.py`: given a fake signal *known* to be 48 kHz, does
  the check catch it? Do the real files come out as 12 kHz?
- `test_band_edge.py`: after `load_signal()`, does every one of the 40
  files have practically nothing left above 5.2 kHz? (`test_load_data.py`
  also checks the filter itself: unchanged below 4.8 kHz, at least 120 dB
  down above 5.2 kHz, and no time shift.)

Most tests use small made-up signals where the right answer is known in
advance. That is the same idea as checking a gauge against a reference
block before trusting it on a real part.

### `results/`: what the scripts produced

Everything here is written by the scripts. Never edit it by hand: change
the code or `config.py` and re-run instead.

| File | Written by |
|---|---|
| `manifest.csv` | `load_data.py` |
| `data_quality_report.txt` | `load_data.py` |
| `sampling_rate_check.csv` | `check_sampling_rate.py` |
| `figures/sampling_rate/<file>.png`, `figures/sampling_rate_overview.png` | `check_sampling_rate.py` |
| `band_edge_by_file.csv`, `band_edge_filters.csv`, `figures/band_edge.png` | `check_band_edge.py` |
| `fault_frequencies.csv` | `bearing_physics.py` |

### `docs/`: the write-ups

- `VALIDATION.md`: the evidence that each step is right, including hand
  calculations, plots and every data-quality finding.
- `HOW_IT_WORKS.md`: this file.

## How to run everything

Open a terminal in the project folder and run these one at a time.

1. Install the libraries (once):

   ```bash
   pip install -r requirements.txt
   ```

2. Build the fault-frequency table:

   ```bash
   python -m src.bearing_physics
   ```

3. Inspect the data and write the manifest:

   ```bash
   python -m src.load_data
   ```

4. Check the sampling rates and draw the plots:

   ```bash
   python -m src.check_sampling_rate
   ```

5. Check the 5 kHz filter:

   ```bash
   python -m src.check_band_edge
   ```

6. Run all the tests:

   ```bash
   python -m unittest discover -s tests -v
   ```

`python -m src.load_data` means "run the `load_data` script inside the
`src` folder". It must be run from the project's top folder, so that
Python can find `src`.

## Adding or replacing data files

All 40 files are in `data/raw/`. If a file is ever added or replaced, name
it by file number (e.g. `105.mat`) and re-run steps 3-6. The manifest, the
duplicate check and the sampling-rate check cover it automatically, and the
tests fail if anything about it does not add up.
