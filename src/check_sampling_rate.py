"""
check_sampling_rate.py - was each file really recorded at 12 kHz?

Why this matters: sources disagree on whether CWRU's normal (healthy) files
were recorded at 12 kHz or 48 kHz. If one class of data were secretly at a
different rate, a classifier could learn "this file looks like 48 kHz"
instead of "this bearing is damaged" - a shortcut that inflates accuracy.

The idea of the check:
  The shaft turns rpm/60 times per second, so a vibration spectrum almost
  always has a peak at that frequency (called "1x"), and usually at 2x, 3x...
  A spectrum's frequency axis is calculated FROM the sampling rate. Every
  file is read here as if it were 12 kHz. If it was really recorded at
  48 kHz, every frequency comes out 4 times too low, so the true 1x, 2x and
  3x peaks land at 1/4, 1/2 and 3/4 of shaft speed.

Two tests, read off one spectrum:
  A. Is there a clear peak at 1x (shaft speed)?
  B. How many of the "quarter orders" 0.25x, 0.50x and 0.75x show a clear
     peak? A genuine 12 kHz recording has no physical reason to vibrate
     at a quarter, half or three-quarters of shaft speed. A 48 kHz
     recording read as 12 kHz does, because those are its true 1x, 2x, 3x.

  Why test A alone is not enough: in a 48 kHz file read as 12 kHz, the
  true 4x harmonic lands exactly on the 1x position. So a peak at 1x does
  not prove 12 kHz. A peak at 0.25x, however, has no innocent explanation.

Verdict:
  12kHz        - clear 1x peak AND no quarter-order peaks
  48kHz        - clear 0.25x peak AND at least 2 of the 3 quarter orders
  inconclusive - anything else; a person must look at the plot

"A clear peak": within +/-3% of the expected frequency, the largest value
must be at least 10 times the typical (median) level of the spectrum
around it (+/-30%).

Run it AFTER src/load_data.py:
    python -m src.check_sampling_rate

Outputs:
    results/sampling_rate_check.csv
    results/figures/sampling_rate/<file>.png        one plot per file
    results/figures/sampling_rate/<file>_resampled_to_12k.png
                                                    for files resampled
    results/figures/sampling_rate_overview.png       all files on one page
"""

import math

import matplotlib
matplotlib.use("Agg")            # draw to files, no screen needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src import bearing_physics, config, load_data

SEARCH_TOLERANCE = 0.03     # look for the peak within +/-3% of where it should be
BACKGROUND_SPAN = 0.30      # compare it with the spectrum within +/-30%
CLEAR_PEAK_RATIO = 10       # a real peak is at least 10x its background

# Multiples of shaft speed we look at. 48 kHz / 12 kHz = 4, so a 48 kHz
# file's true 1x, 2x, 3x appear at 1/4, 2/4, 3/4 when read as 12 kHz.
QUARTER_ORDERS = (0.25, 0.50, 0.75)
ORDERS_TO_TEST = QUARTER_ORDERS + (1.00,)
QUARTER_PEAKS_NEEDED_FOR_48K = 2

PLOT_MAX_HZ = 200

# Chart colours (a colour-blind-checked palette) and neutral inks.
COLOUR_SPECTRUM = "#2a78d6"   # blue
COLOUR_1X = "#eb6834"         # orange
COLOUR_QUARTERS = "#1baf7a"   # aqua
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
    Run tests A and B (see top of file) on one signal, read at assumed_fs.

    Returns (result_dict, frequencies, amplitudes).
    """
    frequencies, amplitudes = amplitude_spectrum(signal, assumed_fs)
    shaft_hz = rpm / 60.0
    result = {"shaft_1x_hz": round(shaft_hz, 3)}

    is_clear = {}
    for order in ORDERS_TO_TEST:
        found_hz, ratio = peak_strength(frequencies, amplitudes, order * shaft_hz)
        result[f"peak_hz_at_{order:.2f}x"] = round(found_hz, 3)
        result[f"ratio_at_{order:.2f}x"] = round(ratio, 1)
        is_clear[order] = ratio >= CLEAR_PEAK_RATIO

    n_quarter_peaks = sum(is_clear[order] for order in QUARTER_ORDERS)
    result["n_quarter_order_peaks"] = n_quarter_peaks

    if is_clear[1.00] and n_quarter_peaks == 0:
        result["verdict"] = "12kHz"
    elif is_clear[0.25] and n_quarter_peaks >= QUARTER_PEAKS_NEEDED_FOR_48K:
        result["verdict"] = "48kHz"
    else:
        result["verdict"] = "inconclusive"
    return result, frequencies, amplitudes


def verdict_for_rate(rate_hz):
    """12000 -> '12kHz', so config values can be compared with verdicts."""
    return f"{int(rate_hz) // 1000}kHz"


def _draw_spectrum(ax, frequencies, amplitudes, result, rpm, compact=False):
    """Draw one spectrum with the reference lines on a matplotlib axis."""
    show = (frequencies > 0) & (frequencies <= PLOT_MAX_HZ)
    shaft_hz = result["shaft_1x_hz"]
    # zorder controls what is drawn on top: the spectrum (3) sits above the
    # reference lines (1), so a line never hides the peak it points at.
    ax.semilogy(frequencies[show], amplitudes[show], color=COLOUR_SPECTRUM,
                linewidth=0.8, zorder=3, label="Spectrum, read as 12 kHz")
    ax.axvline(shaft_hz, color=COLOUR_1X, linestyle="--", linewidth=1.4,
               zorder=1, label="1x shaft speed (rpm/60)")
    for i, order in enumerate(QUARTER_ORDERS):
        ax.axvline(order * shaft_hz, color=COLOUR_QUARTERS, linestyle="--",
                   linewidth=1.2, zorder=1,
                   label="0.25x / 0.5x / 0.75x: true 1x, 2x, 3x if really 48 kHz"
                   if i == 0 else None)

    # Theoretical fault frequencies, as faint reference lines.
    fault_hz = bearing_physics.fault_frequencies_hz(rpm)
    for name in ("BPFO", "2xBSF", "BPFI"):
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


def plot_file(file_number, title, frequencies, amplitudes, result, rpm, path):
    """Save one detailed spectrum plot for one file."""
    fig, ax = plt.subplots(figsize=(9, 4.8), facecolor=SURFACE)
    _draw_spectrum(ax, frequencies, amplitudes, result, rpm)
    ax.set_xlabel("Frequency (Hz), calculated assuming 12 kHz", color=INK)
    ax.set_ylabel("Amplitude (g, log scale)", color=INK)
    ax.set_title(f"{file_number}.mat  |  {title}  |  {rpm:.0f} rpm  |  "
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
    """All files on one page (one row per condition, one column per load)."""
    n = len(panels)
    n_cols = min(4, n)
    n_rows = math.ceil(n / n_cols)
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(3.6 * n_cols, 2.4 * n_rows + 0.9),
                             facecolor=SURFACE, squeeze=False)
    for ax, (file_number, label, freqs, amps, result, rpm) in zip(axes.flat, panels):
        _draw_spectrum(ax, freqs, amps, result, rpm, compact=True)
        ax.set_title(f"{file_number}.mat {label}: {result['verdict']}",
                     fontsize=8, color=INK, loc="left")
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=3, fontsize=9,
               frameon=False, labelcolor=INK_SECONDARY)
    fig.supxlabel("Frequency (Hz), calculated assuming 12 kHz", fontsize=10, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.5 / (2.4 * n_rows + 0.9)))
    fig.savefig(path, dpi=100)
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
            after, freqs_after, amps_after = check_signal(resampled, rpm)
            row["verdict_after_resampling"] = after["verdict"]
            plot_file(number, label + ", resampled to 12 kHz", freqs_after,
                      amps_after, after, rpm,
                      figure_dir / f"{number}_resampled_to_12k.png")
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

    columns = ["file_number", "rpm", "ratio_at_0.25x", "ratio_at_0.50x",
               "ratio_at_0.75x", "ratio_at_1.00x", "verdict", "rate_in_config_hz",
               "verdict_after_resampling"]
    print(table[columns].to_string(index=False))

    # Shout if the evidence disagrees with what config.py says.
    disagree = table[(table["verdict"] != "inconclusive") &
                     (table["verdict"] != table["rate_in_config_hz"].map(verdict_for_rate))]
    unsure = table[table["verdict"] == "inconclusive"]
    bad_resample = table[~table["verdict_after_resampling"].isin(["not needed", "12kHz"])]
    if len(disagree):
        print("\nWARNING: these files disagree with config.py and need an override:")
        print(disagree[["file_number", "verdict", "rate_in_config_hz"]].to_string(index=False))
    if len(unsure):
        print("\nWARNING: inconclusive - look at the plots for files",
              ", ".join(str(n) for n in unsure["file_number"]))
    if len(bad_resample):
        print("\nWARNING: resampled files that do not check out as 12 kHz:",
              ", ".join(str(n) for n in bad_resample["file_number"]))
    if not (len(disagree) or len(unsure) or len(bad_resample)):
        print("\nAll checked files agree with the sampling rates in config.py.")

    print(f"\nSaved {out_csv.relative_to(config.REPO_ROOT)} and plots in "
          f"{config.FIGURES_DIR.relative_to(config.REPO_ROOT)}/")


if __name__ == "__main__":
    main()
