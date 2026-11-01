"""
check_sampling_rate.py - was each file really recorded at 12 kHz?

Why this matters: sources disagree on whether CWRU's normal (healthy) files
were recorded at 12 kHz or 48 kHz. If one class of data were secretly at a
different rate, a classifier could learn "this file looks like 48 kHz"
instead of "this bearing is damaged" - a shortcut that inflates accuracy.

The idea of the check:
  The shaft turns rpm/60 times per second, so a vibration spectrum almost
  always has a peak at that frequency (called "1x"). A spectrum's frequency
  axis is calculated FROM the sampling rate. If we read a file assuming
  12 kHz but it was really recorded at 48 kHz, every frequency comes out
  4 times too low: the 1x peak near 30 Hz would appear near 7.5 Hz.
  So we look for the 1x peak in both places and see which one exists.

How "a peak exists" is decided:
  Within +/-3% of the expected frequency we take the biggest value, and
  divide it by the typical (median) level of the spectrum around it
  (+/-30%). A real peak stands at least 10 times above its surroundings.
  Exactly one candidate rate must pass; otherwise the verdict is
  "inconclusive" and a person has to look at the plot.

Run it AFTER src/load_data.py:
    python -m src.check_sampling_rate

Outputs:
    results/sampling_rate_check.csv
    results/figures/sampling_rate/<file>.png   (one plot per file)
    results/figures/sampling_rate_overview.png  (all files on one page)
"""

import math

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import bearing_physics, config, load_data

CANDIDATE_RATES_HZ = (12_000, 48_000)
SEARCH_TOLERANCE = 0.03     # look for the peak within +/-3% of where it should be
BACKGROUND_SPAN = 0.30      # compare it with the spectrum within +/-30%
CLEAR_PEAK_RATIO = 10       # a real peak is at least 10x its background
PLOT_MAX_HZ = 200

# Chart colours (a colour-blind-checked palette) and neutral inks.
COLOUR_SPECTRUM = "#2a78d6"   # blue
COLOUR_IF_12K = "#eb6834"     # orange
COLOUR_IF_48K = "#1baf7a"     # aqua
COLOUR_REFERENCE = "#8a8984"  # grey, for theoretical fault frequencies
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3de"
SURFACE = "#fcfcfb"


def amplitude_spectrum(signal, fs):
    """
    Frequency content of a signal (FFT), scaled so a pure sine of amplitude
    A shows a peak of height about A.

    A Hann window tapers the ends of the recording to zero first; without it
    the abrupt start and end smear energy across the spectrum.

    Returns (frequencies_hz, amplitudes).
    """
    x = np.asarray(signal, dtype=float)
    x = x - x.mean()                         # remove any DC offset
    window = np.hanning(len(x))
    amplitudes = np.abs(np.fft.rfft(x * window)) * 2 / window.sum()
    frequencies = np.fft.rfftfreq(len(x), d=1.0 / fs)
    return frequencies, amplitudes


def peak_strength(frequencies, amplitudes, expected_hz):
    """
    How clearly does a peak stand out near expected_hz?

    Returns (frequency_of_biggest_value_nearby, ratio_to_background).
    """
    distance = np.abs(frequencies - expected_hz)
    near = distance <= SEARCH_TOLERANCE * expected_hz
    background = (distance <= BACKGROUND_SPAN * expected_hz) & ~near

    nearby_amps = np.where(near, amplitudes, -np.inf)
    i = int(np.argmax(nearby_amps))
    ratio = amplitudes[i] / np.median(amplitudes[background])
    return float(frequencies[i]), float(ratio)


def check_signal(signal, rpm, assumed_fs=config.ASSUMED_SAMPLING_RATE_HZ):
    """
    Test each candidate sampling rate for one signal.

    The spectrum is always computed as if the file were at assumed_fs.
    If the TRUE rate were true_fs, the 1x peak would appear at
        (rpm / 60) * assumed_fs / true_fs
    on that spectrum.

    Returns (result_dict, frequencies, amplitudes).
    """
    frequencies, amplitudes = amplitude_spectrum(signal, assumed_fs)
    shaft_hz = rpm / 60.0
    result = {"shaft_1x_hz": round(shaft_hz, 3)}

    passed = []
    for true_fs in CANDIDATE_RATES_HZ:
        tag = f"{true_fs // 1000}k"
        where_it_would_appear = shaft_hz * assumed_fs / true_fs
        found_hz, ratio = peak_strength(frequencies, amplitudes, where_it_would_appear)
        result[f"if_{tag}_expected_hz"] = round(where_it_would_appear, 3)
        result[f"if_{tag}_found_hz"] = round(found_hz, 3)
        result[f"if_{tag}_peak_ratio"] = round(ratio, 1)
        if ratio >= CLEAR_PEAK_RATIO:
            passed.append(tag)

    result["verdict"] = passed[0] + "Hz" if len(passed) == 1 else "inconclusive"
    return result, frequencies, amplitudes


def verdict_for_rate(rate_hz):
    """12000 -> '12kHz', so config values can be compared with verdicts."""
    return f"{int(rate_hz) // 1000}kHz"


def _draw_spectrum(ax, frequencies, amplitudes, result, rpm, compact=False):
    """Draw one spectrum with the reference lines on a matplotlib axis."""
    show = (frequencies > 0) & (frequencies <= PLOT_MAX_HZ)
    # zorder controls what is drawn on top: the spectrum (3) sits above the
    # reference lines (1), so a line never hides the peak it points at.
    ax.semilogy(frequencies[show], amplitudes[show], color=COLOUR_SPECTRUM,
                linewidth=0.8, zorder=3, label="Spectrum, read as 12 kHz")
    ax.axvline(result["if_12k_expected_hz"], color=COLOUR_IF_12K,
               linestyle="--", linewidth=1.4, zorder=1,
               label="1x if truly 12 kHz (rpm/60)")
    ax.axvline(result["if_48k_expected_hz"], color=COLOUR_IF_48K,
               linestyle="--", linewidth=1.4, zorder=1,
               label="Where 1x would appear if truly 48 kHz")

    # Theoretical fault frequencies, as faint reference lines.
    fault_hz = bearing_physics.fault_frequencies_hz(rpm)
    for name in ("FTF", "BPFO", "2xBSF", "BPFI"):
        ax.axvline(fault_hz[name], color=COLOUR_REFERENCE, linestyle=":",
                   linewidth=0.9, zorder=1)
        if not compact:
            ax.text(fault_hz[name], 1.0, " " + name, transform=ax.get_xaxis_transform(),
                    rotation=90, va="top", ha="left", fontsize=8,
                    color=INK_SECONDARY)

    ax.set_xlim(0, PLOT_MAX_HZ)
    ax.set_facecolor(SURFACE)
    ax.grid(True, which="major", color=GRID, linewidth=0.6)
    ax.tick_params(colors=INK_SECONDARY, labelsize=7 if compact else 9)
    for spine in ax.spines.values():
        spine.set_color(GRID)


def plot_file(file_number, label, frequencies, amplitudes, result, rpm, path):
    """Save one detailed spectrum plot for one file."""
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    _draw_spectrum(ax, frequencies, amplitudes, result, rpm)
    ax.set_xlabel("Frequency (Hz), calculated assuming 12 kHz", color=INK)
    ax.set_ylabel("Amplitude (g, log scale)", color=INK)
    ax.set_title(f"{file_number}.mat  |  {label}  |  {rpm:.0f} rpm  |  "
                 f"verdict: {result['verdict']}", color=INK, fontsize=11, loc="left")
    ax.plot([], [], color=COLOUR_REFERENCE, linestyle=":",
            label="Theoretical fault frequencies")
    # Legend below the plot, so it never covers data.
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2,
              fontsize=8, frameon=False, labelcolor=INK_SECONDARY)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def plot_overview(panels, path):
    """All files on one page, so any odd one out is easy to spot."""
    n = len(panels)
    n_cols = min(4, n)
    n_rows = math.ceil(n / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.6 * n_cols, 2.6 * n_rows + 0.8),
                             facecolor=SURFACE, squeeze=False)
    for ax, (file_number, label, freqs, amps, result, rpm) in zip(axes.flat, panels):
        _draw_spectrum(ax, freqs, amps, result, rpm, compact=True)
        ax.set_title(f"{file_number}.mat {label}\n{result['verdict']}",
                     fontsize=8, color=INK, loc="left")
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=8,
               frameon=False, labelcolor=INK_SECONDARY)
    fig.supxlabel("Frequency (Hz), calculated assuming 12 kHz", fontsize=9, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main():
    manifest_path = config.RESULTS_DIR / "manifest.csv"
    if not manifest_path.exists():
        raise SystemExit("results/manifest.csv not found - run "
                         "'python -m src.load_data' first.")
    manifest = pd.read_csv(manifest_path)
    present = manifest[manifest["status"].isin(["ok", "excluded_duplicate"])]

    figure_dir = config.FIGURES_DIR / "sampling_rate"
    figure_dir.mkdir(parents=True, exist_ok=True)

    rows, panels = [], []
    for _, info in present.iterrows():
        number = int(info["file_number"])
        label = f"{info['fault_location']} {info['fault_size_in']:.3f} in {info['load_hp']} HP"
        signal, rpm = load_data.load_raw_signal(number)

        result, freqs, amps = check_signal(signal, rpm)
        rate_in_config = load_data.recorded_sampling_rate(number)
        row = {"file_number": number, "label": label, "rpm": rpm,
               "n_samples": signal.size, **result,
               "rate_in_config_hz": rate_in_config}

        # If config says this file is 48 kHz, prove the resampled copy is right.
        if rate_in_config != config.TARGET_SAMPLING_RATE_HZ:
            resampled = load_data.resample_to_target(signal, rate_in_config)
            after, _, _ = check_signal(resampled, rpm)
            row["verdict_after_resampling"] = after["verdict"]
        else:
            row["verdict_after_resampling"] = "not needed"

        rows.append(row)
        panels.append((number, label, freqs, amps, result, rpm))
        plot_file(number, label, freqs, amps, result, rpm, figure_dir / f"{number}.png")

    if not rows:
        raise SystemExit("No files present to check.")

    table = pd.DataFrame(rows)
    out_csv = config.RESULTS_DIR / "sampling_rate_check.csv"
    table.to_csv(out_csv, index=False)
    plot_overview(panels, config.FIGURES_DIR / "sampling_rate_overview.png")

    columns = ["file_number", "rpm", "if_12k_found_hz", "if_12k_peak_ratio",
               "if_48k_found_hz", "if_48k_peak_ratio", "verdict"]
    print(table[columns].to_string(index=False))

    # Shout if the evidence disagrees with what config.py says.
    disagree = table[(table["verdict"] != "inconclusive") &
                     (table["verdict"] != table["rate_in_config_hz"].map(verdict_for_rate))]
    unsure = table[table["verdict"] == "inconclusive"]
    if len(disagree):
        print("\nWARNING: these files disagree with config.py and need an override:")
        print(disagree[["file_number", "verdict", "rate_in_config_hz"]].to_string(index=False))
    if len(unsure):
        print("\nWARNING: inconclusive - look at the plots for files",
              ", ".join(str(n) for n in unsure["file_number"]))
    if not len(disagree) and not len(unsure):
        print("\nAll checked files agree with the sampling rates in config.py.")

    print(f"\nSaved {out_csv.relative_to(config.REPO_ROOT)} and plots in "
          f"{config.FIGURES_DIR.relative_to(config.REPO_ROOT)}/")


if __name__ == "__main__":
    main()
