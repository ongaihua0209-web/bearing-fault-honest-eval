# Validation: version 2 (2026-11-01, all 40 files)

This document holds the evidence that each step of the project does what it
claims. Every number here comes from a script in `src/` and is checked by a
test in `tests/`, except where a section says **exploratory**.

**Changes from version 1:**
- covers all 40 files (version 1 had 5);
- settles the two normal-file questions;
- adds a second test to the sampling-rate check (section 3.2);
- extends the exploratory label check to every file (section 4).

---

## 1. Data inventory and quality

Source: `python -m src.load_data`, which writes `results/manifest.csv` and
`results/data_quality_report.txt`.

### 1.1 What is present

All 40 files are present and readable.

| Condition | Size | Files (0-3 HP) | Stored rpm | Recorded at | Duration |
|---|---|---|---|---|---|
| Normal | none | 97, 98, 99, 100 | 1796, *1772*, *1750*, 1725 | **48 kHz** | 5.1 s (97), 10.1 s (others) |
| Inner race | 0.007 in | 105-108 | 1797, 1772, 1748, 1721 | 12 kHz | 10.1-10.2 s |
| Inner race | 0.014 in | 169-172 | 1796, 1774, 1752, 1728 | 12 kHz | 10.1-10.2 s |
| Inner race | 0.021 in | 209-212 | 1797, 1774, 1752, 1728 | 12 kHz | 10.1-10.2 s |
| Ball | 0.007 in | 118-121 | 1796, 1772, 1748, 1722 | 12 kHz | 10.1-10.2 s |
| Ball | 0.014 in | 185-188 | 1796, 1772, 1749, 1724 | 12 kHz | 10.2 s |
| Ball | 0.021 in | 222-225 | 1796, 1774, 1754, 1729 | 12 kHz | 10.1-10.2 s |
| Outer race @ 6:00 | 0.007 in | 130-133 | 1796, 1773, 1750, 1725 | 12 kHz | 10.1-10.2 s |
| Outer race @ 6:00 | 0.014 in | 197-200 | 1796, 1772, 1749, 1723 | 12 kHz | 10.2 s |
| Outer race @ 6:00 | 0.021 in | 234-237 | 1796, 1771, 1748, 1721 | 12 kHz | 10.2 s |

*Italic* rpm: not stored in the file, so the nominal value is used.

### 1.2 Findings

1. **File 99 contains a copy of file 98.** Besides its own recording
   (`X099_DE_time`), 99.mat holds `X098_DE_time` and `X098_FE_time`. These
   are identical, sample for sample, to the signals in 98.mat.
   - The loader uses the variable named after the file (`X099_DE_time`).
     The copy is reported and ignored, so no file is excluded.
   - 99's own signal is different from every other signal.
   - The srigas `CWRU_Bearing_NumPy` repository reports the same
     duplicate independently (see section 5).
   - 99.mat also contains a stray MATLAB variable called `ans`, which is
     harmless.
2. **There are no other duplicates.** Every drive-end variable in all 40
   files was compared. Apart from the 98/99 copy, no two are identical, and
   none share their first 1,000 samples.
3. **The normal files were recorded at 48 kHz.** Every fault file is 12 kHz.
   They are now resampled to 12 kHz; see section 3.
4. **Two files store no RPM.** 98 and 99 have none, so we use the nominal
   1772 and 1750 rpm. Every other file stores its measured speed.
   - The sampling-rate check finds their shaft peaks at about 1774 and
     1752 rpm, within 2 rpm of nominal, so nominal is a good stand-in.
5. **The 3 HP files run below nominal.** Seven of them (100, 108, 121, 133,
   188, 200, 237) store 1721-1725 rpm against a nominal 1730. That is up
   to 9 rpm (0.5%) lower, and every fault frequency shifts by the same 0.5%.
6. **File 97 is half the length of the others.** It lasts 5.1 s, against
   about 10.1 s for every other file. The normal class therefore has 35 s
   of data in total, against about 40.6 s for each fault group.
7. **The normal files have no base-plate (BA) channel.** Fault files have
   DE, FE and BA. We use only DE, but any model given BA could spot
   "normal" from the missing channel alone.

---

## 2. Bearing fault frequencies

Source: `src/bearing_physics.py`, tested in `tests/test_bearing_physics.py`.
Unchanged from version 1.

### 2.1 Formulas

Symbols: n = number of balls, d = ball diameter, D = pitch diameter,
φ = contact angle, f_r = shaft speed in Hz (rpm / 60).

| Frequency | Meaning | Formula |
|---|---|---|
| FTF | cage (ball holder) rotation | f_r / 2 × (1 − d/D cos φ) |
| BPFO | balls passing a point on the outer race | n f_r / 2 × (1 − d/D cos φ) |
| BPFI | balls passing a point on the inner race | n f_r / 2 × (1 + d/D cos φ) |
| BSF | one ball spinning about its own axis | D / (2d) × f_r × (1 − (d/D cos φ)²) |

Assumptions: outer race fixed, inner race turning with the shaft, pure
rolling (no slip). Real bearings slip slightly, so measured fault
frequencies are often 1-2% off these values. In this data, BPFI is
measured at 5.40-5.41×, 0.1-0.3% below theory (section 4).

### 2.2 Hand calculation at 1797 rpm

Bearing: n = 9, d = 7.94 mm, D = 39.04 mm, φ = 0°.

1. **Shaft frequency:** f_r = 1797 / 60 = **29.95 Hz**
2. **Geometry ratio:** d/D × cos φ = 7.94 / 39.04 × cos 0° = 0.203381 × 1 = **0.203381**
   - 1 − 0.203381 = 0.796619
   - 1 + 0.203381 = 1.203381
   - 0.203381² = 0.041364, so 1 − 0.041364 = 0.958636
3. **FTF** = 29.95 / 2 × 0.796619 = 14.975 × 0.796619 = **11.929 Hz**
4. **BPFO** = 9 × 29.95 / 2 × 0.796619 = 134.775 × 0.796619 = **107.364 Hz**
5. **BPFI** = 134.775 × 1.203381 = **162.186 Hz**
6. **BSF** = 39.04 / (2 × 7.94) × 29.95 × 0.958636 = 2.458438 × 29.95 × 0.958636 = **70.585 Hz**
7. **2 × BSF** = **141.169 Hz**

Cross-checks that follow from the formulas (both are tests):
- BPFO + BPFI = n × f_r: 107.364 + 162.186 = 269.550 = 9 × 29.95 ✓
- BPFO = n × FTF: 9 × 11.929 = 107.364 ✓

Values at all four nominal speeds are in `results/fault_frequencies.csv`.

### 2.3 Comparison with CWRU's published multipliers

| | Ours (from geometry) | CWRU published | Difference |
|---|---|---|---|
| BPFI | 5.41522 | 5.4152 | +0.00002 |
| BPFO | 3.58478 | 3.5848 | −0.00002 |
| FTF | 0.39831 | 0.3983 | +0.00001 |
| BSF (standard) | 2.35675 | none | none |
| 2 × BSF | 4.71350 | 4.7135 ("rolling element") | −0.000005 |

Every difference is smaller than CWRU's rounding to 4 decimals.

### 2.4 Finding: CWRU's "rolling element" frequency is 2 × BSF

The standard formula gives **BSF = 2.3567 × shaft speed**. CWRU's published
**4.7135** equals **2 × 2.356748 = 4.713495**, which rounds to 4.7135.

Why 2×: a defect on a ball touches the outer race and then the inner race
during each spin, so it makes **two impacts per ball revolution**. In code
and reports we write **BSF = 2.357×** and **2×BSF = 4.714×**. A test stops
anyone from "correcting" BSF to 4.7135.

---

## 3. Sampling-rate check

Source: `python -m src.check_sampling_rate`, tested in
`tests/test_sampling_rate.py`.

### 3.1 The question

CWRU's fault data is drive-end at 12 kHz. Published sources disagree on
whether the normal baseline is 12 kHz or 48 kHz (section 5). If one class
were at a different rate, a classifier could learn the recording rate
instead of the fault. That would be a leakage shortcut.

### 3.2 Method (version 2)

Every file is read as if it were 12 kHz. If a file was really recorded at
48 kHz, every frequency then comes out 4 times too low.

- **Test A:** is there a clear peak at 1× (rpm/60)?
- **Test B:** how many of the quarter orders, 0.25×, 0.5× and 0.75× shaft
  speed, show a clear peak? A real 12 kHz recording has no physical reason
  to vibrate at those fractions. A 48 kHz file read as 12 kHz does, because
  they are its true 1×, 2× and 3×.

"Clear" means the largest value within ±3% of the location is at least 10
times the median spectrum level within ±30% around it.

| Verdict | Rule |
|---|---|
| 12 kHz | clear 1× peak **and** no quarter-order peaks |
| 48 kHz | clear 0.25× peak **and** at least 2 of the 3 quarter orders |
| inconclusive | anything else; a person must look at the plot |

**Why version 1 was not enough.** Version 1 compared only two locations:
1× (expected if the file is 12 kHz) and 0.25× (where 1× would appear if
it is 48 kHz). On the normal files, both locations passed, so version 1
answered "inconclusive", as designed. The reason is that a 48 kHz file's
true **4×** harmonic lands exactly where a 12 kHz file's 1× would be. A
peak at 1× therefore proves nothing, but a peak at 0.25× has no innocent
explanation. Test B uses that asymmetry.

> **Honesty note:** test B was added *after* seeing the normal files'
> result. It is motivated by the physics above, not tuned to the data.
> It leaves every 12 kHz verdict unchanged. A synthetic test reproduces
> the 4× trap and checks that the method handles it.

### 3.3 Results

**36 fault files are 12 kHz.**
- The 1× peak scores between 13.0 and 219.
- It sits within 0.065 Hz of rpm/60.
- No quarter-order location scores above 4.9 in any of them, against a
  threshold of 10.

The weakest file is 200 (1× ratio 13.0). Its spectrum has a flat noise floor
below about 80 Hz, unlike the others, but its verdict is still clear because
it shows no quarter-order peaks.

**The 4 normal files are 48 kHz:**

| File | rpm | Peak at 0.25× (Hz) | Ratio 0.25× | Ratio 0.5× | Ratio 0.75× | After resampling |
|---|---|---|---|---|---|---|
| 97 | 1796 | 7.477 (expected 7.483) | 12.6 | 13.5 | 23.7 | 12 kHz ✓ |
| 98 | 1772* | 7.390 (expected 7.383) | 11.2 | 30.0 | 31.2 | 12 kHz ✓ |
| 99 | 1750* | 7.298 (expected 7.292) | 12.2 | 30.3 | 20.0 | 12 kHz ✓ |
| 100 | 1725 | 7.190 (expected 7.188) | 12.8 | 20.1 | 14.2 | 12 kHz ✓ |

\* nominal rpm; no RPM is stored in the file.

Two further pieces of evidence point the same way:
- **Mains hum.** In 98 and 99, the peak near the 1× position is at
  **30.0 Hz** regardless of shaft speed (expected 29.53 and 29.17 Hz). At
  48 kHz that is **120 Hz**, twice the 60 Hz US mains frequency, which
  does not depend on shaft speed.
- **Length.** At 48 kHz, files 98-100 last **10.1 s**, the same as every
  fault recording. At 12 kHz they would last 40 s.

![Spectra of all 40 files](../results/figures/sampling_rate_overview.png)

Normal file 98, read as 12 kHz. Note the peaks on the green quarter-order
lines:

![File 98 raw](../results/figures/sampling_rate/98.png)

The same file after resampling from 48 kHz to 12 kHz. The quarter-order
peaks are gone and 1× is in the right place:

![File 98 resampled](../results/figures/sampling_rate/98_resampled_to_12k.png)

### 3.4 What was done about it

- `src/config.py` records 97-100 as 48 kHz, with a comment pointing here.
  A test fails if the config and the check ever disagree.
- `load_data.load_signal()` resamples those files to 12 kHz with
  `scipy.signal.resample_poly`. This low-pass filters below 6 kHz before
  keeping every 4th sample. Keeping every 4th sample without filtering
  would fold 6-24 kHz vibration back into 0-6 kHz (aliasing).
- A test re-checks every signal that `load_signal()` hands out, and all 40
  come out 12 kHz.

### 3.5 Remaining leakage risk (decision needed)

Even after resampling, **the normal class differs from every fault class in
how it was recorded:**
- a different sampling rate, so a different anti-aliasing filter shape
  near the top of the band (5-6 kHz);
- no BA channel;
- a different file structure (97 is half length).

A classifier could use the 5-6 kHz band edge to separate "normal" from
"fault" without learning anything about bearings.

**Recommendation:** low-pass every signal at about 5 kHz before computing
features, so every class has an identical top band. Treat any very high
normal-vs-fault accuracy with suspicion.

### 3.6 Limits of this check

- The check needs visible shaft harmonics. All 40 files have them.
- A 12 kHz file with a single stray resonance at a quarter order would get
  "inconclusive", not a wrong verdict. A test covers this case.

---

## 4. Observations from looking at the spectra

### 4.1 A peak at 5.40× shaft speed is in every file, including the healthy ones

In **all 40 files** (healthy normal files included, after resampling), the
tallest raw-spectrum peak below 200 Hz is at **5.40 × shaft speed**, with
smaller neighbours at about 4.93× and 6.40×.
- 5.40× is where the inner-race fault frequency (BPFI) shows up in the
  inner-race files' envelope spectra (section 4.2, measured at
  5.40-5.41×): 0.1-0.3% below the theoretical 5.415×, which is typical
  slip.
- Because the peak is also present in healthy bearings, it is a property
  of the test rig, not a sign of a fault. Its cause is unknown.

**Consequence:** a "raw spectrum amplitude at BPFI" feature cannot tell
anything apart in this data. Physics-informed features must use the
envelope spectrum.

### 4.2 Does each file show its labelled fault? (exploratory)

> **Exploratory:** these numbers come from a one-off script with a single
> fixed band (band-pass 2-5 kHz, Hilbert envelope). It is **not in the repo
> yet**. A different band could reveal signatures this one misses, so
> "no signature found" does not mean "no fault".

Each number is the envelope-spectrum peak-to-background ratio at the
labelled fault frequency (±2%), using the same "10 or more = clear" rule as
section 3.

| Group | Envelope result | Matches label? |
|---|---|---|
| Normal (97-100) | no fault-frequency peaks (ratios 2-5); strongest components at 4× and 8× shaft speed | ✓ no fault seen |
| Inner race 0.007 (105-108) | BPFI 212-264 | ✓ clear |
| Inner race 0.014 (169-172) | BPFI 73-115 | ✓ clear |
| Inner race 0.021 (209-212) | BPFI 136-171 | ✓ clear |
| Outer race 0.007 (130-133) | BPFO 549-753 | ✓ very clear |
| Outer race 0.014 (197-200) | **BPFO 3-8** | ✗ **no BPFO signature** |
| Outer race 0.021 (234-237) | BPFO 89-99 | ✓ clear |
| Ball 0.007 (118-121) | BSF 4-10, 2×BSF 4-6; weak mixed peaks near BPFO and BPFI (4-23) | ✗ no ball signature |
| Ball 0.014 (185-188) | all fault frequencies ≤ 4; strongest components at 0.39-0.40× (= FTF, the cage speed) and 0.61×, 1.19× | ~ indirect only: cage-rate modulation is typical of ball faults, but no BSF line |
| Ball 0.021 (222-225) | BPFI 15-23 with peaks at 5.41×, 4.41×, 3.40× (BPFI and its shaft-speed sidebands); 2×BSF 3-6 | ✗ **looks like an inner-race fault** |

**Summary:**
- **24 of 40 files clearly show what their label says**: all 4 normal, all
  12 inner-race, and 8 of the 12 outer-race files.
- **The 12 ball files and the 4 outer-race 0.014 in files do not.**

This fits what the literature reports: ball faults are by far the hardest
CWRU faults to diagnose, and several ball and 0.014 in outer-race defects
are hard to find with envelope analysis (section 5).

**Consequences for the project:**
- Expect physics-informed features to work for inner race and outer race
  0.007/0.021, and to struggle on ball and outer race 0.014. Under honest
  splits that is a genuine result about the data, not a bug.
- If a model scores near 100% on ball files, check whether it learned
  something that is not ball-fault physics. Recognising the recording
  itself is the obvious candidate, which is exactly the leakage this
  project sets out to show.

---

## 5. Related sources

- Smith, W.A. and Randall, R.B. (2015), *Rolling element bearing diagnostics
  using the Case Western Reserve University data: a benchmark study*,
  Mechanical Systems and Signal Processing 64-65, 100-131,
  doi:10.1016/j.ymssp.2015.04.021.
  ([ResearchGate](https://www.researchgate.net/publication/276248554_Rolling_Element_Bearing_Diagnostics_Using_the_Case_Western_Reserve_University_Data_A_Benchmark_Study))
  - **Not yet read in full.** The statements here come from search
    summaries: ball faults were "by far the most difficult to diagnose";
    BSF is hard to separate from 2× shaft speed; impulsive events from
    mechanical looseness affected results more than fault size.
  - The claim that many ball and 0.014 in outer-race defects are hard to
    find with envelope analysis comes from a secondary write-up
    ([zenn.dev](https://zenn.dev/logicia32/articles/2026-07-09-bearing-envelope-leak?locale=en))
    and has not been checked against the paper.
- The 98/99 duplicate is reported independently in
  [srigas/CWRU_Bearing_NumPy](https://github.com/srigas/CWRU_Bearing_NumPy).
- Sources disagree on the normal files' rate. For example,
  [arXiv:2412.01322](https://arxiv.org/pdf/2412.01322) lists them as
  48 kHz, while others treat them as 12 kHz. Section 3 settles it from the
  data.

---

## 6. Open items

| Item | Status |
|---|---|
| Normal files 12 vs 48 kHz | **resolved: 48 kHz**, resampled to 12 kHz |
| Duplicate normal file | **resolved**: copy of 98 inside 99.mat, reported and not used |
| Envelope label check as a tested script | exploratory only; next step |
| Band choice for the envelope check (fixed 2-5 kHz vs data-driven) | to decide with the script |
| Low-pass all signals at about 5 kHz to remove the 48 kHz band-edge difference | owner decision (section 3.5) |
| Cause of the rig-wide 5.40× raw-spectrum peak | unexplained |
| Read Smith & Randall (2015) in full | to do |
