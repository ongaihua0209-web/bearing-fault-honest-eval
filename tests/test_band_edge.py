"""
Tests for src/check_band_edge.py and the guarantee it stands for:
no signal handed to later code carries anything above 5.2 kHz.
"""

import unittest

import numpy as np

from src import check_band_edge as band
from src import config, load_data


class TestMeasurements(unittest.TestCase):

    def test_share_above_edge_for_white_noise(self):
        # White noise spreads its power evenly over 0-6 kHz, so the share
        # above 5.2 kHz is (6000 - 5200) / 6000 = 13.3%, i.e. about -8.8 dB.
        rng = np.random.default_rng(0)
        self.assertAlmostEqual(band.share_above_db(rng.normal(size=120_000)),
                               10 * np.log10(800 / 6000), delta=0.3)

    def test_resampling_filter_is_flat_where_we_keep_the_signal(self):
        """
        The 5 kHz cutoff relies on scipy's 48 -> 12 kHz resampling filter
        being flat below 4.8 kHz. If a future scipy version changed that,
        this test would catch it.
        """
        freqs, db = band.resampling_filter_response()
        keep = (freqs > 100) & (freqs <= config.LOWPASS_PASSBAND_EDGE_HZ)
        self.assertLess(np.abs(db[keep]).max(), 0.5)


class TestRealFiles(unittest.TestCase):

    def test_no_signal_has_content_above_the_stopband_edge(self):
        present = [r["file_number"] for r in config.expected_files()
                   if load_data.mat_path(r["file_number"]).exists()]
        if not present:
            self.skipTest("no CWRU files in data/raw/")
        for number in present:
            with self.subTest(file=number):
                signal, _, _ = load_data.load_signal(number)
                # less than 1 part in 10 billion of the power above 5.2 kHz
                self.assertLess(band.share_above_db(signal), -100)


if __name__ == "__main__":
    unittest.main()
