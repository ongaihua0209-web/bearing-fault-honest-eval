# Changelog

Newest session first. Each entry says what changed, what was found, and
what comes next.

## Session 2 (2026-11-01): all 40 files added, normal-file questions settled

No models trained.

### Added / changed
- `data/raw/`: the remaining 35 CWRU files. All 40 are now present and
  readable, and each was byte-checked against its upload.
- `src/check_sampling_rate.py` **version 2**:
  - Version 1 returned "inconclusive" on the normal files, because a 48 kHz
    file's 4× harmonic lands exactly where a 12 kHz file's 1× would be.
  - Version 2 adds a test for peaks at 0.25×, 0.5× and 0.75× shaft speed.
    A 12 kHz recording has no reason to show these; a 48 kHz file read as
    12 kHz does. No 12 kHz verdict changed.
  - Plots now mark the quarter orders, and each resampled file gets its
    own "resampled to 12 kHz" plot.
- `src/config.py`: files 97-100 recorded as 48 kHz, with the evidence in a
  comment. `load_signal()` now resamples them to 12 kHz.
- Tests: 46 in total (up from 42), all passing. New ones cover:
  - the 4× trap;
  - a single stray quarter-order peak (must give "inconclusive");
  - every signal from `load_signal()` checking out as 12 kHz;
  - the 98/99 duplicate being reported but not used.
- `docs/VALIDATION.md` v2, `docs/HOW_IT_WORKS.md` v2, `CLAUDE.md` data
  status.

### Found
- **The normal files 97-100 were recorded at 48 kHz.** All 36 fault files
  are 12 kHz. Evidence:
  - quarter-order peaks scoring 11-31 in the normal files, against ≤ 4.9
    in every fault file;
  - a 30.0 Hz peak in 98 and 99 that becomes 120 Hz mains hum at 48 kHz;
  - at 48 kHz, 98-100 last 10.1 s, matching the fault files.
- **99.mat contains a copy of 98's signals** (`X098_DE_time`,
  `X098_FE_time`). The loader uses 99's own signal and reports the copy.
  The srigas `CWRU_Bearing_NumPy` repository reports the same thing. There
  are no other duplicates.
- 98 and 99 store no RPM, so nominal is used. The spectra put them within
  2 rpm of nominal. The 3 HP files run 5-9 rpm below nominal.
- **Leakage risk:** the normal class differs in how it was recorded (48 kHz
  with a different anti-alias filter, no BA channel, 97 is only 5 s long).
- **The 5.40× raw-spectrum peak is in all 40 files, healthy ones included.**
  It is a property of the rig, not a fault sign.
- **Exploratory envelope check (2-5 kHz band):**
  - matches the label clearly in 24 of 40 files: all normal, all inner
    race, outer race 0.007 and 0.021;
  - **no clear signature in the 12 ball files or the 4 outer-race 0.014 in
    files**. Ball 0.021 looks like an inner-race fault, and ball 0.014
    shows only cage-rate (FTF) modulation;
  - this fits secondary reports of Smith & Randall's 2015 CWRU benchmark.

### Next steps
1. Turn the envelope check into `src/check_fault_signatures.py`, with tests
   and a principled band choice.
2. Owner decisions (see summary): low-pass all signals at about 5 kHz; how
   to report ball and outer race 0.014 results.
3. Read Smith & Randall (2015) in full.
4. Write `README.md`.
5. Agree window length, overlap and split design before `segment.py` and
   `splits.py`.

## Session 1 (2026-11-01): foundations, data checks, bearing physics

No models were trained in this session (by design).

### Added
- `CLAUDE.md`: project goal, data and bearing facts, rules, planned
  structure, how to run.
- `requirements.txt`: pinned numpy 2.5.3, scipy 1.18.1, pandas 3.0.5,
  scikit-learn 1.9.1, matplotlib 3.11.2 (Python 3.13). `.gitignore` for
  Python cache files.
- `src/config.py`: the single place for every fixed fact (40-file list and
  labels, geometry, nominal speeds, sampling rates, paths).
- `src/load_data.py`:
  - loads the files and extracts the drive-end signal and RPM (falls back
    to nominal RPM if none is stored);
  - reports missing, unreadable and unexpected files;
  - finds exact duplicates (by hash) and partial copies (identical first
    1,000 samples), and excludes exact duplicates;
  - writes `results/manifest.csv` and `results/data_quality_report.txt`;
  - provides `load_signal()`, which always returns 12 kHz data.
- `src/check_sampling_rate.py`: 12 vs 48 kHz check using the 1× shaft
  peak, per-file and overview spectrum plots (0-200 Hz), and
  `results/sampling_rate_check.csv`. Resampling path (anti-aliased
  `resample_poly`) ready for any file found to be 48 kHz.
- `src/bearing_physics.py`: FTF, BPFO, BPFI, BSF from geometry, and
  `results/fault_frequencies.csv`.
- `tests/`: 42 tests across physics, loading, duplicates, resampling and
  the sampling-rate check. All pass.
- `docs/VALIDATION.md` v1 and `docs/HOW_IT_WORKS.md` v1.

### Found
- **Only 5 of 40 files are in `data/raw/`:** 225 (ball 0.021 in, 3 HP)
  and 234-237 (outer race 0.021 in, 0-3 HP). No normal files, so the
  duplicate-normal-file question and the normal 12-vs-48 kHz question are
  still open.
- All 5 present files are confirmed 12 kHz. No duplicates among them.
- File 237's stored speed is 1721 rpm, 9 rpm below nominal.
- Our formulas reproduce CWRU's BPFI, BPFO and FTF multipliers to 4
  decimals. **CWRU's "rolling element" 4.7135 is exactly 2 × BSF**
  (BSF = 2.3567).
- Unexplained: in all 5 files the tallest raw-spectrum peak below 200 Hz
  is at about 5.40× shaft speed, close to BPFI, although none are
  inner-race faults.
- A quick envelope check (not yet in the repo) agrees with the outer-race
  labels (BPFO) but finds no clear BSF or 2×BSF signature in ball file 225.

### Next steps
1. Add the 35 missing `.mat` files to `data/raw/`, re-run `load_data`
   and `check_sampling_rate`, and update VALIDATION.md, especially the
   normal-file duplicate and 12-vs-48 kHz questions.
2. Turn the envelope check into `src/check_fault_signatures.py` with
   tests, so every file's label is checked against its fault frequency.
3. Write a proper `README.md` for the portfolio.
4. Agree the window length, overlap and split design (see CLAUDE.md,
   "Planned approach") before writing `segment.py` and `splits.py`.
