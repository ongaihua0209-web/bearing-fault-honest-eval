"""
check_fault_signatures.py - does each file show the fault its label claims?

This is a check on the DATA, not a classifier. It never changes a label:
CWRU's labels are kept exactly as published (owner decision, 2026-11-02).
It only reports where the physics agrees with the label and where it
does not, so later results can be read with that in mind.

How envelope analysis works (plain English):
  A damaged spot makes a small impact every time a ball rolls over it.
  Each impact makes the structure "ring" briefly at its own natural
  frequencies (thousands of Hz). The impacts repeat at the fault frequency
  (e.g. BPFO, about 107 Hz), so the ringing switches on and off at that
  rate. To recover the on/off rate:
    1. keep only a frequency band where the ringing is strong (band-pass);
    2. trace the outline - the "envelope" - of the filtered signal;
    3. take the spectrum of that envelope: peaks appear at the impact rate.

Which band? (the "principled band choice")
  Impacts make a signal spiky. Kurtosis measures spikiness: 0 for plain
  random noise, large for a signal made of sharp impacts. We try
  overlapping 1.2 kHz-wide bands from 0.4 to 4.8 kHz and use the spikiest
  one. This is the idea behind spectral kurtosis and the "kurtogram"
  (J. Antoni), in its simplest form. The choice uses only the signal, never
  the label. As a second opinion we also use one fixed wide band (2.0 to
  4.8 kHz), so a single unlucky band choice cannot hide a fault.

  Why 1.2 kHz wide: the envelope can only show frequencies up to about the
  band's width, and we need to see BPFI (about 160 Hz) clearly, with room
  for its harmonics and sidebands. Why stop at 4.8 kHz: the project rule
  that nothing above 4.8 kHz is used (docs/VALIDATION.md 3.5).

Evidence for each fault type (envelope peak / background, see below):
    outer race: BPFO
    inner race: BPFI
    ball:       BSF or 2 x BSF, whichever is stronger
    (the cage frequency FTF is reported for information only)
  "Peak / background" = the biggest envelope value within +/-2% of the
  fault frequency, divided by the median level within +/-20% around it.
  A fault type counts as "clear" when this is 10 or more (the same
  threshold as the sampling-rate check).

Verdict for each file (rules fixed BEFORE running on the real data):
  normal file: "matches label" if no fault type is clear in either band,
               otherwise "unexpected: <types>".
  fault file:  "matches label" if its own fault type is clear in either
               band; "looks like <type>" if only another type is clear;
               "no signature" if nothing is clear.

Sensitivity check (added AFTER the first run on real data, and reported
separately - the verdict above stays the primary result):
  The first run showed that inner-race files have a sideband at
  BPFI - 3 x shaft speed = 2.40 x shaft speed, which sits at the very edge
  of the +/-2% ball (BSF) window (2.31-2.40 x). That can create false "ball"
  evidence. "verdict_narrow" repeats the verdict with a +/-1% window, which
  excludes that sideband and still allows more slip than the clean files
  show (0.3-0.6%). The CSV also records where each peak was found, as a
  multiple of shaft speed, so anyone can see what was measured.

Run it after src/load_data.py:
    python -m src.check_fault_signatures

Outputs:
    results/fault_signatures.csv
    results/figures/fault_signatures_overview.png
"""

import math

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.signal
import scipy.stats

from src import bearing_physics, config, load_data
from src.check_sampling_rate import amplitude_spectrum, peak_strength

# Band search
BAND_WIDTH_HZ = 1200
BAND_STEP_HZ = 400
LOWEST_BAND_EDGE_HZ = 400
HIGHEST_BAND_EDGE_HZ = config.LOWPASS_PASSBAND_EDGE_HZ        # 4800
FIXED_BAND_HZ = (2000, config.LOWPASS_PASSBAND_EDGE_HZ)

# Peak measurement
SEARCH_TOLERANCE = 0.02     # +/-2% around each fault frequency (allows for slip)
NARROW_TOLERANCE = 0.01     # sensitivity check, see top of file
BACKGROUND_SPAN = 0.20      # background = median within +/-20%
CLEAR_PEAK_RATIO = 10

FAULT_TYPES = ("outer_race", "inner_race", "ball")

# Plot
PLOT_MAX_ORDER = 7          # x-axis up to 7 x shaft speed
COLOUR_ENVELOPE = "#6f6e69"                 # neutral grey: the data
COLOUR_BY_TYPE = {"outer_race": "#eb6834",  # orange  } reference lines, in the
                  "inner_race": "#1baf7a",  # aqua    } three colour-blind-safe
                  "ball": "#2a78d6"}        # blue    } palette colours
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3de"
SURFACE = "#fcfcfb"


# ---------------------------------------------------------------------------
# Signal processing steps
# ---------------------------------------------------------------------------

def candidate_bands():
    """The overlapping bands we try: (400, 1600), (800, 2000), ... (3600, 4800)."""
    lows = range(LOWEST_BAND_EDGE_HZ, HIGHEST_BAND_EDGE_HZ - BAND_WIDTH_HZ + 1, BAND_STEP_HZ)
    return [(low, low + BAND_WIDTH_HZ) for low in lows]


def bandpass(signal, band, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Keep only the frequencies inside band = (low_hz, high_hz).
    A 4th-order Butterworth filter, run forwards and backwards so the
    impacts are not shifted in time.
    """
    sos = scipy.signal.butter(4, band, btype="bandpass", fs=fs, output="sos")
    return scipy.signal.sosfiltfilt(sos, signal)


def spikiness(signal):
    """Excess kurtosis: 0 for random noise, large for a train of impacts."""
    return float(scipy.stats.kurtosis(signal))


def most_impulsive_band(signal, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Try every candidate band and return the spikiest one.
    Returns (band, its_kurtosis).
    """
    scores = [(spikiness(bandpass(signal, band, fs)), band) for band in candidate_bands()]
    best_kurtosis, best_band = max(scores)
    return best_band, best_kurtosis


def envelope_spectrum(signal, band, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Steps 1-3 of envelope analysis (see top of file).
    The Hilbert transform gives the envelope: the smooth outline that
    joins the tops of the ringing.
    Returns (frequencies_hz, amplitudes).
    """
    filtered = bandpass(signal, band, fs)
    envelope = np.abs(scipy.signal.hilbert(filtered))
    return amplitude_spectrum(envelope, fs)      # removes the mean, Hann window


# ---------------------------------------------------------------------------
# Evidence and verdict
# ---------------------------------------------------------------------------

def evidence_by_fault_type(frequencies, amplitudes, rpm, tolerance=SEARCH_TOLERANCE):
    """
    For each fault type (and the cage, for info): the peak/background ratio
    and where the peak was found, as a multiple of shaft speed.
    Returns {fault_type: (ratio, peak_position_in_shaft_orders)}.
    """
    hz = bearing_physics.fault_frequencies_hz(rpm)
    shaft_hz = rpm / 60.0

    def measure(name):
        peak_hz, ratio = peak_strength(frequencies, amplitudes, hz[name],
                                       tolerance, BACKGROUND_SPAN)
        return ratio, peak_hz / shaft_hz

    return {"outer_race": measure("BPFO"),
            "inner_race": measure("BPFI"),
            "ball": max(measure("BSF"), measure("2xBSF")),   # the stronger one
            "cage_FTF": measure("FTF")}


def clear_fault_types(evidence):
    """The fault types whose ratio reaches the 'clear' threshold."""
    return [t for t in FAULT_TYPES if evidence[t][0] >= CLEAR_PEAK_RATIO]


def verdict(label, clear_types):
    """Apply the verdict rules from the top of this file."""
    if label == "normal":
        return "matches label" if not clear_types else "unexpected: " + ", ".join(clear_types)
    if label in clear_types:
        return "matches label"
    if clear_types:
        return "looks like " + " + ".join(clear_types)
    return "no signature"


def rig_wide_raw_peaks(signal, rpm, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    Not part of the verdict. Measures two peaks in the RAW spectrum (no
    envelope) that appear in every file, healthy ones included: the
    inner-race frequencies of the drive-end bearing (BPFI, 5.415x) and of the
    fan-end bearing (4.947x, CWRU's figure). Recording them shows why a raw
    spectrum peak at BPFI is NOT evidence of an inner-race fault in this data.
    Returns {name: (ratio, peak_position_in_shaft_orders)}.
    """
    frequencies, amplitudes = amplitude_spectrum(signal, fs)
    shaft_hz = rpm / 60.0
    targets = {"raw_drive_end_BPFI": bearing_physics.bpfi_multiplier(),
               "raw_fan_end_BPFI": config.FAN_END_CWRU_MULTIPLIERS["BPFI"]}
    found = {}
    for name, multiplier in targets.items():
        peak_hz, ratio = peak_strength(frequencies, amplitudes, multiplier * shaft_hz,
                                       SEARCH_TOLERANCE, BACKGROUND_SPAN)
        found[name] = (ratio, peak_hz / shaft_hz)
    return found


def check_signal(signal, rpm, label, fs=config.TARGET_SAMPLING_RATE_HZ):
    """
    The whole check for one signal: pick the band, compute both envelope
    spectra, measure the evidence, give the verdict.
    Returns (result_dict, plot_data).
    """
    band, kurtosis = most_impulsive_band(signal, fs)
    spectra = {"sel": envelope_spectrum(signal, band, fs),
               "fix": envelope_spectrum(signal, FIXED_BAND_HZ, fs)}
    result = {"selected_band_hz": f"{band[0]}-{band[1]}",
              "selected_band_kurtosis": round(kurtosis, 2)}

    # Primary result (+/-2%) and sensitivity check (+/-1%), same spectra.
    for suffix, tolerance in (("", SEARCH_TOLERANCE), ("_narrow", NARROW_TOLERANCE)):
        evidence = {name: evidence_by_fault_type(f, a, rpm, tolerance)
                    for name, (f, a) in spectra.items()}
        clear = [t for t in FAULT_TYPES
                 if any(t in clear_fault_types(e) for e in evidence.values())]
        if suffix == "":       # keep the detailed numbers for the primary run
            for name, e in evidence.items():
                for fault_type, (ratio, position) in e.items():
                    result[f"{name}_{fault_type}"] = round(ratio, 1)
                    result[f"{name}_{fault_type}_at_order"] = round(position, 3)
        result["clear_types" + suffix] = " + ".join(clear) if clear else "none"
        result["verdict" + suffix] = verdict(label, clear)
    return result, spectra["sel"]


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

def plot_overview(panels, path):
    """Envelope spectra of every file (selected band), one row per condition."""
    multipliers = {"outer_race": [bearing_physics.bpfo_multiplier()],
                   "inner_race": [bearing_physics.bpfi_multiplier()],
                   "ball": [bearing_physics.bsf_multiplier(), 2 * bearing_physics.bsf_multiplier()]}
    legend_names = {"outer_race": "BPFO (outer race)", "inner_race": "BPFI (inner race)",
                    "ball": "BSF and 2xBSF (ball)"}
    n_cols = 4
    n_rows = math.ceil(len(panels) / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.6 * n_cols, 2.3 * n_rows + 0.9),
                             facecolor=SURFACE, squeeze=False)
    for ax, (number, label, rpm, freqs, amps, result) in zip(axes.flat, panels):
        orders = freqs / (rpm / 60.0)            # x-axis in multiples of shaft speed
        show = (orders > 0.2) & (orders <= PLOT_MAX_ORDER)
        ax.plot(orders[show], amps[show], color=COLOUR_ENVELOPE, linewidth=0.7, zorder=3)
        for fault_type, values in multipliers.items():
            for i, m in enumerate(values):
                ax.axvline(m, color=COLOUR_BY_TYPE[fault_type], linestyle="--",
                           linewidth=1.1, zorder=1,
                           label=legend_names[fault_type] if i == 0 else None)
        ax.set_title(f"{number}.mat {label}: {result['verdict']}",
                     fontsize=7.5, color=INK, loc="left")
        ax.set_xlim(0, PLOT_MAX_ORDER)
        ax.set_yticks([])
        ax.set_facecolor(SURFACE)
        ax.grid(True, axis="x", color=GRID, linewidth=0.6)
        ax.tick_params(colors=INK_SECONDARY, labelsize=7)
        for spine in ax.spines.values():
            spine.set_color(GRID)
    for ax in list(axes.flat)[len(panels):]:
        ax.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=9,
               frameon=False, labelcolor=INK_SECONDARY)
    fig.supxlabel("Envelope frequency as a multiple of shaft speed "
                  "(spikiest band per file)", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.5 / (2.3 * n_rows + 0.9)))
    fig.savefig(path, dpi=100)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    rows, panels = [], []
    for info in config.expected_files():
        number = info["file_number"]
        if not load_data.mat_path(number).exists():
            continue
        signal, rpm, fs = load_data.load_signal(number)
        label = info["fault_location"]
        result, (freqs, amps) = check_signal(signal, rpm, label, fs)
        for name, (ratio, position) in rig_wide_raw_peaks(signal, rpm, fs).items():
            result[name] = round(ratio, 1)
            result[name + "_at_order"] = round(position, 3)
        short = f"{label} {info['fault_size_in']:.3f} {info['load_hp']}HP"
        rows.append({"file_number": number, "label": label,
                     "fault_size_in": info["fault_size_in"], "load_hp": info["load_hp"],
                     "rpm": rpm, **result})
        panels.append((number, short, rpm, freqs, amps, result))

    table = pd.DataFrame(rows)
    out_csv = config.RESULTS_DIR / "fault_signatures.csv"
    table.to_csv(out_csv, index=False)
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_overview(panels, config.FIGURES_DIR / "fault_signatures_overview.png")

    columns = ["file_number", "label", "fault_size_in", "load_hp", "selected_band_hz",
               "sel_outer_race", "sel_inner_race", "sel_ball",
               "fix_outer_race", "fix_inner_race", "fix_ball", "verdict",
               "verdict_narrow"]
    print(table[columns].to_string(index=False))
    for column in ("verdict", "verdict_narrow"):
        print(f"\n{column} by condition:")
        summary = table.groupby(["label", "fault_size_in"], sort=False)[column].agg(
            lambda v: ", ".join(f"{k} x{c}" for k, c in v.value_counts().items()))
        for (label, size), text in summary.items():
            print(f"  {label:10s} {size:.3f}  {text}")
    print("\nRaw-spectrum peaks present in every file (not used in verdicts):")
    for name in ("raw_drive_end_BPFI", "raw_fan_end_BPFI"):
        print(f"  {name}: found at {table[name + '_at_order'].min():.3f}-"
              f"{table[name + '_at_order'].max():.3f} x shaft speed, "
              f"peak/background {table[name].min():.0f}-{table[name].max():.0f}")
    print(f"\nSaved {out_csv.relative_to(config.REPO_ROOT)} and "
          f"results/figures/fault_signatures_overview.png")


if __name__ == "__main__":
    main()
