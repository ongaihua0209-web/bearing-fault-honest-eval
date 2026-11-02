"""
features.py - turn each window into a handful of numbers ("features").

Feature set F1: seven generic statistics that any vibration engineer would
recognise. They describe the size and shape of the signal, but know nothing
about bearing geometry or fault frequencies. (Name clash warning: "F1" here
is the name of this FEATURE SET; "macro-F1" elsewhere is a SCORE.)

    rms           root mean square - the overall vibration level
    peak          largest absolute value - the biggest single swing
    peak_to_peak  highest minus lowest value
    crest_factor  peak / rms - how "spiky" relative to the overall level
    kurtosis      impulsiveness; 3 for random noise, higher for impacts
                  (the engineering convention, not the "excess" one)
    skewness      lopsidedness: are positive and negative swings alike?
    std           standard deviation - like rms, but ignores any steady offset

All windows come from load_signal(), so they contain only 0-5.2 kHz, the
range where the normal and fault recordings were captured alike
(docs/VALIDATION.md 3.5).
"""

import numpy as np
import pandas as pd
import scipy.stats

FEATURE_NAMES_F1 = ["rms", "peak", "peak_to_peak", "crest_factor",
                    "kurtosis", "skewness", "std"]


def features_f1(windows):
    """
    Feature set F1 for many windows at once.

    windows: 2-D array, one row per window.
    Returns a table with one row per window and one column per feature.
    """
    x = np.atleast_2d(np.asarray(windows, dtype=float))
    rms = np.sqrt(np.mean(x ** 2, axis=1))
    peak = np.max(np.abs(x), axis=1)
    return pd.DataFrame({
        "rms": rms,
        "peak": peak,
        "peak_to_peak": x.max(axis=1) - x.min(axis=1),
        "crest_factor": peak / rms,
        "kurtosis": scipy.stats.kurtosis(x, axis=1, fisher=False),
        "skewness": scipy.stats.skew(x, axis=1),
        "std": x.std(axis=1),
    }, columns=FEATURE_NAMES_F1)
