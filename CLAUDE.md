# CLAUDE.md: project brief and rules

Read this first in every session.

## Goal

An honest evaluation of machine-learning bearing-fault classifiers on the
Case Western Reserve University (CWRU) bearing dataset, in two parts:

1. **Show how data leakage inflates CWRU results.** Many published models
   report about 99% accuracy. That usually happens because short windows cut
   from the *same* recording end up in both the training set and the test
   set, so the model recognises the recording rather than the fault.
2. **Test whether physics-informed features generalise better.** These are
   features built from bearing fault frequencies (BPFO, BPFI, BSF, FTF),
   normalised by shaft speed. We compare them against generic statistical
   features under honest splits.

The owner is a mechanical engineer with little coding experience. This is
a portfolio project. Keep the code simple and well commented, and explain
every decision in plain English.

## Rules

1. **Never fit anything on test data.** This covers models, scalers,
   normalisation statistics, feature selection, hyperparameter tuning and
   decision thresholds. Fit on the training data only, then apply to the
   test data. Choose the train/test split *before* looking at any test
   result.
2. **Every session ends with:**
   - all tests passing (`python -m unittest discover -s tests -v`),
   - an updated `CHANGELOG.md`,
   - a plain-English summary for the owner (what was built, what was
     surprising, what needs a decision).

### Working conventions

- Stack: Python 3 with numpy, scipy, pandas, scikit-learn and matplotlib
  only. Tests use Python's built-in `unittest`. CPU only. Versions are
  pinned in `requirements.txt`.
- The project never downloads data or models from the internet. All data
  comes from `data/raw/`.
- Every fixed fact (file list, labels, bearing geometry, nominal speeds,
  sampling rates, paths) lives in `src/config.py` and nowhere else.
- Other code gets signals only through `load_data.load_signal()`. That
  guarantees every signal arrives at 12 kHz and low-pass filtered at 5 kHz
  (flat to 4.8 kHz, at least 120 dB down above 5.2 kHz).
- **Features use 0-4.8 kHz only.** Above that, the normal files still
  differ from the fault files at around −110 dB because they were recorded
  differently (docs/VALIDATION.md 3.5).
- Files in `results/` are written by scripts. Never edit them by hand.
- Report unexpected or negative findings in `docs/VALIDATION.md`. Do not
  hide them.
- Simple and readable beats clever. One idea per function, with a comment
  saying *why*, not only *what*.

## Context

### Data files

`data/raw/` should hold 40 CWRU `.mat` files, named by CWRU file number
(e.g. `105.mat`).

| Condition | Fault size | Files (0, 1, 2, 3 HP) |
|---|---|---|
| Normal | none | 97, 98, 99, 100 |
| Inner race | 0.007 in | 105, 106, 107, 108 |
| Inner race | 0.014 in | 169, 170, 171, 172 |
| Inner race | 0.021 in | 209, 210, 211, 212 |
| Ball | 0.007 in | 118, 119, 120, 121 |
| Ball | 0.014 in | 185, 186, 187, 188 |
| Ball | 0.021 in | 222, 223, 224, 225 |
| Outer race @ 6:00 | 0.007 in | 130, 131, 132, 133 |
| Outer race @ 6:00 | 0.014 in | 197, 198, 199, 200 |
| Outer race @ 6:00 | 0.021 in | 234, 235, 236, 237 |

- Within each group of four, the loads are 0, 1, 2 and 3 HP. Nominal speeds
  are about 1797, 1772, 1750 and 1730 rpm.
- The fault data is drive-end (DE) at 12 kHz. Use the DE channel.
- Use each file's stored RPM where present, otherwise the nominal speed.
  98 and 99 store no RPM.
- **The normal files 97-100 were recorded at 48 kHz** (checked from the
  data by `src/check_sampling_rate.py`). `load_signal()` resamples them to
  12 kHz.
- **99.mat also contains a copy of 98's signal** (`X098_DE_time`). The
  loader uses `X099_DE_time` and reports the copy. No file is excluded.

**Data status (2026-11-01):** all **40 of 40** files are present and
readable. Known issues and evidence are in `docs/VALIDATION.md`:
- the normal class was recorded differently (48 kHz, no BA channel, 97 is
  only 5 s long). That is a leakage risk;
- the envelope label check (`src/check_fault_signatures.py`) finds the
  labelled fault in 26 of 40 files. It finds no sharp ball line in any of
  the 12 ball files (ball 0.021 looks like inner race), and only 1 of the
  4 outer-race 0.014 in files matches.

**Labels: CWRU's labels are kept exactly as published** (owner decision,
2026-11-02), even where the label check disagrees. Every result must be
reported **per class** (and per fault size), with the ball and outer-race
0.014 in groups flagged (docs/VALIDATION.md 4.3).

### Bearing

Drive-end bearing: SKF 6205-2RS JEM. 9 balls, ball diameter 7.94 mm, pitch
diameter 39.04 mm, contact angle 0 degrees.

CWRU's published multipliers (× shaft speed): BPFI 5.4152, BPFO 3.5848,
FTF 0.39828, rolling element 4.7135. The last one is **2 × BSF**. The
standard BSF is 2.3567. See `docs/VALIDATION.md`.

### Checked against the official website (2026-11-02)

- All 40 file numbers, labels and file sizes match CWRU's Bearing Data
  Center. The record is `data/cwru_official_reference.csv`, and tests
  re-check it offline. No data was downloaded.
- The official site contradicts itself on whether 6:00 is the centre of
  the load zone or orthogonal to it. Do not state either as fact.
- The site gives no sampling rate for the normal files. Our data shows
  48 kHz (docs/VALIDATION.md 1.3 and 3).

## Repository structure

Status as of 2026-11-01: [done] = exists, [planned] = not written yet.

```
bearing-fault-honest-eval/
├── CLAUDE.md                     project brief and rules (this file)       [done]
├── CHANGELOG.md                  what changed in each session              [done]
├── README.md                     portfolio-facing summary                  [planned]
├── requirements.txt              pinned library versions                   [done]
├── data/raw/                     CWRU .mat files, e.g. 105.mat             [40 of 40]
├── data/cwru_official_reference.csv  official names + sizes (read 2026-11-02) [done]
├── src/
│   ├── config.py                 all fixed facts: files, labels, geometry  [done]
│   ├── load_data.py              load files, manifest, duplicate check     [done]
│   ├── check_sampling_rate.py    12 vs 48 kHz check from the 1x peak      [done]
│   ├── check_band_edge.py        proves the 5 kHz low-pass evens out
│   │                             the band edge across classes            [done]
│   ├── bearing_physics.py        fault frequencies from geometry           [done]
│   ├── check_fault_signatures.py envelope spectrum: does each file show
│   │                             its labelled fault frequency?             [done]
│   ├── segment.py                cut signals into fixed-length windows     [planned]
│   ├── features_statistical.py   generic features (RMS, kurtosis, ...)     [planned]
│   ├── features_physics.py       envelope energy at BPFO/BPFI/BSF/2xBSF    [planned]
│   ├── splits.py                 leaky vs honest train/test splits         [planned]
│   └── evaluate.py               train models, score, save results         [planned]
├── tests/                        one test file per src module              [done for 6 modules]
├── results/                      generated tables and figures              [done]
└── docs/
    ├── VALIDATION.md             evidence that each step is correct        [done, v3.1]
    └── HOW_IT_WORKS.md           plain-English guide to every file         [done, v2]
```

### Planned approach (subject to the owner's decisions)

1. **Leaky baseline:** cut each recording into windows and split the windows
   randomly. Windows from the same 10-second recording land on both sides.
   Expect inflated accuracy.
2. **Honest splits:** split by recording. In CWRU each (fault, size, load)
   combination is a single recording, so "unseen recording" means "unseen
   load". Main test: leave one load out (train on 3 loads, test on the 4th).
   Harder test: leave one fault size out.
3. **Features:** generic statistical features compared with physics-informed
   features (envelope-spectrum energy at fault frequencies, normalised by
   shaft speed), both under the honest splits.

## How to run

From the repository folder:

```
pip install -r requirements.txt
python -m src.bearing_physics        # fault-frequency table
python -m src.load_data              # manifest + data-quality report
python -m src.check_sampling_rate    # sampling-rate check + plots
python -m src.check_band_edge        # 5 kHz low-pass check + plot
python -m src.check_fault_signatures # envelope label check + plot
python -m unittest discover -s tests -v
```
