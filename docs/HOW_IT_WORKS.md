# How it works: version 4 (2026-11-02)

A plain-English guide to every file in this project, written for someone
who has never programmed.

## The big picture

The project is a measurement chain, like an instrumented test rig. Each
step checks the one before it before anything gets built on top:

```
 raw recordings     check & list them      cut into windows    describe each     train & test
 data/raw/*.mat --> load_data.py      --> segment.py      --> window         --> run_experiments.py
                    check_*.py                                features.py        (3 ways of testing:
                    bearing_physics.py                                            splits.py)
```

The checking stages are complete. The first experiment (generic features,
three ways of testing) is in place; physics-based features come next.

## Data leakage, explained with an exam

Imagine a teacher who wants to know whether students understand
mechanics. She writes 100 questions, gives the students 80 to study, and
sets the exam from the other 20.

Now imagine the 100 questions were made by taking 10 long problems and
cutting each into 10 small steps. Steps from the same problem look alike:
same numbers, same diagram. If the 80 study questions and the 20 exam
questions are picked at random, almost every exam question has a sibling
in the study pile. A student who memorised the study pile scores 98% on
the exam without understanding any mechanics. They recognise the problem;
they do not solve it.

That is **data leakage**, and it is exactly what happens with CWRU:

| Exam | This project |
|---|---|
| a long problem | one 10-second recording |
| its small steps | the 0.17-second windows cut from it |
| study pile / exam | training set / test set |
| memorising the problem | recognising the recording: its loudness, noise and quirks |
| understanding mechanics | recognising the *fault*, on a machine never seen before |

**Why protocol A (random windows) is misleading.** It is the random
pick in the story. Every recording ends up in both the training and the
test set, so the model can score highly just by recognising recordings.
In our run it scores 0.99, which looks like a solved problem. When the
same models are tested on fault sizes they have never seen (protocol C),
they score about 0.46-0.50, where 0.25 is pure guessing.

The 0.99 was not wrong arithmetic. It answered a different, much easier
question ("have I seen this recording before?") than the one that matters
("can I recognise this fault on a new bearing?").

**Protocol B (new load) leaks too, in a quieter way.** Each CWRU fault is
one physical bearing, recorded at four loads. Testing at a new load still
tests the *same bearing* the model studied, like an exam with the same
problems and slightly different numbers. That is why B scores almost as
high as A (0.97).

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

### `data/cwru_official_reference.csv`: the official check

What CWRU's official website listed on 2026-11-02 for each of our 40
files: its official name (e.g. `IR007_0`), its size in bytes, and its
download address. Think of it as the supplier's delivery note. The tests
compare our labels and our files against it every time they run, without
going online. All 40 names and all 40 sizes match.

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

**`src/check_fault_signatures.py`: does each file show its labelled fault?**
Run with `python -m src.check_fault_signatures`. A damaged spot makes a
small impact every time a ball passes it. Each impact makes the bearing
housing ring briefly, like a struck bell. The script looks for the rhythm
of that ringing:
1. **Pick a band.** Keep only the frequency band where the ringing is
   strongest. The script tries nine bands and keeps the "spikiest" one,
   measured by kurtosis, a number that is large when a signal is made of
   sharp knocks.
2. **Trace the outline.** Follow the outline ("envelope") of the ringing.
3. **Find the rhythm.** Look at how often the outline pulses. A peak at
   BPFO means an outer-race fault, at BPFI an inner-race fault, and at BSF
   or 2×BSF a ball fault.

It then says, for every file, whether that rhythm matches the CWRU label.
It never changes a label; it only reports. It writes
`results/fault_signatures.csv` and
`results/figures/fault_signatures_overview.png`.

**`src/segment.py`: cutting recordings into windows.**
Run with `python -m src.segment`. It cuts every recording into
back-to-back windows of 2048 samples (0.17 s), with no overlap. That gives
2331 windows from the 40 recordings. Every window remembers which
recording, fault type, fault size and load it came from.

**`src/features.py`: describing each window with 7 numbers.**
Feature set "F1" holds seven everyday vibration statistics: RMS, peak,
peak-to-peak, crest factor, kurtosis, skewness and standard deviation.
They know nothing about bearings. (Careful: "F1" is the name of this
feature set; "macro-F1" is a score, explained below.)

**`src/splits.py`: three ways of choosing the exam.**
- **A, random:** shuffle all windows and keep 20% for testing. Leaky on
  purpose (see "Data leakage, explained with an exam").
- **B, unseen load:** train on 0-2 HP, test on 3 HP. No recording is on
  both sides, but every bearing is.
- **C, unseen fault size:** three rounds. Each round tests on one fault
  size (0.007, 0.014 or 0.021 in) of every fault type, and trains on the
  other two. The faulty test bearings are truly new. The healthy class has
  only one bearing, so the healthy test windows come from that same
  bearing at a different load.

**`src/run_experiments.py`: the experiment.**
Run with `python -m src.run_experiments`. It takes about 2 minutes. For
every protocol it trains three kinds of model:
- logistic regression, which draws straight dividing lines;
- random forest, a vote among hundreds of decision trees;
- gradient boosting, which builds trees one after another, each fixing
  the last one's mistakes.

Each is trained with 5 different random seeds, to show how much the
results wobble.

The scaler that puts all features on the same scale learns only from the
training windows. That is rule 1 of the project: never let the test set
leak into training in any form.

Scores:
- **Macro-F1:** how well each class is caught, without false alarms,
  averaged so that all four classes count equally. 1.0 is perfect; about
  0.25 is guessing.
- **Balanced accuracy:** the share of each class recognised, averaged
  equally over the classes.

The results go into `results/` (see the table below), including a chart
and confusion matrices. A confusion matrix shows, for each true class, what
the model said it was.

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
- `test_fault_signatures.py`: given fake signals with a *known* fault
  (impacts at exactly BPFO, BPFI or 2×BSF, buried in noise), does the check
  name the right fault, and only that one? Do textbook-clear real files
  (inner race 0.007, outer race 0.007) match, and do healthy files show
  nothing?
- `test_band_edge.py`: after `load_signal()`, does every one of the 40
  files have practically nothing left above 5.2 kHz? (`test_load_data.py`
  also checks the filter itself: unchanged below 4.8 kHz, at least 120 dB
  down above 5.2 kHz, and no time shift.)
- `test_splits.py`: the proof that the exams are set fairly.
  - No window is ever in both the training and the test set.
  - In protocols B and C no faulty recording is either.
  - In C the held-out fault size never appears in training.
  - It also proves the leak in protocol A really exists: every recording
    is on both sides.
- `test_run_experiments.py`:
  - The scaler learns only from training data.
  - Scrambling the test answers does not change a single prediction, which
    shows the models never see them.
- `test_features.py`: does a sine wave of amplitude 2 give RMS 1.414,
  crest factor 1.414 and kurtosis 1.5, as the textbook says?
- `test_segment.py`: are windows cut back to back, with no sample used
  twice?

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
| `fault_signatures.csv`, `figures/fault_signatures_overview.png` | `check_fault_signatures.py` |
| `fault_frequencies.csv` | `bearing_physics.py` |
| `results_f1.csv`: headline scores, protocol × model | `run_experiments.py` |
| `results_f1_runs.csv`, `results_f1_by_group.csv`, `results_f1_by_fold.csv`, `confusion_matrices_f1.csv` | `run_experiments.py` |
| `figures/f1_macro_f1_by_protocol.png`, `figures/f1_confusion_*.png` | `run_experiments.py` |

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

6. Check each file against its label:

   ```bash
   python -m src.check_fault_signatures
   ```

7. Run the leakage experiment (about 2 minutes):

   ```bash
   python -m src.run_experiments
   ```

8. Run all the tests:

   ```bash
   python -m unittest discover -s tests -v
   ```

`python -m src.load_data` means "run the `load_data` script inside the
`src` folder". It must be run from the project's top folder, so that
Python can find `src`.

## Adding or replacing data files

All 40 files are in `data/raw/`. If a file is ever added or replaced, name
it by file number (e.g. `105.mat`) and re-run steps 3-7. The manifest, the
duplicate check and the sampling-rate check cover it automatically, and the
tests fail if anything about it does not add up.
