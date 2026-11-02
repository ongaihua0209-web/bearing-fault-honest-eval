"""
config.py - every fact the project relies on, written down in ONE place.

Think of this file as the test-rig data sheet. Nothing here is calculated
from the data; it is what CWRU and the bearing maker tell us. Every other
script reads its numbers from here, so if a fact changes it only has to be
changed once.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Folders. Paths are worked out from where this file lives, so the scripts
# work no matter which folder you run them from.
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = REPO_ROOT / "data" / "raw"
RESULTS_DIR = REPO_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures"

# ---------------------------------------------------------------------------
# Sampling rate.
# CWRU says the drive-end fault data was recorded at 12,000 samples per
# second. Sources disagree about the normal (healthy) files, so we START by
# assuming 12 kHz for everything and then check it with
# src/check_sampling_rate.py.
#
# If that check proves a file was really recorded at 48 kHz, add it to
# RECORDED_SAMPLING_RATE_OVERRIDES below, e.g. {97: 48000}, with a comment
# pointing at the evidence. load_data.load_signal() will then resample it to
# 12 kHz automatically. A test fails if this table and the check disagree.
# ---------------------------------------------------------------------------
ASSUMED_SAMPLING_RATE_HZ = 12_000
TARGET_SAMPLING_RATE_HZ = 12_000

# The four normal (healthy) files were recorded at 48 kHz, not 12 kHz.
# Evidence (docs/VALIDATION.md, section 3): read as 12 kHz, each shows clear
# peaks at 0.25x, 0.5x and 0.75x shaft speed (= its true 1x, 2x, 3x), which
# no 12 kHz file shows; and at 48 kHz files 98-100 last 10.1 s, the same as
# every fault recording. load_data.load_signal() resamples them to 12 kHz.
RECORDED_SAMPLING_RATE_OVERRIDES = {97: 48_000, 98: 48_000, 99: 48_000, 100: 48_000}

# ---------------------------------------------------------------------------
# Low-pass filter applied to EVERY signal by load_data.load_signal().
#
# Why: the normal files (recorded at 48 kHz, resampled) and the fault files
# (recorded at 12 kHz) went through different anti-aliasing filters. Measured
# with src/check_band_edge.py, the two recording chains agree below about
# 5.2 kHz and differ above it. Removing everything above 5.2 kHz makes the
# top of the band identical for every class, so a model cannot tell the
# classes apart by HOW they were recorded. See docs/VALIDATION.md 3.5.
#
# The spec: below 4.8 kHz the signal passes unchanged; above 5.2 kHz it is
# reduced at least 60 dB (1000x in amplitude). The -6 dB point is 5.0 kHz.
# ---------------------------------------------------------------------------
LOWPASS_PASSBAND_EDGE_HZ = 4_800
LOWPASS_STOPBAND_EDGE_HZ = 5_200
LOWPASS_STOPBAND_ATTENUATION_DB = 60

# ---------------------------------------------------------------------------
# Motor load (horsepower) -> nominal shaft speed (rpm).
# Used only when a file does not store its own measured RPM.
# ---------------------------------------------------------------------------
NOMINAL_RPM = {0: 1797, 1: 1772, 2: 1750, 3: 1730}

# ---------------------------------------------------------------------------
# Drive-end bearing: SKF 6205-2RS JEM deep-groove ball bearing.
# ---------------------------------------------------------------------------
N_BALLS = 9
BALL_DIAMETER_MM = 7.94
PITCH_DIAMETER_MM = 39.04
CONTACT_ANGLE_DEG = 0.0

# CWRU's published fault-frequency multipliers (multiply by shaft speed in Hz),
# copied from https://engineering.case.edu/bearingdatacenter/bearing-information
# (checked 2026-11-02). We do NOT use these in calculations - we calculate our
# own from the geometry above and use these only to check our maths.
# Note: CWRU's FTF (0.39828) is slightly inconsistent with their own BPFO:
# FTF should equal BPFO / 9 = 0.39831. The 0.008% gap is negligible.
CWRU_PUBLISHED_MULTIPLIERS = {
    "BPFI": 5.4152,
    "BPFO": 3.5848,
    "FTF": 0.39828,
    "rolling_element": 4.7135,
}

# Fan-end bearing (SKF 6203-2RS JEM), same source. We do not analyse fan-end
# data, but its inner-race frequency shows up in every drive-end recording
# (docs/VALIDATION.md 4.1), so we need it to recognise that peak.
FAN_END_CWRU_MULTIPLIERS = {
    "BPFI": 4.9469,
    "BPFO": 3.0530,
    "FTF": 0.3817,
    "rolling_element": 3.9874,
}

# What we read on CWRU's official website (2026-11-02): every file's official
# name, size in bytes and download address. Used by tests to check that our
# labels and files match the official ones - without going online.
OFFICIAL_REFERENCE_CSV = REPO_ROOT / "data" / "cwru_official_reference.csv"

# ---------------------------------------------------------------------------
# The 40 files we expect, named by CWRU file number.
# Each group lists four files, for 0, 1, 2 and 3 HP motor load in that order.
# fault_size_in is the fault diameter in inches (0.0 means no fault).
# All outer-race faults in this set are at the 6 o'clock position. CWRU's
# website contradicts itself about where that is: its data table says the
# load zone is centred at 6:00, its procedures page calls 6:00 "orthogonal to
# the load zone" (docs/VALIDATION.md 1.3). The file labels are unaffected.
#
# These are CWRU's labels, kept exactly as published (owner decision,
# 2026-11-02) - even for the 14 files where src/check_fault_signatures.py
# does not find the labelled fault. See docs/VALIDATION.md 4.2-4.3.
# ---------------------------------------------------------------------------
FILE_GROUPS = [
    # (fault_location, fault_size_in, [files for 0 HP, 1 HP, 2 HP, 3 HP])
    ("normal",     0.000, [97, 98, 99, 100]),
    ("inner_race", 0.007, [105, 106, 107, 108]),
    ("inner_race", 0.014, [169, 170, 171, 172]),
    ("inner_race", 0.021, [209, 210, 211, 212]),
    ("ball",       0.007, [118, 119, 120, 121]),
    ("ball",       0.014, [185, 186, 187, 188]),
    ("ball",       0.021, [222, 223, 224, 225]),
    ("outer_race", 0.007, [130, 131, 132, 133]),
    ("outer_race", 0.014, [197, 198, 199, 200]),
    ("outer_race", 0.021, [234, 235, 236, 237]),
]


def cwru_name(fault_location, fault_size_in, load_hp):
    """
    The name CWRU's website uses for a file, e.g. ("inner_race", 0.007, 0)
    -> "IR007_0", ("outer_race", 0.021, 3) -> "OR021@6_3", ("normal", 0, 1)
    -> "Normal_1". Handy for cross-checking with the official tables.
    """
    size = f"{round(fault_size_in * 1000):03d}"          # 0.007 -> "007"
    prefix = {"normal": "Normal", "inner_race": f"IR{size}",
              "ball": f"B{size}", "outer_race": f"OR{size}@6"}[fault_location]
    return f"{prefix}_{load_hp}"


def expected_files():
    """
    Turn FILE_GROUPS into one row per file.

    Returns a list of dictionaries like:
      {"file_number": 105, "cwru_name": "IR007_0", "fault_location":
       "inner_race", "fault_size_in": 0.007, "load_hp": 0}
    """
    rows = []
    for fault_location, fault_size_in, file_numbers in FILE_GROUPS:
        # enumerate gives 0, 1, 2, 3 - which is exactly the load in HP
        for load_hp, file_number in enumerate(file_numbers):
            rows.append({
                "file_number": file_number,
                "cwru_name": cwru_name(fault_location, fault_size_in, load_hp),
                "fault_location": fault_location,
                "fault_size_in": fault_size_in,
                "load_hp": load_hp,
            })
    return rows
