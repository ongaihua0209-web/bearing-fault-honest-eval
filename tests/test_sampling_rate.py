"""
Tests for src/check_sampling_rate.py.

We build fake vibration signals where we KNOW the true sampling rate, and
check that the method gets the answer right. Then we check the real files.
"""

import unittest

import numpy as np
import pandas as pd

from src import check_sampling_rate as check
from src import config, load_data

RPM = 1797
SHAFT_HZ = RPM / 60


def fake_vibration(true_fs, seconds=10, seed=0):
    """
    Shaft vibration at 1x, 2x and 3x shaft speed (real machines vibrate at
    several harmonics), buried in random noise, sampled at true_fs.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(int(true_fs * seconds)) / true_fs
    x = rng.normal(0, 0.1, t.size)
    for harmonic, amplitude in ((1, 0.05), (2, 0.03), (3, 0.02)):
        x += amplitude * np.sin(2 * np.pi * harmonic * SHAFT_HZ * t)
    return x


class TestMethodOnFakeSignals(unittest.TestCase):

    def test_true_12k_signal_is_recognised(self):
        result, _, _ = check.check_signal(fake_vibration(12_000), RPM)
        self.assertEqual(result["verdict"], "12kHz")
        self.assertEqual(result["n_quarter_order_peaks"], 0)
        self.assertAlmostEqual(result["peak_hz_at_1.00x"], SHAFT_HZ, delta=0.2)

    def test_true_48k_signal_read_as_12k_is_caught(self):
        # Pretend to be fooled: hand a 48 kHz recording to a 12 kHz reader.
        result, _, _ = check.check_signal(fake_vibration(48_000), RPM, assumed_fs=12_000)
        self.assertEqual(result["verdict"], "48kHz")
        self.assertEqual(result["n_quarter_order_peaks"], 3)
        # The true 1x peak shows up 4 times too low.
        self.assertAlmostEqual(result["peak_hz_at_0.25x"], SHAFT_HZ / 4, delta=0.1)

    def test_48k_file_whose_4x_harmonic_fakes_a_1x_peak(self):
        """
        The trap that made version 1 of the check say 'inconclusive':
        a 48 kHz file with a strong 4x harmonic shows a peak exactly where a
        12 kHz file's 1x would be. The quarter-order test must still win.
        """
        t = np.arange(48_000 * 10) / 48_000
        x = fake_vibration(48_000) + 0.05 * np.sin(2 * np.pi * 4 * SHAFT_HZ * t)
        result, _, _ = check.check_signal(x, RPM)
        self.assertGreaterEqual(result["ratio_at_1.00x"], check.CLEAR_PEAK_RATIO)
        self.assertEqual(result["verdict"], "48kHz")

    def test_48k_signal_is_12k_after_resampling(self):
        resampled = load_data.resample_to_target(fake_vibration(48_000), 48_000, 12_000)
        result, _, _ = check.check_signal(resampled, RPM)
        self.assertEqual(result["verdict"], "12kHz")

    def test_one_stray_quarter_order_peak_is_inconclusive(self):
        # A 12 kHz file that happens to have one resonance near 0.5x.
        t = np.arange(12_000 * 10) / 12_000
        x = fake_vibration(12_000) + 0.05 * np.sin(2 * np.pi * 0.5 * SHAFT_HZ * t)
        result, _, _ = check.check_signal(x, RPM)
        self.assertEqual(result["n_quarter_order_peaks"], 1)
        self.assertEqual(result["verdict"], "inconclusive")

    def test_pure_noise_is_inconclusive(self):
        rng = np.random.default_rng(1)
        result, _, _ = check.check_signal(rng.normal(size=120_000), RPM)
        self.assertEqual(result["verdict"], "inconclusive")

    def test_spectrum_amplitude_scaling(self):
        # A sine of amplitude 2 should show a peak of about 2.
        fs = 12_000
        t = np.arange(fs * 10) / fs
        _, amps = check.amplitude_spectrum(2.0 * np.sin(2 * np.pi * 100 * t), fs)
        self.assertAlmostEqual(amps.max(), 2.0, delta=0.05)


def present_file_numbers():
    return [r["file_number"] for r in config.expected_files()
            if load_data.mat_path(r["file_number"]).exists()]


class TestRealFiles(unittest.TestCase):

    def test_raw_files_match_the_rates_in_config(self):
        """Each raw file's verdict must equal the rate config.py records."""
        present = present_file_numbers()
        if not present:
            self.skipTest("no CWRU files in data/raw/")
        for number in present:
            with self.subTest(file=number):
                signal, rpm = load_data.load_raw_signal(number)
                result, _, _ = check.check_signal(signal, rpm)
                expected = check.verdict_for_rate(load_data.recorded_sampling_rate(number))
                self.assertEqual(result["verdict"], expected)

    def test_every_signal_handed_to_later_code_is_12k(self):
        """The guarantee the rest of the project relies on."""
        present = present_file_numbers()
        if not present:
            self.skipTest("no CWRU files in data/raw/")
        for number in present:
            with self.subTest(file=number):
                signal, rpm, fs = load_data.load_signal(number)
                self.assertEqual(fs, 12_000)
                result, _, _ = check.check_signal(signal, rpm)
                self.assertEqual(result["verdict"], "12kHz")

    def test_config_agrees_with_saved_check(self):
        """If the saved check says a file is 48 kHz, config.py must say so too."""
        path = config.RESULTS_DIR / "sampling_rate_check.csv"
        if not path.exists():
            self.skipTest("run python -m src.check_sampling_rate first")
        table = pd.read_csv(path)
        for _, row in table[table["verdict"] != "inconclusive"].iterrows():
            number = int(row["file_number"])
            with self.subTest(file=number):
                expected = check.verdict_for_rate(load_data.recorded_sampling_rate(number))
                self.assertEqual(row["verdict"], expected)


if __name__ == "__main__":
    unittest.main()
