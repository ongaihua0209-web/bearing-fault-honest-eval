"""
load_data.py - read the raw CWRU files, check them, and write a manifest.

What it does, step by step:
  1. For each of the 40 files we expect (listed in config.py), look for
     data/raw/<number>.mat. Missing files are reported, not ignored.
  2. Open each file and pick out the drive-end (DE) accelerometer signal and
     the shaft speed (RPM). If the file has no stored RPM, use the nominal
     speed for that motor load.
  3. Check for duplicate signals: two files containing exactly the same
     numbers. One CWRU normal file reportedly contains a copy of another.
     Exact duplicates are reported and excluded.
  4. Save results/manifest.csv (one row per expected file) and
     results/data_quality_report.txt (everything unusual we found).

Run it from the repository folder:
    python -m src.load_data

Other scripts should get signals through load_signal() at the bottom of this
file, so every signal arrives at the same 12 kHz sampling rate.
"""

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.io
import scipy.signal

from src import config

# How many opening samples to compare when looking for partial copies.
N_SAMPLES_FOR_SHARED_START = 1000

# Flag a stored RPM that differs from nominal by at least this many rpm.
RPM_DIFFERENCE_TO_NOTE = 5


# ---------------------------------------------------------------------------
# Small building blocks
# ---------------------------------------------------------------------------

def mat_path(file_number, raw_dir=config.RAW_DATA_DIR):
    """Where file number N should be: data/raw/N.mat"""
    return Path(raw_dir) / f"{file_number}.mat"


def read_mat(path):
    """
    Read a MATLAB .mat file into a dictionary: variable name -> numbers.
    MATLAB adds housekeeping entries whose names start with "__"; we drop them.
    """
    contents = scipy.io.loadmat(path)
    return {name: value for name, value in contents.items()
            if not name.startswith("__")}


def pick_de_variable(variables, file_number):
    """
    Decide which variable holds the drive-end signal.

    CWRU names variables after the file, e.g. 105.mat holds "X105_DE_time".
    Rules:
      1. If the variable named after this file exists, use it.
      2. Otherwise, if there is exactly one DE variable, use it and add a note.
      3. Otherwise (none at all, or several and none match), give up on the
         file by raising an error - guessing could silently mislabel data.

    Returns (chosen_variable_name, list_of_notes).
    """
    expected_name = f"X{file_number:03d}_DE_time"
    de_variables = sorted(name for name in variables if name.endswith("_DE_time"))
    notes = []

    if expected_name in de_variables:
        chosen = expected_name
    elif len(de_variables) == 1:
        chosen = de_variables[0]
        notes.append(f"DE variable is named {chosen}, expected {expected_name}")
    elif len(de_variables) == 0:
        raise ValueError("no drive-end (_DE_time) variable in file")
    else:
        raise ValueError(f"several DE variables and none is {expected_name}: "
                         f"{de_variables}")

    others = [name for name in de_variables if name != chosen]
    if others:
        notes.append("file also contains " + ", ".join(others))
    return chosen, notes


def pick_rpm(variables, de_variable, load_hp):
    """
    Find the shaft speed that belongs to the chosen signal.

    The RPM is stored next to the signal with the same prefix:
    "X105_DE_time" goes with "X105RPM". If it is not there, fall back to the
    nominal speed for this motor load.

    Returns (rpm, source) where source is "stored" or "nominal".
    """
    prefix = de_variable.split("_")[0]          # "X105_DE_time" -> "X105"
    rpm_name = prefix + "RPM"
    if rpm_name in variables:
        values = np.asarray(variables[rpm_name], dtype=float).ravel()
        if values.size > 0 and values[0] > 0:
            return float(values[0]), "stored"
    return float(config.NOMINAL_RPM[load_hp]), "nominal"


def recorded_sampling_rate(file_number):
    """
    The rate the file was RECORDED at. 12 kHz unless the sampling-rate check
    proved otherwise and the file was added to the overrides in config.py.
    """
    return config.RECORDED_SAMPLING_RATE_OVERRIDES.get(
        file_number, config.ASSUMED_SAMPLING_RATE_HZ)


def fingerprint(signal):
    """
    A 64-character code computed from every number in the signal (a SHA-256
    hash). Two signals get the same code only if they are identical
    sample-for-sample, so comparing codes is a fast way to find copies.
    """
    data = np.ascontiguousarray(signal, dtype=np.float64)
    return hashlib.sha256(data.tobytes()).hexdigest()


def resample_to_target(signal, from_hz, to_hz=config.TARGET_SAMPLING_RATE_HZ):
    """
    Change a signal's sampling rate, e.g. 48 kHz -> 12 kHz.

    We use scipy's resample_poly rather than simply keeping every 4th sample.
    It first removes content above the new Nyquist limit (6 kHz) with a
    low-pass filter. Without that step, vibration between 6 and 24 kHz would
    "fold back" (alias) into 0-6 kHz and corrupt the spectrum.
    """
    if from_hz == to_hz:
        return np.asarray(signal, dtype=float)
    divisor = math.gcd(int(from_hz), int(to_hz))
    up = int(to_hz) // divisor
    down = int(from_hz) // divisor
    return scipy.signal.resample_poly(signal, up, down)


def lowpass_filter_taps(fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Design the low-pass filter described in config.py.

    The filter is a weighted moving average (an "FIR filter"): each output
    sample is a weighted sum of nearby input samples. scipy's kaiserord
    works out how many weights are needed to meet the spec (flat below
    4.8 kHz, at least 60 dB down above 5.2 kHz), and firwin calculates them.
    The result is about 100 weights.
    """
    pass_edge = config.LOWPASS_PASSBAND_EDGE_HZ
    stop_edge = config.LOWPASS_STOPBAND_EDGE_HZ
    width = (stop_edge - pass_edge) / (fs / 2)     # as a fraction of Nyquist
    n_taps, beta = scipy.signal.kaiserord(config.LOWPASS_STOPBAND_ATTENUATION_DB, width)
    n_taps += 1 - n_taps % 2       # make it odd, so the filter is symmetric
    cutoff = (pass_edge + stop_edge) / 2
    return scipy.signal.firwin(n_taps, cutoff, window=("kaiser", beta), fs=fs)


def lowpass(signal, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Remove everything above about 5 kHz (see config.py for why).

    filtfilt runs the filter forwards and then backwards. That cancels the
    filter's time delay, so impacts stay exactly where they were, and it
    doubles the attenuation (at least 120 dB above 5.2 kHz).
    """
    return scipy.signal.filtfilt(lowpass_filter_taps(fs), [1.0], signal)


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def find_duplicates(all_signals):
    """
    Look for copies among signals.

    all_signals: list of (file_number, variable_name, signal) - every DE
                 variable found in every file, not just the ones we use.

    Returns:
      exact_groups: list of groups; each group is a list of
                    (file_number, variable_name) whose signals are identical.
      shared_starts: list of groups whose first N_SAMPLES_FOR_SHARED_START
                     samples are identical although the full signals are
                     not (a possible partial copy - reported, not excluded).
    """
    by_full = {}
    by_start = {}
    for file_number, name, signal in all_signals:
        by_full.setdefault(fingerprint(signal), []).append((file_number, name))
        start = signal[:N_SAMPLES_FOR_SHARED_START]
        by_start.setdefault(fingerprint(start), []).append(
            (file_number, name, fingerprint(signal)))

    exact_groups = [group for group in by_full.values() if len(group) > 1]

    shared_starts = []
    for group in by_start.values():
        distinct_full_signals = {full for _, _, full in group}
        if len(distinct_full_signals) > 1:      # same start, different whole
            shared_starts.append([(f, n) for f, n, _ in group])
    return exact_groups, shared_starts


def choose_exclusions(used_fingerprints, labels):
    """
    Decide which files to drop because their signal is a copy of another
    file's signal.

    used_fingerprints: {file_number: fingerprint of the signal we would use}
    labels:            {file_number: (fault_location, fault_size_in)}

    Rule:
      - Copies with the SAME fault label: keep the lowest file number,
        exclude the rest (one copy is real data; the others add nothing).
      - Copies with DIFFERENT fault labels: exclude all of them, because at
        least one label must be wrong and we cannot tell which.

    Returns {file_number: reason}.
    """
    groups = {}
    for file_number, code in used_fingerprints.items():
        groups.setdefault(code, []).append(file_number)

    excluded = {}
    for files in groups.values():
        if len(files) < 2:
            continue
        files = sorted(files)
        if len({labels[f] for f in files}) == 1:
            keep = files[0]
            for f in files[1:]:
                excluded[f] = f"exact copy of file {keep}'s DE signal"
        else:
            for f in files:
                others = [o for o in files if o != f]
                excluded[f] = (f"exact copy of files {others} which carry a "
                               f"different fault label")
    return excluded


# ---------------------------------------------------------------------------
# The main job: build the manifest
# ---------------------------------------------------------------------------

def build_manifest(raw_dir=config.RAW_DATA_DIR):
    """
    Go through every expected file and collect its facts.

    Returns (manifest, findings):
      manifest: pandas DataFrame, one row per EXPECTED file (40 rows), with a
                'status' column: ok, missing, unreadable or excluded_duplicate.
      findings: dictionary of everything unusual, used for the report.
    """
    expected = config.expected_files()
    labels = {r["file_number"]: (r["fault_location"], r["fault_size_in"])
              for r in expected}

    rows = []
    all_de_signals = []        # every DE variable in every file
    used_fingerprints = {}     # the one signal we actually use per file

    for info in expected:
        number = info["file_number"]
        row = dict(info, rpm=np.nan, rpm_source="", sampling_rate_hz=np.nan,
                   n_samples=np.nan, duration_s=np.nan, status="",
                   de_variable="", notes="")
        path = mat_path(number, raw_dir)

        if not path.exists():
            row["status"] = "missing"
            rows.append(row)
            continue

        try:
            variables = read_mat(path)
            de_variable, notes = pick_de_variable(variables, number)
        except Exception as error:      # broken file or no usable signal
            row["status"] = "unreadable"
            row["notes"] = str(error)
            rows.append(row)
            continue

        # Keep every DE variable for the duplicate check.
        for name in variables:
            if name.endswith("_DE_time"):
                all_de_signals.append(
                    (number, name, np.asarray(variables[name], dtype=float).ravel()))

        signal = np.asarray(variables[de_variable], dtype=float).ravel()
        used_fingerprints[number] = fingerprint(signal)

        n_bad = int(np.sum(~np.isfinite(signal)))
        if n_bad:
            notes.append(f"{n_bad} NaN/infinite samples")

        rpm, rpm_source = pick_rpm(variables, de_variable, info["load_hp"])
        nominal = config.NOMINAL_RPM[info["load_hp"]]
        if rpm_source == "stored" and abs(rpm - nominal) >= RPM_DIFFERENCE_TO_NOTE:
            notes.append(f"stored rpm {rpm:.0f} differs from nominal {nominal} "
                         f"by {rpm - nominal:+.0f}")

        fs = recorded_sampling_rate(number)
        row.update(rpm=rpm, rpm_source=rpm_source, sampling_rate_hz=fs,
                   n_samples=signal.size, duration_s=round(signal.size / fs, 3),
                   status="ok", de_variable=de_variable, notes="; ".join(notes))
        rows.append(row)

    manifest = pd.DataFrame(rows)

    # Duplicates: report everything, exclude only exact copies of used signals.
    exact_groups, shared_starts = find_duplicates(all_de_signals)
    excluded = choose_exclusions(used_fingerprints, labels)
    for number, reason in excluded.items():
        i = manifest.index[manifest["file_number"] == number][0]
        manifest.loc[i, "status"] = "excluded_duplicate"
        old = manifest.loc[i, "notes"]
        manifest.loc[i, "notes"] = f"{old}; {reason}" if old else reason

    # Files in data/raw that we did not expect (typo in a name, extra data...)
    expected_names = {f"{r['file_number']}.mat" for r in expected}
    unexpected = sorted(p.name for p in Path(raw_dir).glob("*.mat")
                        if p.name not in expected_names)

    # Whole numbers should look like whole numbers in the CSV.
    for column in ("rpm", "sampling_rate_hz", "n_samples"):
        manifest[column] = manifest[column].round().astype("Int64")

    findings = {
        "exact_duplicate_groups": exact_groups,
        "shared_start_groups": shared_starts,
        "excluded": excluded,
        "unexpected_files": unexpected,
    }
    return manifest, findings


def write_report(manifest, findings, path):
    """Write a plain-text summary of everything unusual we found."""
    lines = ["CWRU data quality report (written by src/load_data.py)", ""]

    counts = manifest["status"].value_counts()
    lines.append(f"Expected files: {len(manifest)}")
    for status in ("ok", "missing", "unreadable", "excluded_duplicate"):
        lines.append(f"  {status:20s} {int(counts.get(status, 0))}")
    lines.append("")

    missing = manifest.loc[manifest["status"] == "missing"]
    lines.append(f"Missing files ({len(missing)}):")
    for (location, size), group in missing.groupby(
            ["fault_location", "fault_size_in"], sort=False):
        numbers = ", ".join(str(n) for n in group["file_number"])
        lines.append(f"  {location:11s} {size:.3f} in: {numbers}")
    if missing.empty:
        lines.append("  none")
    lines.append("")

    lines.append("Exact duplicate signals (identical sample-for-sample):")
    for group in findings["exact_duplicate_groups"]:
        lines.append("  " + " == ".join(f"{f}.mat:{n}" for f, n in group))
    if not findings["exact_duplicate_groups"]:
        lines.append(f"  none among the {int(counts.get('ok', 0) + counts.get('excluded_duplicate', 0))} files present")
    lines.append("")

    lines.append(f"Signals sharing their first {N_SAMPLES_FOR_SHARED_START} "
                 "samples but not identical overall (possible partial copies):")
    for group in findings["shared_start_groups"]:
        lines.append("  " + ", ".join(f"{f}.mat:{n}" for f, n in group))
    if not findings["shared_start_groups"]:
        lines.append("  none")
    lines.append("")

    lines.append("Excluded files:")
    for number, reason in sorted(findings["excluded"].items()):
        lines.append(f"  {number}: {reason}")
    if not findings["excluded"]:
        lines.append("  none")
    lines.append("")

    lines.append("Files in data/raw/ that are not in the expected list:")
    lines.extend(f"  {name}" for name in findings["unexpected_files"])
    if not findings["unexpected_files"]:
        lines.append("  none")
    lines.append("")

    noted = manifest.loc[manifest["notes"] != ""]
    lines.append("Per-file notes:")
    for _, row in noted.iterrows():
        lines.append(f"  {row['file_number']}: {row['notes']}")
    if noted.empty:
        lines.append("  none")

    Path(path).write_text("\n".join(lines) + "\n")
    return lines


# ---------------------------------------------------------------------------
# The one function other scripts should use to get a signal
# ---------------------------------------------------------------------------

def load_raw_signal(file_number, raw_dir=config.RAW_DATA_DIR):
    """
    Load one file's drive-end signal exactly as stored (no resampling).
    Used by the sampling-rate check, which must see the raw data.

    Returns (signal, rpm).
    """
    info = next(r for r in config.expected_files() if r["file_number"] == file_number)
    variables = read_mat(mat_path(file_number, raw_dir))
    de_variable, _ = pick_de_variable(variables, file_number)
    signal = np.asarray(variables[de_variable], dtype=float).ravel()
    rpm, _ = pick_rpm(variables, de_variable, info["load_hp"])
    return signal, rpm


def load_signal(file_number, raw_dir=config.RAW_DATA_DIR):
    """
    Load one file's drive-end signal, ready for the rest of the project.

    Every signal comes out the same way, whatever class it belongs to:
      1. at 12 kHz - files recorded at 48 kHz (per config.py) are resampled;
      2. low-pass filtered at 5 kHz - so no class can be recognised from
         its recording equipment's behaviour near the top of the band.

    Returns (signal, rpm, sampling_rate_hz).
    """
    signal, rpm = load_raw_signal(file_number, raw_dir)
    recorded_hz = recorded_sampling_rate(file_number)
    signal = resample_to_target(signal, recorded_hz, config.TARGET_SAMPLING_RATE_HZ)
    signal = lowpass(signal, config.TARGET_SAMPLING_RATE_HZ)
    return signal, rpm, config.TARGET_SAMPLING_RATE_HZ


def main():
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    manifest, findings = build_manifest()

    manifest_path = config.RESULTS_DIR / "manifest.csv"
    report_path = config.RESULTS_DIR / "data_quality_report.txt"
    manifest.to_csv(manifest_path, index=False)
    lines = write_report(manifest, findings, report_path)

    print("\n".join(lines))
    print(f"\nSaved {manifest_path.relative_to(config.REPO_ROOT)}")
    print(f"Saved {report_path.relative_to(config.REPO_ROOT)}")


if __name__ == "__main__":
    main()
