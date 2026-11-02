"""
Tests for src/segment.py.
"""

import unittest

import numpy as np

from src import config, load_data, segment


class TestCutting(unittest.TestCase):

    def test_back_to_back_windows_with_leftover_dropped(self):
        x = np.arange(10_000)
        w = segment.cut_into_windows(x, length=2048)
        self.assertEqual(w.shape, (4, 2048))              # 4 x 2048 = 8192 used
        np.testing.assert_array_equal(w[0], x[:2048])
        np.testing.assert_array_equal(w[3], x[3 * 2048:4 * 2048])
        # no sample is used twice
        self.assertEqual(len(np.unique(w)), w.size)

    def test_too_short_signal_gives_no_windows(self):
        self.assertEqual(len(segment.cut_into_windows(np.zeros(100), 2048)), 0)


class TestRealWindows(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not all(load_data.mat_path(r["file_number"]).exists() for r in config.expected_files()):
            raise unittest.SkipTest("not all 40 data files are present")
        cls.windows, cls.meta = segment.make_windows()

    def test_shapes_match(self):
        self.assertEqual(len(self.windows), len(self.meta))
        self.assertEqual(self.windows.shape[1], config.WINDOW_LENGTH_SAMPLES)

    def test_each_recording_gives_all_its_whole_windows(self):
        counts = self.meta.groupby("file_number").size()
        for number in (97, 105, 237):
            with self.subTest(file=number):
                signal, _, _ = load_data.load_signal(number)
                self.assertEqual(counts[number], len(signal) // config.WINDOW_LENGTH_SAMPLES)

    def test_windows_keep_their_recordings_facts(self):
        row = self.meta[self.meta["file_number"] == 186].iloc[0]
        self.assertEqual((row["fault_location"], row["fault_size_in"], row["load_hp"]),
                         ("ball", 0.014, 1))

    def test_first_window_is_the_start_of_the_signal(self):
        signal, _, _ = load_data.load_signal(130)
        first = self.windows[(self.meta["file_number"] == 130).to_numpy()][0]
        np.testing.assert_array_equal(first, signal[:config.WINDOW_LENGTH_SAMPLES])


if __name__ == "__main__":
    unittest.main()
