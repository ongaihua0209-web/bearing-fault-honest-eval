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

# No overrides yet: all files checked so far are confirmed 12 kHz
# (see docs/VALIDATION.md). The normal files 97-100 have not been checked
# because they are not in data/raw/ yet.
RECORDED_SAMPLING_RATE_OVERRIDES = {}

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

# CWRU's published fault-frequency multipliers (multiply by shaft speed in Hz).
# We do NOT use these in calculations - we calculate our own from the
# geometry above and use these only to check our maths (see tests/).
CWRU_PUBLISHED_MULTIPLIERS = {
    "BPFI": 5.4152,
    "BPFO": 3.5848,
    "FTF": 0.3983,
    "rolling_element": 4.7135,
}

# ---------------------------------------------------------------------------
# The 40 files we expect, named by CWRU file number.
# Each group lists four files, for 0, 1, 2 and 3 HP motor load in that order.
# fault_size_in is the fault diameter in inches (0.0 means no fault).
# All outer-race faults in this set are at the 6 o'clock position (the
# centre of the load zone).
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


def expected_files():
    """
    Turn FILE_GROUPS into one row per file.

    Returns a list of dictionaries like:
      {"file_number": 105, "fault_location": "inner_race",
       "fault_size_in": 0.007, "load_hp": 0}
    """
    rows = []
    for fault_location, fault_size_in, file_numbers in FILE_GROUPS:
        # enumerate gives 0, 1, 2, 3 - which is exactly the load in HP
        for load_hp, file_number in enumerate(file_numbers):
            rows.append({
                "file_number": file_number,
                "fault_location": fault_location,
                "fault_size_in": fault_size_in,
                "load_hp": load_hp,
            })
    return rows
