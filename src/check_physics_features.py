"""
check_physics_features.py - three checks on the physics-informed features F3.

1. Resolution: can a window of N samples tell the fault lines apart?
   A spectrum computed from N samples at 12 kHz has bins 12000/N Hz wide.
   With a Hann window, two peaks need to be about 2 bins apart to be seen
   as two. For each of the 9 lines F3 measures (1x, 2x, 3x of BPFO, BPFI
   and 2xBSF) we find the nearest other line - another fault line, a
   shaft-speed harmonic, or the usual sidebands BPFO+-1x and BPFI+-1x - and
   ask whether it is at least 2 bins away. Checked at the lowest speed
   (1730 rpm), where lines are closest together.

2. Sanity: on inner-race recordings the envelope level at BPFI should beat
   the level at BPFO in most windows, and the reverse on outer-race ones.
   The band here is chosen from ALL windows (no labels used); this is a
   check of the features, not a classifier.

3. Figure: the envelope spectrum of one window per fault type, with BPFO,
   BPFI and 2xBSF (and their 2x and 3x) marked.

Run:
    python -m src.check_physics_features

Outputs:
    results/f3_resolution_check.csv
    results/f3_sanity.csv
    results/figures/f3_envelope_spectra.png
"""

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import bearing_physics, config, features, segment
from src.check_fault_signatures import envelope_spectrum

FS = config.TARGET_SAMPLING_RATE_HZ
BINS_NEEDED = 2.0               # Hann window: peaks closer than ~2 bins merge
WINDOW_LENGTHS_TO_CHECK = (2048, 8192, 16384)
SLOWEST_RPM = min(config.NOMINAL_RPM.values())        # 1730

COLOUR_BY_LINE = {"bpfo": "#eb6834", "bpfi": "#1baf7a", "2xbsf": "#2a78d6"}
LINE_LABEL = {"bpfo": "BPFO (outer race)", "bpfi": "BPFI (inner race)",
              "2xbsf": "2×BSF (ball)"}
INK, INK_SECONDARY, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"
SPECTRUM_GREY = "#6f6e69"


# ---------------------------------------------------------------------------
# 1. Resolution
# ---------------------------------------------------------------------------

def spectral_lines(rpm):
    """
    Every line that could be confused with an F3 target, in Hz.
    Returns (targets, others): two {name: frequency_hz} dictionaries.
    """
    shaft = rpm / 60.0
    targets = {f"{h}x{name}": h * m * shaft
               for name, m in features.F3_TARGETS.items() for h in features.F3_HARMONICS}
    others = {f"{k}x shaft": k * shaft for k in range(1, 21)}
    bpfo = features.F3_TARGETS["bpfo"] * shaft
    bpfi = features.F3_TARGETS["bpfi"] * shaft
    others.update({"BPFO-1x": bpfo - shaft, "BPFO+1x": bpfo + shaft,
                   "BPFI-1x": bpfi - shaft, "BPFI+1x": bpfi + shaft})
    return targets, others


def resolution_table(rpm=SLOWEST_RPM):
    """For each F3 line: its nearest neighbour and the gap in bins per window length."""
    targets, others = spectral_lines(rpm)
    rows = []
    for name, freq in targets.items():
        candidates = {**{k: v for k, v in targets.items() if k != name}, **others}
        nearest, nearest_freq = min(candidates.items(), key=lambda kv: abs(kv[1] - freq))
        gap = abs(nearest_freq - freq)
        row = {"line": name, "hz": round(freq, 2), "nearest": nearest,
               "nearest_hz": round(nearest_freq, 2), "gap_hz": round(gap, 2)}
        for n in WINDOW_LENGTHS_TO_CHECK:
            row[f"gap_bins_{n}"] = round(gap / (FS / n), 2)
            row[f"separated_{n}"] = gap / (FS / n) >= BINS_NEEDED
        rows.append(row)
    return pd.DataFrame(rows).sort_values("gap_hz").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. Sanity
# ---------------------------------------------------------------------------

def sanity_table(meta, f3_values):
    """
    Share of windows where BPFI beats BPFO (inner race) or BPFO beats BPFI
    (outer race), at 1x, overall and per fault size.
    f3_values: array (n_windows x 9) for one band, columns FEATURE_NAMES_F3.
    """
    table = pd.DataFrame(f3_values, columns=features.FEATURE_NAMES_F3)
    table["fault_location"] = meta["fault_location"].to_numpy()
    table["fault_size_in"] = meta["fault_size_in"].to_numpy()
    rows = []
    for location, expected, other in (("inner_race", "bpfi_1x", "bpfo_1x"),
                                      ("outer_race", "bpfo_1x", "bpfi_1x")):
        part = table[table["fault_location"] == location]
        wins = part[expected] > part[other]
        rows.append({"fault_location": location, "fault_size_in": "all",
                     "test": f"{expected} > {other}", "n_windows": len(part),
                     "share_true": round(wins.mean(), 3)})
        for size, group in part.groupby("fault_size_in"):
            rows.append({"fault_location": location, "fault_size_in": f"{size:.3f}",
                         "test": f"{expected} > {other}", "n_windows": len(group),
                         "share_true": round((group[expected] > group[other]).mean(), 3)})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 3. Figure
# ---------------------------------------------------------------------------

EXAMPLE_FILES = {"normal": 97, "inner_race": 105, "ball": 118, "outer_race": 130}


def plot_envelope_examples(windows, meta, band, path):
    """Envelope spectrum of the first window of one recording per class."""
    fig, axes = plt.subplots(4, 1, figsize=(9, 10), sharex=True, facecolor=SURFACE)
    for ax, (location, number) in zip(axes, EXAMPLE_FILES.items()):
        i = int(np.flatnonzero(meta["file_number"].to_numpy() == number)[0])
        rpm = meta["rpm"].iloc[i]
        freqs, amps = envelope_spectrum(windows[i], band, FS)
        show = (freqs > 2) & (freqs <= 520)
        ax.plot(freqs[show], amps[show], color=SPECTRUM_GREY, linewidth=0.9, zorder=3)
        shaft = rpm / 60.0
        for name, multiplier in features.F3_TARGETS.items():
            for h in features.F3_HARMONICS:
                ax.axvline(h * multiplier * shaft, color=COLOUR_BY_LINE[name],
                           linestyle="-" if h == 1 else "--", linewidth=1.3 if h == 1 else 0.9,
                           zorder=1, label=f"{LINE_LABEL[name]}: 1× solid, 2× and 3× dashed"
                           if h == 1 else None)
        name = location.replace("_", " ")
        ax.set_title(f"{name}: {meta['cwru_name'].iloc[i]} ({number}.mat), "
                     f"{rpm:.0f} rpm, first 0.68 s window", loc="left", fontsize=10, color=INK)
        ax.set_ylabel("Envelope amplitude (g)", fontsize=9, color=INK)
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.tick_params(colors=INK_SECONDARY, labelsize=9)
        for spine in ax.spines.values():
            spine.set_color(GRID)
    axes[-1].set_xlabel("Envelope frequency (Hz)", fontsize=10, color=INK)
    axes[-1].set_xlim(0, 520)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=1, fontsize=9, frameon=False,
               labelcolor=INK_SECONDARY)
    fig.suptitle(f"Envelope spectra, band {band[0]}-{band[1]} Hz", x=0.01, ha="left",
                 y=0.995, fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    resolution = resolution_table()
    resolution.to_csv(config.RESULTS_DIR / "f3_resolution_check.csv", index=False)
    print(f"1. Resolution at {SLOWEST_RPM} rpm (lines need >= {BINS_NEEDED:.0f} bins apart):")
    print(resolution.to_string(index=False))
    for n in WINDOW_LENGTHS_TO_CHECK:
        print(f"   {n} samples ({FS / n:.2f} Hz bins): "
              f"{int(resolution[f'separated_{n}'].sum())} of {len(resolution)} lines separated")

    windows, meta = segment.make_windows(config.F3_WINDOW_LENGTH_SAMPLES)
    kurtosis, f3 = features.f3_for_every_band(windows, meta["rpm"].to_numpy())
    band_index = features.choose_band(kurtosis, np.arange(len(windows)))   # all windows, no labels
    band = features.F3_BANDS[band_index]

    sanity = sanity_table(meta, f3[band_index])
    sanity.to_csv(config.RESULTS_DIR / "f3_sanity.csv", index=False)
    print(f"\n2. Sanity check (band {band[0]}-{band[1]} Hz, chosen from all windows):")
    print(sanity.to_string(index=False))

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot_envelope_examples(windows, meta, band, config.FIGURES_DIR / "f3_envelope_spectra.png")
    print("\nSaved results/f3_resolution_check.csv, results/f3_sanity.csv, "
          "results/figures/f3_envelope_spectra.png")


if __name__ == "__main__":
    main()
