"""
Tests for src/splits.py: proof of what each protocol keeps apart.

Most tests use a stand-in window table with the real structure (40
recordings, about 59 windows each, recording 97 shorter), so they run in
milliseconds. One test repeats the key checks on the real windows.

What must hold:
  every protocol - no window is in both train and test, and every window
                   is used on one side or the other;
  B and C        - no FAULTY recording is in both train and test;
  C              - faulty test windows are all of the held-out size, and
                   that size never appears in training;
  A              - recordings DO appear on both sides (that is the leak we
                   want to demonstrate, so we prove it exists).
"""

import unittest

import numpy as np
import pandas as pd

from src import config, segment, splits


def stand_in_meta():
    """A window table shaped like the real one, without loading any data."""
    rows = []
    for info in config.expected_files():
        n_windows = 29 if info["file_number"] == 97 else 59
        rows += [{**info, "window_in_file": i} for i in range(n_windows)]
    return pd.DataFrame(rows)


def recordings(meta, positions, faulty_only=False):
    part = meta.iloc[positions]
    if faulty_only:
        part = part[part["fault_location"] != "normal"]
    return set(part["file_number"])


class SplitChecks:
    """Checks shared by the stand-in and real-data tests."""

    def assert_clean_partition(self, meta, train, test):
        self.assertEqual(len(set(train) & set(test)), 0, "window on both sides")
        self.assertEqual(len(train) + len(test), len(meta), "window left out")
        for side in (train, test):
            self.assertEqual(set(meta.iloc[side]["fault_location"]), set(splits.CLASSES),
                             "a class is missing from one side")

    def assert_no_shared_faulty_recording(self, meta, train, test):
        shared = (recordings(meta, train, faulty_only=True)
                  & recordings(meta, test, faulty_only=True))
        self.assertEqual(shared, set(), f"faulty recordings on both sides: {shared}")


class TestProtocolA(unittest.TestCase, SplitChecks):

    def setUp(self):
        self.meta = stand_in_meta()

    def test_clean_partition_for_every_seed(self):
        for seed in range(5):
            with self.subTest(seed=seed):
                train, test = splits.split_random(self.meta, seed)
                self.assert_clean_partition(self.meta, train, test)
                self.assertAlmostEqual(len(test) / len(self.meta), 0.2, delta=0.01)

    def test_seeds_give_different_splits(self):
        _, test0 = splits.split_random(self.meta, 0)
        _, test1 = splits.split_random(self.meta, 1)
        self.assertFalse(np.array_equal(test0, test1))

    def test_the_leak_is_real_every_recording_is_on_both_sides(self):
        train, test = splits.split_random(self.meta, 0)
        shared = recordings(self.meta, train) & recordings(self.meta, test)
        self.assertEqual(len(shared), 40)


class TestProtocolB(unittest.TestCase, SplitChecks):

    def setUp(self):
        self.meta = stand_in_meta()
        self.train, self.test = splits.split_by_load(self.meta)

    def test_clean_partition(self):
        self.assert_clean_partition(self.meta, self.train, self.test)

    def test_no_recording_on_both_sides(self):
        self.assert_no_shared_faulty_recording(self.meta, self.train, self.test)
        self.assertEqual(recordings(self.meta, self.train) & recordings(self.meta, self.test), set())

    def test_loads(self):
        self.assertEqual(set(self.meta.iloc[self.test]["load_hp"]), {3})
        self.assertEqual(set(self.meta.iloc[self.train]["load_hp"]), {0, 1, 2})


class TestProtocolC(unittest.TestCase, SplitChecks):

    def setUp(self):
        self.meta = stand_in_meta()

    def folds(self):
        for size in splits.C_FAULT_SIZES:
            yield size, splits.split_by_fault_size(self.meta, size)

    def test_clean_partition_for_every_fold(self):
        for size, (train, test) in self.folds():
            with self.subTest(fold=size):
                self.assert_clean_partition(self.meta, train, test)

    def test_no_faulty_recording_on_both_sides(self):
        for size, (train, test) in self.folds():
            with self.subTest(fold=size):
                self.assert_no_shared_faulty_recording(self.meta, train, test)

    def test_held_out_size_is_only_in_test(self):
        for size, (train, test) in self.folds():
            with self.subTest(fold=size):
                faulty = self.meta["fault_location"] != "normal"
                test_sizes = set(self.meta.iloc[test][faulty.iloc[test].values]["fault_size_in"])
                train_sizes = set(self.meta.iloc[train][faulty.iloc[train].values]["fault_size_in"])
                self.assertEqual(test_sizes, {size})
                self.assertNotIn(size, train_sizes)
                # every fault type is tested at the held-out size
                test_types = set(self.meta.iloc[test]["fault_location"]) - {"normal"}
                self.assertEqual(test_types, {"inner_race", "ball", "outer_race"})

    def test_healthy_class_holds_out_one_load_per_fold(self):
        for size, (train, test) in self.folds():
            with self.subTest(fold=size):
                normal_test = self.meta.iloc[test].query("fault_location == 'normal'")
                normal_train = self.meta.iloc[train].query("fault_location == 'normal'")
                self.assertEqual(set(normal_test["load_hp"]), {splits.C_NORMAL_TEST_LOAD[size]})
                # different healthy RECORDINGS on each side ...
                self.assertEqual(set(normal_test["file_number"]) & set(normal_train["file_number"]), set())
                # ... but, as documented, the same healthy BEARING on both sides
                self.assertGreater(len(normal_train), 0)

    def test_each_window_is_tested_at_most_once_across_folds(self):
        tested = np.concatenate([test for _, (_, test) in self.folds()])
        self.assertEqual(len(tested), len(set(tested)))


class TestAllSplits(unittest.TestCase):

    def test_counts(self):
        all_splits = splits.all_splits(stand_in_meta(), seeds=range(5))
        protocols = [s["protocol"] for s in all_splits]
        self.assertEqual(protocols.count("A"), 5)
        self.assertEqual(protocols.count("B"), 5)
        self.assertEqual(protocols.count("C"), 15)


class TestOnRealWindows(unittest.TestCase, SplitChecks):

    @classmethod
    def setUpClass(cls):
        if not all((config.RAW_DATA_DIR / f"{r['file_number']}.mat").exists()
                   for r in config.expected_files()):
            raise unittest.SkipTest("not all 40 data files are present")
        _, cls.meta = segment.make_windows()

    def test_all_protocols_on_real_windows(self):
        for s in splits.all_splits(self.meta, seeds=[0]):
            with self.subTest(protocol=s["protocol"], fold=s["fold"]):
                self.assert_clean_partition(self.meta, s["train"], s["test"])
                if s["protocol"] in ("B", "C"):
                    self.assert_no_shared_faulty_recording(self.meta, s["train"], s["test"])


if __name__ == "__main__":
    unittest.main()
