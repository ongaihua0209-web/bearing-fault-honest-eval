"""
features.py - turn each window into a handful of numbers ("features").

Three feature sets (plus one combination). Name clash warning: "F1" is the
name of a FEATURE SET here; "macro-F1" elsewhere is a SCORE.

F1  generic statistics (7 numbers) - size and shape of the signal, nothing
    about bearings:
      rms, peak, peak_to_peak, crest_factor, kurtosis (engineering
      convention: 3 for random noise), skewness, std

F2  spectral band energies (16 numbers) - how the vibration energy is
    spread over frequency, in 16 equal bands of 300 Hz from 0 to 4.8 kHz.
    Still nothing about bearings.
    Why 0-4.8 kHz and not 0-6 kHz: above 4.8 kHz the healthy recordings
    still differ from the faulty ones because they were recorded on
    different equipment settings (docs/VALIDATION.md 3.5). The project rule
    is that features use 0-4.8 kHz only.

F3  physics-informed (9 numbers) - envelope analysis, the way a bearing
    specialist looks for a fault:
      1. band-pass filter in the band where impacts ring most clearly;
      2. take the envelope (Hilbert transform);
      3. take the envelope's spectrum;
      4. measure the peak at 1x, 2x and 3x of BPFO, BPFI and 2xBSF,
         calculated from that recording's own RPM, within a small
         tolerance (1% or one frequency bin, whichever is wider);
      5. divide by the median level of the envelope spectrum between 10
         and 600 Hz, and take log10 (the ratios span 1 to 1000).
    The band is chosen FROM TRAINING DATA ONLY: for each candidate band
    (nine 1.2 kHz bands from 0.4 to 4.8 kHz) we compute the kurtosis
    (spikiness) of every TRAINING window after band-pass filtering, and
    pick the band with the highest median kurtosis. The test windows are
    then filtered in that same band. No labels are used.
    F3 uses 8192-sample windows (config.py explains why).

F1+F3  both sets side by side (16 numbers), on the same 8192-sample windows.

All windows come from load_signal(), so they contain only 0-5.2 kHz, the
range where the normal and fault recordings were captured alike.
"""

import numpy as np
import pandas as pd
import scipy.stats

from src import bearing_physics, config
from src.check_fault_signatures import bandpass, candidate_bands, envelope_spectrum

FS = config.TARGET_SAMPLING_RATE_HZ

# ---------------------------------------------------------------------------
# F1: generic statistics
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# F2: energy in 16 equal frequency bands, 0-4.8 kHz
# ---------------------------------------------------------------------------

F2_N_BANDS = 16
F2_MAX_HZ = config.LOWPASS_PASSBAND_EDGE_HZ                       # 4800
F2_EDGES_HZ = np.linspace(0, F2_MAX_HZ, F2_N_BANDS + 1)           # 0, 300, ... 4800
FEATURE_NAMES_F2 = [f"band_{int(lo):04d}_{int(hi):04d}hz"
                    for lo, hi in zip(F2_EDGES_HZ[:-1], F2_EDGES_HZ[1:])]


def features_f2(windows, fs=FS):
    """
    Feature set F2: log10 of the vibration energy in each 300 Hz band.

    The spectrum is taken with a Hann window (which tapers the ends of the
    window so they do not smear energy across bands). log10 because band
    energies range over many orders of magnitude.
    """
    x = np.atleast_2d(np.asarray(windows, dtype=float))
    x = x - x.mean(axis=1, keepdims=True)
    power = np.abs(np.fft.rfft(x * np.hanning(x.shape[1]), axis=1)) ** 2
    freqs = np.fft.rfftfreq(x.shape[1], d=1.0 / fs)
    columns = {}
    for name, lo, hi in zip(FEATURE_NAMES_F2, F2_EDGES_HZ[:-1], F2_EDGES_HZ[1:]):
        in_band = (freqs >= lo) & (freqs < hi)
        columns[name] = np.log10(power[:, in_band].sum(axis=1) + 1e-20)
    return pd.DataFrame(columns, columns=FEATURE_NAMES_F2)


# ---------------------------------------------------------------------------
# F3: physics-informed envelope features
# ---------------------------------------------------------------------------

F3_HARMONICS = (1, 2, 3)
F3_TOLERANCE = 0.01                  # +/-1% around each line (slip here is ~0.3%)
F3_MEDIAN_RANGE_HZ = (10, 600)       # holds every target line (up to 3xBPFI ~ 490 Hz)
F3_TARGETS = {"bpfo": bearing_physics.bpfo_multiplier(),
              "bpfi": bearing_physics.bpfi_multiplier(),
              "2xbsf": 2 * bearing_physics.bsf_multiplier()}
FEATURE_NAMES_F3 = [f"{name}_{h}x" for name in F3_TARGETS for h in F3_HARMONICS]
F3_BANDS = candidate_bands()         # nine 1.2 kHz bands, 0.4-4.8 kHz


def envelope_line_levels(frequencies, amplitudes, rpm):
    """
    Steps 4-5 for one envelope spectrum: the 9 F3 numbers.
    """
    shaft_hz = rpm / 60.0
    bin_width = frequencies[1] - frequencies[0]
    lo, hi = F3_MEDIAN_RANGE_HZ
    median = np.median(amplitudes[(frequencies >= lo) & (frequencies <= hi)])
    values = []
    for name, multiplier in F3_TARGETS.items():
        for h in F3_HARMONICS:
            target = h * multiplier * shaft_hz
            tolerance = max(F3_TOLERANCE * target, bin_width)
            near = np.abs(frequencies - target) <= tolerance
            values.append(np.log10(amplitudes[near].max() / median))
    return values


def f3_for_every_band(windows, rpms, fs=FS):
    """
    Do the expensive work once: for every candidate band and every window,
    the band-passed kurtosis and the 9 F3 numbers.

    Returns (kurtosis, f3):
      kurtosis: array (n_windows x n_bands)
      f3:       array (n_bands x n_windows x 9)
    Choosing a band later is then just picking one slice.
    """
    windows = np.atleast_2d(windows)
    kurtosis = np.empty((len(windows), len(F3_BANDS)))
    f3 = np.empty((len(F3_BANDS), len(windows), len(FEATURE_NAMES_F3)))
    for b, band in enumerate(F3_BANDS):
        for i, (window, rpm) in enumerate(zip(windows, rpms)):
            kurtosis[i, b] = scipy.stats.kurtosis(bandpass(window, band, fs))
            freqs, amps = envelope_spectrum(window, band, fs)
            f3[b, i] = envelope_line_levels(freqs, amps, rpm)
    return kurtosis, f3


def choose_band(kurtosis, train_positions):
    """
    Pick the F3 band from TRAINING windows only: the band whose band-passed
    training windows have the highest median kurtosis.
    Returns the band's index into F3_BANDS.
    """
    median_by_band = np.median(kurtosis[train_positions], axis=0)
    return int(np.argmax(median_by_band))
