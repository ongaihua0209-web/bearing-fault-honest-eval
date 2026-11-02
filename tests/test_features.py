"""
Tests for src/features.py, using signals whose answers are known by hand.
"""

import unittest

import numpy as np

from src import features


class TestFeatureSetF1(unittest.TestCase):

    def test_sine_wave(self):
        # A sine of amplitude 2: RMS = 2/sqrt(2), peak = 2, peak-to-peak = 4,
        # crest factor = sqrt(2), kurtosis = 1.5, skewness = 0.
        t = np.arange(12_000) / 12_000
        x = 2 * np.sin(2 * np.pi * 50 * t)          # exactly 50 whole cycles
        f = features.features_f1(x).iloc[0]
        self.assertAlmostEqual(f["rms"], 2 / np.sqrt(2), places=6)
        self.assertAlmostEqual(f["peak"], 2, places=3)
        self.assertAlmostEqual(f["peak_to_peak"], 4, places=3)
        self.assertAlmostEqual(f["crest_factor"], np.sqrt(2), places=3)
        self.assertAlmostEqual(f["kurtosis"], 1.5, places=3)
        self.assertAlmostEqual(f["skewness"], 0, places=6)
        self.assertAlmostEqual(f["std"], f["rms"], places=6)

    def test_random_noise_has_kurtosis_3(self):
        rng = np.random.default_rng(0)
        f = features.features_f1(rng.normal(size=200_000)).iloc[0]
        self.assertAlmostEqual(f["kurtosis"], 3.0, delta=0.05)
        self.assertAlmostEqual(f["skewness"], 0.0, delta=0.02)

    def test_impacts_raise_kurtosis_and_crest_factor(self):
        rng = np.random.default_rng(1)
        x = rng.normal(0, 0.1, 2048)
        smooth = features.features_f1(x).iloc[0]
        x[::200] += 3.0                              # sharp knocks
        knocks = features.features_f1(x).iloc[0]
        self.assertGreater(knocks["kurtosis"], 10 * smooth["kurtosis"] / 3)
        self.assertGreater(knocks["crest_factor"], smooth["crest_factor"])

    def test_std_ignores_a_steady_offset_but_rms_does_not(self):
        rng = np.random.default_rng(2)
        x = rng.normal(size=2048)
        a = features.features_f1(x).iloc[0]
        b = features.features_f1(x + 5).iloc[0]
        self.assertAlmostEqual(a["std"], b["std"], places=10)
        self.assertGreater(b["rms"], a["rms"])

    def test_one_row_per_window(self):
        table = features.features_f1(np.random.default_rng(3).normal(size=(10, 2048)))
        self.assertEqual(table.shape, (10, 7))
        self.assertEqual(list(table.columns), features.FEATURE_NAMES_F1)


if __name__ == "__main__":
    unittest.main()
