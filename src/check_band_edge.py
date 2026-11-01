"""
check_band_edge.py - after filtering, do all classes look alike above 5 kHz?

Background: the normal files were recorded at 48 kHz and resampled to
12 kHz; the fault files were recorded at 12 kHz. Each went through a
different anti-aliasing filter, so near the top of the band (5-6 kHz) the
two groups look different for reasons that have nothing to do with
bearings. A classifier could use that difference as a shortcut.
load_data.load_signal() therefore low-pass filters every signal at 5 kHz.
This script measures whether that works.

What it measures:
  1. How the resampling filter (48 -> 12 kHz) treats each frequency, by
     passing random noise through it (noise contains every frequency
     equally, so whatever comes out shows the filter's shape).
  2. How our low-pass filter treats each frequency.
  3. For every file, the share of its vibration energy above 5.2 kHz,
     before and after the low-pass filter.
  4. The typical (median) spectrum of the fault files and of the normal
     files between 2 and 6 kHz, before and after, drawn as a figure.

Run it after src/load_data.py:
    python -m src.check_band_edge

Outputs:
    results/band_edge_by_file.csv    energy above 5.2 kHz, every file
    results/band_edge_filters.csv    both filters' responses
    results/figures/band_edge.png
"""

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.signal

from src import config, load_data

FS = config.TARGET_SAMPLING_RATE_HZ
SEGMENT = 2048                  # Welch segment length: about 6 Hz resolution
REPORT_FREQUENCIES_HZ = (3000, 4000, 4500, 4800, 5000, 5200, 5500, 5800, 5950)

COLOUR_FAULT = "#2a78d6"        # blue
COLOUR_NORMAL = "#eb6834"       # orange
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3de"
SURFACE = "#fcfcfb"
BAND = "#e9e8e3"


def power_spectrum(signal):
    """Average power at each frequency (Welch's method). Returns (freqs, power)."""
    return scipy.signal.welch(signal, FS, nperseg=SEGMENT)


def share_above_db(signal, edge_hz=config.LOWPASS_STOPBAND_EDGE_HZ):
    """Fraction of the signal's power above edge_hz, in dB (-30 dB = 0.1%)."""
    freqs, power = power_spectrum(signal)
    share = power[freqs >= edge_hz].sum() / power[freqs > 0].sum()
    return 10 * np.log10(share)


def resampling_filter_response():
    """Measure the 48 -> 12 kHz resampling filter with 200 s of random noise."""
    rng = np.random.default_rng(0)
    noise = rng.normal(size=48_000 * 200)
    freqs, power = power_spectrum(load_data.resample_to_target(noise, 48_000, FS))
    reference = np.median(power[(freqs > 500) & (freqs < 3000)])
    return freqs, 10 * np.log10(power / reference)


def lowpass_response(freqs):
    """Our low-pass filter's effect in dB, run forwards and backwards."""
    _, h = scipy.signal.freqz(load_data.lowpass_filter_taps(), worN=freqs, fs=FS)
    # filtfilt applies the filter twice, so the effect in dB doubles.
    return 2 * 20 * np.log10(np.maximum(np.abs(h), 1e-12))


def median_shape_db(signals):
    """
    The typical spectrum of a group of signals, in dB, shifted so that the
    2-4 kHz level is 0 dB. Shifting lets us compare SHAPES, not loudness.
    """
    spectra = []
    for s in signals:
        freqs, power = power_spectrum(s)
        db = 10 * np.log10(np.maximum(power, 1e-30))
        spectra.append(db - np.median(db[(freqs >= 2000) & (freqs <= 4000)]))
    return freqs, np.median(spectra, axis=0)


def value_at(freqs, values, target_hz):
    return float(values[np.argmin(np.abs(freqs - target_hz))])


def plot(curves, path):
    """Two panels: typical spectrum shapes before and after the low-pass."""
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.4), sharey=True, facecolor=SURFACE)
    for ax, stage in zip(axes, ("before", "after")):
        ax.axvspan(config.LOWPASS_PASSBAND_EDGE_HZ, config.LOWPASS_STOPBAND_EDGE_HZ,
                   color=BAND, zorder=0, label="Filter transition 4.8-5.2 kHz")
        for group, colour in (("fault", COLOUR_FAULT), ("normal", COLOUR_NORMAL)):
            freqs, db = curves[(group, stage)]
            show = (freqs >= 2000) & (freqs <= 6000)
            name = ("36 fault files (recorded at 12 kHz)" if group == "fault"
                    else "4 normal files (recorded at 48 kHz, resampled)")
            ax.plot(freqs[show], db[show], color=colour, linewidth=2, label=name)
        ax.set_title(f"{stage.capitalize()} the 5 kHz low-pass", loc="left",
                     fontsize=11, color=INK)
        ax.set_xlabel("Frequency (Hz)", color=INK)
        ax.set_xlim(2000, 6000)
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, linewidth=0.6)
        ax.tick_params(colors=INK_SECONDARY)
        for spine in ax.spines.values():
            spine.set_color(GRID)
    axes[0].set_ylabel("Typical spectrum, dB (2-4 kHz level = 0)", color=INK)
    axes[0].set_ylim(-170, 25)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=9,
               frameon=False, labelcolor=INK_SECONDARY)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main():
    rows, groups = [], {("fault", "before"): [], ("fault", "after"): [],
                        ("normal", "before"): [], ("normal", "after"): []}
    for info in config.expected_files():
        number = info["file_number"]
        if not load_data.mat_path(number).exists():
            continue
        raw, _ = load_data.load_raw_signal(number)
        before = load_data.resample_to_target(raw, load_data.recorded_sampling_rate(number))
        after = load_data.lowpass(before)
        group = "normal" if info["fault_location"] == "normal" else "fault"
        groups[(group, "before")].append(before)
        groups[(group, "after")].append(after)
        rows.append({"file_number": number, "group": group,
                     "recorded_at_hz": load_data.recorded_sampling_rate(number),
                     "share_above_5200hz_before_db": round(share_above_db(before), 1),
                     "share_above_5200hz_after_db": round(share_above_db(after), 1)})

    by_file = pd.DataFrame(rows)
    by_file.to_csv(config.RESULTS_DIR / "band_edge_by_file.csv", index=False)

    curves = {key: median_shape_db(signals) for key, signals in groups.items()}
    resample_freqs, resample_db = resampling_filter_response()
    report = []
    for hz in REPORT_FREQUENCIES_HZ:
        report.append({
            "frequency_hz": hz,
            "resampling_filter_db": round(value_at(resample_freqs, resample_db, hz), 2),
            "lowpass_filter_db": round(float(lowpass_response(np.array([hz]))[0]), 2),
            "fault_typical_before_db": round(value_at(*curves[("fault", "before")], hz), 1),
            "normal_typical_before_db": round(value_at(*curves[("normal", "before")], hz), 1),
        })
    filters = pd.DataFrame(report)
    filters.to_csv(config.RESULTS_DIR / "band_edge_filters.csv", index=False)

    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    plot(curves, config.FIGURES_DIR / "band_edge.png")

    print("Filters and typical spectra (dB):")
    print(filters.to_string(index=False))
    print("\nShare of energy above 5.2 kHz (dB; -30 dB = 0.1%), by group:")
    summary = by_file.groupby("group")[["share_above_5200hz_before_db",
                                        "share_above_5200hz_after_db"]].agg(["min", "max"])
    print(summary.to_string())
    print(f"\nSaved results/band_edge_by_file.csv, results/band_edge_filters.csv, "
          f"results/figures/band_edge.png")


if __name__ == "__main__":
    main()
