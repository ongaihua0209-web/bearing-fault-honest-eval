# Changelog

Newest session first. Each entry says what changed, what was found, and
what comes next.

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
