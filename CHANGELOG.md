# Changelog

Newest session first. Each entry says what changed, what was found, and
what comes next.

## Session 4 (2026-11-02): split protocols, generic-feature baseline, leakage measured

### Added
- `src/config.py`: `WINDOW_LENGTH_SAMPLES = 2048`.
- `src/segment.py`: cuts every recording into back-to-back 2048-sample
  windows with no overlap. That gives 2331 windows: 206 normal, 709 inner
  race, 708 ball and 708 outer race. Each window keeps its recording's
  facts.
- `src/splits.py`: three protocols. The label is the fault location.
  - **A, random:** 80/20, stratified, a new split per seed. Leaky by
    design.
  - **B, unseen load:** train 0-2 HP, test 3 HP.
  - **C, unseen fault size:** 3 folds. The healthy class holds out 1, 2 or
    3 HP; file 97 stays in training because it is short. The docstring
    states that the healthy class still shares one bearing, and that B
    shares every bearing.
- `src/features.py`: feature set F1. RMS, peak, peak-to-peak, crest
  factor, kurtosis (engineering convention, noise = 3), skewness and std.
- `src/run_experiments.py`:
  - **Models:** logistic regression, random forest (300 trees) and
    gradient boosting, with no tuning.
  - **No fitting on test data:** the scaler sits inside a pipeline, so it
    is fitted on training data only. Balanced class weights come from the
    training labels.
  - **Seeds:** 5. Protocol C is averaged over its folds per seed.
  - **Outputs:** `results/results_f1.csv`, plus per-run, per-group,
    per-fold and confusion-matrix CSVs, a bar chart, and confusion
    matrices for the best model under A and C.
  - **Run time:** 105 s on a 4-core CPU. A re-run gives identical numbers.
- Tests: 102 (29 new), all passing.
  - `test_splits.py`: no window on both sides; no faulty recording on both
    sides in B and C; the held-out size never in training; the leak in A
    proven to exist.
  - `test_run_experiments.py`: the scaler learns from training data only;
    scrambling the test labels changes no prediction.
  - `test_features.py` and `test_segment.py`.
- `docs/HOW_IT_WORKS.md` v4: data leakage explained with an exam analogy,
  why protocol A is misleading, and the new files. `docs/VALIDATION.md` v4,
  new section 5. `CLAUDE.md` updated.

### Found (macro-F1, mean ± std over 5 seeds)
| Protocol | Logistic regression | Random forest | Gradient boosting |
|---|---|---|---|
| A random | 0.854 ± 0.011 | 0.986 ± 0.003 | 0.981 ± 0.005 |
| B unseen load | 0.763 ± 0.000 | 0.968 ± 0.001 | 0.959 ± 0.001 |
| C unseen fault size | 0.504 ± 0.000 | 0.458 ± 0.004 | 0.460 ± 0.001 |

- **Leakage inflates the random forest's macro-F1 from 0.46 to 0.99.** B
  keeps most of the inflation (0.97), because it tests on bearings already
  studied at other loads.
- **Under C, inner race collapses** to 0-9% correct for the tree models,
  even though it has the clearest physical signature.
- **"Ball" becomes the default answer:** 61% of all faulty test windows are
  called ball by the random forest.
- **Outer race 0.007 and 0.014 score 0%; 0.021 scores about 100%.**
- **Normal scores 100% everywhere.** It shares its bearing, so this does not
  show that healthy bearings are recognised in general.
- **Logistic regression is worst under A and B but best under C.**
- **Folds vary far more than seeds** (C folds 0.32-0.72).

### Next steps
1. Physics-informed features: envelope band energy at BPFO, BPFI, BSF and
   2×BSF, normalised by shaft speed. Compare with F1 under B and C; inner
   race under C is the clearest test.
2. Write `README.md` around the A → B → C chart.
3. Read Smith & Randall (2015) in full.

## Session 3b (2026-11-02): checked against CWRU's official website

Owner request: check the files against the official website. The owner
allowed `engineering.case.edu` in the session's network settings. No data
file was downloaded; file sizes came from header-only requests.

### Added / changed
- `data/cwru_official_reference.csv` (new): the official name, size in
  bytes, date and address of each of our 40 files, as listed on 2026-11-02.
- `src/config.py`:
  - `cwru_name()` gives each file's official name, which now also appears
    in the manifest;
  - `OFFICIAL_REFERENCE_CSV` points to the reference file;
  - FTF updated to CWRU's 5-decimal figure, 0.39828;
  - `FAN_END_CWRU_MULTIPLIERS` added;
  - the load-zone wording is corrected.
- `src/check_fault_signatures.py`: also records two raw-spectrum peaks per
  file, at the drive-end and fan-end BPFI. They are not used in verdicts.
- Tests: 73 (5 new), all passing. They check offline that all 40 labels
  match the official names and all 40 file sizes match.
  - Swapping two condition groups in the config makes 8 subtests fail.
- `docs/VALIDATION.md` v3.1:
  - new section 1.3 (website check);
  - section 2.3 adds the FTF note;
  - section 4.1 is rewritten with the explanation of the rig-wide peaks.
  - `CLAUDE.md` and `docs/HOW_IT_WORKS.md` updated.

### Found
- **All 40 files match the official site:** same file number → condition,
  fault size and load (40/40), and the same size to the byte (40/40).
- Nominal speeds, bearing geometry, and BPFI, BPFO and rolling-element
  multipliers all match.
- CWRU's FTF (0.39828) is 0.008% off their own BPFO ÷ 9 (0.39831), which is
  negligible.
- **The site gives no sampling rate for the normal files**, so it does not
  contradict our 48 kHz finding. RPM was "recorded by hand", and the site
  says every file has RPM, but 98 and 99 do not.
- **The site contradicts itself on the outer-race position.** Its table
  says the load zone is centred at 6:00; its procedures page calls 6:00
  "orthogonal to the load zone". Our "@6" labels are unaffected.
- **The rig-wide raw peaks are explained.** At 5.40× and 4.93× shaft speed
  they are the inner-race frequencies of the drive-end and fan-end bearings
  (fan-end value from the official site). They are in all 40 files, both
  about 0.27% below theory.

## Session 3 (2026-11-02): envelope label check; CWRU labels kept

Owner decisions:
- keep CWRU's labels exactly as published;
- turn the exploratory envelope check into a tested script.

No models trained.

### Added / changed
- `src/check_fault_signatures.py` (new): envelope analysis for every file.
  - **Band choice:** the spikiest (highest-kurtosis) of nine 1.2 kHz bands
    between 0.4 and 4.8 kHz, plus a fixed 2.0-4.8 kHz band as a second
    opinion.
  - **Evidence:** peak/background at BPFO, BPFI and BSF/2×BSF; a type is
    clear at 10 or more.
  - **Verdict per file:** matches label, looks like X, or no signature.
  - **Rules:** fixed and tested on synthetic signals before the first run
    on real data.
  - **Sensitivity check:** a ±1% window, added after the first run (see
    Found). The CSV also records where each peak was found.
- `src/check_sampling_rate.py`: `peak_strength()` now takes the window
  sizes as optional arguments. Its default behaviour is unchanged.
- `tests/test_fault_signatures.py` (new, 15 tests). They cover:
  - synthetic outer-race, inner-race and ball signals, a mislabelled
    signal, and noise;
  - band choice ignoring a loud hum;
  - the verdict rules and the window widths;
  - positive controls on real data (inner race 0.007, outer race 0.007,
    normal).

  The total is 68 tests, all passing. One synthetic test was corrected
  before the real run: its signal was unrealistically noise-free, and it is
  now realistically noisy. The method was not changed.
- `src/config.py` comment, `CLAUDE.md` (label decision, per-class
  reporting rule), `docs/VALIDATION.md` v3 (sections 4.2 and 4.3 rewritten),
  `docs/HOW_IT_WORKS.md` v3.

### Found
- **26 of 40 files match their label:** all normal, all 12 inner race,
  outer race 0.007 and 0.021, plus 199 (outer race 0.014) and 120 (ball
  0.007).
- **Ball:** no sharp ball line in any of the 12 files.
  - 0.021: all 4 look like inner race.
  - 0.014: no signature in any of the 4.
  - 0.007: mixed outer-race and inner-race evidence.
- **Outer race 0.014:** 1 of 4 matches; 197 and 198 look like inner race,
  and 200 shows nothing.
- **Window overlap.** "Ball" evidence in the inner-race and outer-race files
  is not real ball evidence. It comes from peaks at 2.40× (the inner-race
  sideband BPFI − 3×) and 4.79-4.80×, sitting at the edges of the ±2% ball
  windows.
  - A ±1% window removes them and changes exactly one verdict: ball 120
    goes from "match" to "looks like outer + inner race".
  - Under the narrow window, 0 of 12 ball files match.
- **Broad humps.** Ball files 222 and 223 show broad humps near BSF and
  2×BSF, which the sharp-peak measure cannot detect. So "no signature"
  does not mean "no fault".

### Next steps
1. Write `README.md`.
2. Read Smith & Randall (2015) in full.
3. Agree window length, overlap and split design before `segment.py` and
   `splits.py`.
4. When designing physics features, consider band energy around BSF and
   2×BSF, which can see broad humps, instead of sharp-peak ratios only.

## Session 2b (2026-11-01): 5 kHz low-pass on every signal

Owner decision: low-pass every signal at about 5 kHz, to remove the
recording-equipment difference between the normal and fault files.

### Added / changed
- `src/config.py`: low-pass spec. Flat below 4.8 kHz, at least 60 dB down
  above 5.2 kHz per pass, so the cutoff sits at 5.0 kHz.
- `src/load_data.py`:
  - `lowpass_filter_taps()` designs the filter: 111 weights, Kaiser window;
  - `lowpass()` runs it forwards and backwards, so there is no time shift;
  - `load_signal()` now resamples **and** low-passes every signal.
- `src/check_band_edge.py` (new): measures the resampling filter and the
  low-pass filter, and every file's energy above 5.2 kHz before and after.
  Writes two CSVs and `results/figures/band_edge.png`.
- Tests: 53 (up from 46), all passing.
  - New: the filter spec (flat passband, at least 120 dB stopband, no time
    shift), and a check that all 40 real signals have less than −100 dB of
    energy above 5.2 kHz.
  - Switching the filter off makes 43 tests fail.
- `CLAUDE.md`: new rule, **features use 0-4.8 kHz only**.
  `docs/VALIDATION.md` v2.1 rewrites section 3.5. `docs/HOW_IT_WORKS.md`
  updated.

### Found
- **Why 4.8 / 5.2 kHz.** Measured: scipy's resampling filter is flat
  (within 0.2 dB) up to 5.2 kHz, and the 12 kHz recorder's filter starts
  cutting at about 5.3 kHz. So the two recording chains differ only above
  about 5.2 kHz.
- **Before filtering, the gap was 59 dB** at 5.95 kHz: −67.5 dB for the
  typical fault file against −8.9 dB for the typical normal file. That
  was an easy shortcut for a classifier.
- **After filtering, all 40 files have less than −130 dB of their energy
  above 5.2 kHz.**
- **A trace remains there.** The normal files still sit 10-15 dB above the
  fault files, at around −110 dB, hence the 0-4.8 kHz rule for features.
- **New:** the normal files share sharp tones at 4.1-4.3 kHz that no fault
  file has. They sit inside the kept band, so they are a possible shortcut
  that filtering cannot remove. Cause unknown.

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
2. Owner decision (see summary): how
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
