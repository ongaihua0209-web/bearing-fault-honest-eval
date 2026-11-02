"""
segment.py - cut every recording into short windows for machine learning.

A classifier needs many examples to learn from, but CWRU has only 40
recordings. The usual approach - and the one we copy, so that we can show
its pitfalls - is to cut each 10-second recording into many short windows
and treat each window as one example.

Choices (see config.py):
  - window length 2048 samples = 0.17 s at 12 kHz;
  - windows do NOT overlap: each sample belongs to exactly one window.
    (Overlapping windows would share samples, so a random split could put
    literally the same data on both sides - an even worse leak.)
  - the few samples left at the end of a recording (fewer than 2048) are
    dropped.

Every window keeps the facts of the recording it came from (file number,
fault location, fault size, load), so the splits can later decide which
windows are allowed into training and which into testing.

Signals come from load_data.load_signal(), so every window is at 12 kHz
and low-pass filtered at 5 kHz, whatever class it belongs to.

Run it to see how many windows each recording gives:
    python -m src.segment
"""

import numpy as np
import pandas as pd

from src import config, load_data


def cut_into_windows(signal, length=config.WINDOW_LENGTH_SAMPLES):
    """
    Cut one signal into back-to-back windows of `length` samples.
    Returns a 2-D array: one row per window.
    """
    n_windows = len(signal) // length            # whole windows only
    return np.asarray(signal[:n_windows * length]).reshape(n_windows, length)


def make_windows(raw_dir=config.RAW_DATA_DIR):
    """
    Cut every available recording into windows.

    Returns (windows, meta):
      windows: array with one row per window (n_windows x 2048)
      meta:    table with one row per window, in the same order, saying
               where it came from (file_number, cwru_name, fault_location,
               fault_size_in, load_hp, rpm, window_in_file).
    """
    all_windows, rows = [], []
    for info in config.expected_files():
        number = info["file_number"]
        if not load_data.mat_path(number, raw_dir).exists():
            continue
        signal, rpm, _ = load_data.load_signal(number, raw_dir)
        windows = cut_into_windows(signal)
        all_windows.append(windows)
        for i in range(len(windows)):
            rows.append({**info, "rpm": rpm, "window_in_file": i})

    meta = pd.DataFrame(rows)
    return np.vstack(all_windows), meta


def main():
    windows, meta = make_windows()
    print(f"{len(windows)} windows of {windows.shape[1]} samples "
          f"({windows.shape[1] / config.TARGET_SAMPLING_RATE_HZ:.3f} s each)\n")
    print("Windows per class:")
    print(meta["fault_location"].value_counts().to_string())
    print("\nWindows per recording (min / max):",
          meta.groupby("file_number").size().min(), "/",
          meta.groupby("file_number").size().max())


if __name__ == "__main__":
    main()
