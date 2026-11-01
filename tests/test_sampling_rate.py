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
    """A 1x shaft sine buried in random noise, sampled at true_fs."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(true_fs * seconds)) / true_fs
    return 0.05 * np.sin(2 * np.pi * SHAFT_HZ * t) + rng.normal(0, 0.1, t.size)


class TestMethodOnFakeSignals(unittest.TestCase):

    def test_true_12k_signal_is_recognised(self):
        result, _, _ = check.check_signal(fake_vibration(12_000), RPM)
        self.assertEqual(result["verdict"], "12kHz")
        self.assertAlmostEqual(result["if_12k_found_hz"], SHAFT_HZ, delta=0.2)

    def test_true_48k_signal_read_as_12k_is_caught(self):
        # Pretend to be fooled: hand a 48 kHz recording to a 12 kHz reader.
        result, _, _ = check.check_signal(fake_vibration(48_000), RPM, assumed_fs=12_000)
        self.assertEqual(result["verdict"], "48kHz")
        # The 1x peak shows up 4 times too low.
        self.assertAlmostEqual(result["if_48k_found_hz"], SHAFT_HZ / 4, delta=0.1)

    def test_48k_signal_is_12k_after_resampling(self):
        resampled = load_data.resample_to_target(fake_vibration(48_000), 48_000, 12_000)
        result, _, _ = check.check_signal(resampled, RPM)
        self.assertEqual(result["verdict"], "12kHz")

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


class TestRealFiles(unittest.TestCase):

    def test_present_files_are_12k(self):
        present = [r["file_number"] for r in config.expected_files()
                   if load_data.mat_path(r["file_number"]).exists()]
        if not present:
            self.skipTest("no CWRU files in data/raw/")
        for number in present:
            with self.subTest(file=number):
                signal, rpm = load_data.load_raw_signal(number)
                result, _, _ = check.check_signal(signal, rpm)
                expected = check.verdict_for_rate(load_data.recorded_sampling_rate(number))
                self.assertEqual(result["verdict"], expected)

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
