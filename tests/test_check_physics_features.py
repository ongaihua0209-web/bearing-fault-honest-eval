"""
Tests for src/check_physics_features.py: the resolution argument behind the
8192-sample windows, and the sanity check on real data.
"""

import unittest

import numpy as np

from src import check_physics_features as chk
from src import config, features, load_data, segment


class TestResolution(unittest.TestCase):

    def setUp(self):
        self.table = chk.resolution_table()            # at 1730 rpm

    def test_2048_samples_cannot_separate_most_lines(self):
        self.assertEqual(int(self.table["separated_2048"].sum()), 3)

    def test_8192_samples_separate_all_but_one_pair(self):
        unseparated = set(self.table.loc[~self.table["separated_8192"], "line"])
        self.assertEqual(unseparated, {"3xbpfo", "2xbpfi"})

    def test_that_pair_is_under_one_percent_apart(self):
        # 3 x 3.585 = 10.754 vs 2 x 5.415 = 10.830: 0.7% apart, about the
        # size of real-world slip, so no window length truly separates them.
        a = 3 * features.F3_TARGETS["bpfo"]
        b = 2 * features.F3_TARGETS["bpfi"]
        self.assertLess(abs(a - b) / b, 0.01)

    def test_2xbsf_and_the_outer_race_sideband(self):
        row = self.table.set_index("line").loc["1x2xbsf"]
        self.assertEqual(row["nearest"], "BPFO+1x")
        self.assertLess(row["gap_hz"], 4.0)


class TestSanityOnRealData(unittest.TestCase):
    """Inner race should show more at BPFI than BPFO in most windows; outer race the reverse."""

    @classmethod
    def setUpClass(cls):
        if not all(load_data.mat_path(r["file_number"]).exists() for r in config.expected_files()):
            raise unittest.SkipTest("not all 40 data files are present")
        windows, cls.meta = segment.make_windows(config.F3_WINDOW_LENGTH_SAMPLES)
        kurtosis, f3 = features.f3_for_every_band(windows, cls.meta["rpm"].to_numpy())
        band = features.choose_band(kurtosis, np.arange(len(windows)))
        cls.sanity = chk.sanity_table(cls.meta, f3[band]).set_index(["fault_location", "fault_size_in"])

    def test_inner_race_mostly_bpfi(self):
        self.assertGreater(self.sanity.loc[("inner_race", "all"), "share_true"], 0.5)

    def test_outer_race_mostly_bpfo(self):
        self.assertGreater(self.sanity.loc[("outer_race", "all"), "share_true"], 0.5)


if __name__ == "__main__":
    unittest.main()
